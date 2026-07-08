import re
import os
import json
import argparse
import urllib.request
from html.parser import HTMLParser
from datetime import datetime

class TicketHTMLParser(HTMLParser):
    def __init__(self, concert_path):
        super().__init__()
        self.concert_path = concert_path
        self.in_link = False
        self.current_link = None
        self.current_data = []
        self.tickets = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == 'a' and 'href' in attrs_dict:
            href = attrs_dict['href']
            # Target resale ticket URLs on the concert page
            if self.concert_path in href:
                self.in_link = True
                self.current_link = href
                self.current_data = []

    def handle_endtag(self, tag):
        if tag == 'a' and self.in_link:
            text = " ".join(self.current_data)
            self.tickets.append({
                'link': self.current_link,
                'text': text
            })
            self.in_link = False
            self.current_link = None

    def handle_data(self, data):
        if self.in_link:
            clean_data = data.strip()
            if clean_data:
                self.current_data.append(clean_data)

def fetch_page_content(url):
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"[{datetime.now()}] Error fetching page: {e}")
        return None

def send_line_push_notification(channel_access_token, user_id, message):
    url = "https://api.line.me/v2/bot/message/push"
    payload = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": message.strip()
            }
        ]
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {channel_access_token}",
            "Content-Type": "application/json"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            print(f"[{datetime.now()}] LINE Push Notification sent successfully: {res_data}")
            return True
    except Exception as e:
        print(f"[{datetime.now()}] Error sending LINE Push Notification: {e}")
        return False

def send_telegram_notification(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message.strip()
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            if res_data.get("ok"):
                print(f"[{datetime.now()}] Telegram message sent successfully.")
                return True
            else:
                print(f"[{datetime.now()}] Telegram returned error: {res_data}")
                return False
    except Exception as e:
        print(f"[{datetime.now()}] Error sending Telegram message: {e}")
        return False

def load_notified_state(state_file):
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_notified_state(state_file, notified_list):
    try:
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(notified_list, f, indent=2, ensure_ascii=False)
        print(f"[{datetime.now()}] Saved state: {notified_list}")
    except Exception as e:
        print(f"[{datetime.now()}] Error saving state: {e}")

def main():
    parser = argparse.ArgumentParser(description="Tixxa Resale Ticket Monitor (Server Version)")
    parser.add_argument("--url", default="https://tixxa.co/th/rock-day-gfest-marathon-concert-2026-1387", help="Tixxa concert page URL")
    parser.add_argument("--line-token", help="LINE Messaging API Channel Access Token")
    parser.add_argument("--line-uid", help="LINE Messaging API User ID")
    parser.add_argument("--telegram-token", help="Telegram Bot Token")
    parser.add_argument("--telegram-chat", help="Telegram Chat ID")
    parser.add_argument("--qty", type=int, default=2, help="Minimum ticket quantity required")
    parser.add_argument("--state", help="State JSON file path for tracking notified tickets")
    args = parser.parse_args()
    
    # Validation: Must provide either LINE config or Telegram config
    has_line = args.line_token and args.line_uid
    has_telegram = args.telegram_token and args.telegram_chat
    if not (has_line or has_telegram):
        print("Error: You must configure either LINE Messaging API (--line-token AND --line-uid) or Telegram (--telegram-token AND --telegram-chat).")
        return
        
    script_dir = os.path.dirname(os.path.abspath(__file__))
    state_file = args.state if args.state else os.path.join(script_dir, "notified_tickets.json")
    
    # Extract path pattern from URL (e.g. /rock-day-gfest-marathon-concert-2026-1387)
    match = re.search(r'https?://[^/]+(/[^?#]+)', args.url)
    if not match:
        print("Error: Invalid Tixxa URL format.")
        return
    raw_path = match.group(1)
    # Remove language prefix (e.g., /th/ or /en/) if present
    clean_path = re.sub(r'^/(th|en|vi|my|zh|ja)/', '/', raw_path)
    concert_path = clean_path.rstrip('/') + '/'
    
    all_tickets = []
    current_ids = []
    all_seen_ids = set()
    page = 1
    
    while True:
        # Append pagination query parameter
        page_url = f"{args.url}?page={page}"
        print(f"[{datetime.now()}] Fetching resale page: {page_url}...")
        content = fetch_page_content(page_url)
        if not content:
            print(f"[{datetime.now()}] Failed to fetch page {page}. Ending pagination.")
            break
            
        parser_obj = TicketHTMLParser(concert_path)
        parser_obj.feed(content)
        
        if not parser_obj.tickets:
            print(f"[{datetime.now()}] No ticket links found on page {page}. Ending pagination.")
            break
            
        # Safeguard: Check if all tickets on this page have already been seen
        has_new_ticket = False
        for t in parser_obj.tickets:
            link = t['link']
            ticket_id_match = re.search(r'/(\d+)$', link)
            if ticket_id_match:
                ticket_id = ticket_id_match.group(1)
                if ticket_id not in all_seen_ids:
                    all_seen_ids.add(ticket_id)
                    has_new_ticket = True
                    
        if not has_new_ticket:
            print(f"[{datetime.now()}] All tickets on page {page} were already seen. Ending pagination to prevent loops.")
            break
            
        print(f"[{datetime.now()}] Page {page}: Found {len(parser_obj.tickets)} listings.")
        all_tickets.extend(parser_obj.tickets)
        page += 1
        
    matching_tickets = []

    for t in all_tickets:
        link = t['link']
        text = t['text']
        
        # Extract unique ticket listing ID from URL
        ticket_id_match = re.search(r'/(\d+)$', link)
        if not ticket_id_match:
            continue
        ticket_id = ticket_id_match.group(1)
        current_ids.append(ticket_id)

        # Extract quantity (จำนวน X บัตร)
        qty_match = re.search(r'จำนวน\s*(\d+)\s*บัตร', text)
        qty = int(qty_match.group(1)) if qty_match else 0
        
        # Extract price (e.g. X,XXX.XX บาท / บัตร)
        price_match = re.search(r'([\d,.]+)\s*บาท\s*/\s*บัตร', text)
        price = price_match.group(1) if price_match else "Unknown"

        # Extract details
        details = text
        details_match = re.match(r'^(.*?)\s*ราคาหน้าบัตร', text)
        if details_match:
            details = details_match.group(1).strip()
            # Remove date prefix if present
            details = re.sub(r'^\d+\s+\d+/\d+\s+', '', details)

        if qty >= args.qty:
            matching_tickets.append({
                'id': ticket_id,
                'qty': qty,
                'price': price,
                'details': details,
                'link': f"https://tixxa.co{link}"
            })

    print(f"[{datetime.now()}] Scanned all pages. Found {len(all_tickets)} total listings. {len(matching_tickets)} matching target quantity (>= {args.qty}).")

    if not matching_tickets:
        return

    notified_ids = load_notified_state(state_file)
    new_notified_ids = list(notified_ids)

    # Filter to only new matches
    tickets_to_alert = [t for t in matching_tickets if t['id'] not in notified_ids]

    if not tickets_to_alert:
        print(f"[{datetime.now()}] All matches were already notified. Skipping notifications.")
        return

    # Build alert message
    alert_body = f"[Ticket Alert] Found new listings on Tixxa with >= {args.qty} tickets!\n"
    for t in tickets_to_alert:
        alert_body += f"\n- {t['details']} ({t['qty']} tickets, {t['price']} THB/ticket)\n  Link: {t['link']}\n"
        new_notified_ids.append(t['id'])

    # Send notifications
    line_success = False
    telegram_success = False
    
    if has_line:
        line_success = send_line_push_notification(args.line_token, args.line_uid, alert_body)
    if has_telegram:
        telegram_success = send_telegram_notification(args.telegram_token, args.telegram_chat, alert_body)
        
    if line_success or telegram_success:
        active_notified_ids = [nid for nid in new_notified_ids if nid in current_ids or nid in [t['id'] for t in tickets_to_alert]]
        save_notified_state(state_file, active_notified_ids)

if __name__ == "__main__":
    main()

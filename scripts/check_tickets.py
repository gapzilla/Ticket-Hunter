import re
import os
import json
import argparse
import urllib.request
import subprocess
import gzip
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
        headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Encoding': 'gzip, deflate'
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            html_bytes = response.read()
            if response.info().get('Content-Encoding') == 'gzip':
                html_bytes = gzip.decompress(html_bytes)
            return html_bytes.decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"[{datetime.now()}] Error fetching page: {e}")
        return None

def send_email_via_applescript(to_address, subject, body):
    # Escape quotes and backslashes for AppleScript
    escaped_subject = subject.replace('\\', '\\\\').replace('"', '\\"')
    escaped_body = body.replace('\\', '\\\\').replace('"', '\\"')
    
    applescript = f'''
    tell application "Mail"
        set newMessage to make new outgoing message with properties {{subject:"{escaped_subject}", content:"{escaped_body}", visible:false}}
        tell newMessage
            make new to recipient with properties {{address:"{to_address}"}}
            send
        end tell
    end tell
    '''
    try:
        res = subprocess.run(['osascript', '-e', applescript], check=True, capture_output=True, text=True)
        print(f"[{datetime.now()}] Email sent successfully via Mail.app to {to_address}.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[{datetime.now()}] Error sending email via AppleScript: {e.stderr.strip()}")
        return False

def send_imessage_via_applescript(target, body):
    escaped_body = body.replace('\\', '\\\\').replace('"', '\\"')
    
    applescript = f'''
    tell application "Messages"
        set targetAccount to 1st account whose service type is iMessage
        set targetParticipant to participant "{target}" of targetAccount
        send "{escaped_body}" to targetParticipant
    end tell
    '''
    try:
        subprocess.run(['osascript', '-e', applescript], check=True, capture_output=True, text=True)
        print(f"[{datetime.now()}] iMessage sent successfully to {target}.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[{datetime.now()}] Error sending iMessage: {e.stderr.strip()}")
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
    except Exception as e:
        print(f"[{datetime.now()}] Error saving state: {e}")

def main():
    parser = argparse.ArgumentParser(description="Tixxa Resale Ticket Monitor")
    parser.add_argument("--url", default="https://tixxa.co/th/rock-day-gfest-marathon-concert-2026-1387", help="Tixxa concert page URL")
    parser.add_argument("--email", default="gapzilla@gmail.com", help="Target email for notification")
    parser.add_argument("--imessage", default="gapzilla@gmail.com", help="Target phone number or Apple ID for iMessage")
    parser.add_argument("--qty", type=int, default=2, help="Minimum ticket quantity required")
    parser.add_argument("--state", help="State JSON file path for tracking notified tickets")
    args = parser.parse_args()
    
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

    notified_ids = load_notified_state(state_file)
    new_notified_ids = list(notified_ids)

    # Filter to only new matches
    tickets_to_alert = [t for t in matching_tickets if t['id'] not in notified_ids]

    if not tickets_to_alert:
        print(f"[{datetime.now()}] No new matching tickets found. Sending status heartbeat...")
        subject = "[Status Update] Tixxa Check Completed"
        body = (
            "Dear Gap,\n\n"
            f"Our ticket monitor successfully ran and checked all pages ({len(all_tickets)} total listings found).\n\n"
            f"There are no new resale ticket listings matching your criteria (>= {args.qty} tickets).\n\n"
            "Kind regards,\n"
            "Kisadanu Unthawapee (Gap)\n"
            "Production Director"
        )
        
        # 1. Send Email
        send_email_via_applescript(args.email, subject, body)
        
        # 2. Send iMessage (if target specified)
        if args.imessage:
            imessage_body = f"[Status Update] Checked all pages ({len(all_tickets)} total listings). No new matching tickets found."
            send_imessage_via_applescript(args.imessage, imessage_body)
        return

    # Build and send email alert
    subject = f"[Ticket Alert] {args.qty}+ Resell Tickets Available for Rock Day GFEST"
    
    body_lines = [
        "Dear Gap,",
        "",
        "We have detected new resale ticket listings on Tixxa with target ticket count:",
        ""
    ]
    
    for t in tickets_to_alert:
        body_lines.append(f"- Detail: {t['details']}")
        body_lines.append(f"  Quantity: {t['qty']} tickets")
        body_lines.append(f"  Price: {t['price']} THB / ticket")
        body_lines.append(f"  Link: {t['link']}")
        body_lines.append("")
        new_notified_ids.append(t['id'])

    body_lines.append("Kind regards,")
    body_lines.append("Kisadanu Unthawapee (Gap)")
    body_lines.append("Production Director")
    
    email_body = "\n".join(body_lines)
    
    # 1. Send Email
    email_success = send_email_via_applescript(args.email, subject, email_body)
    
    # 2. Send iMessage (if target specified)
    imessage_success = False
    if args.imessage:
        imessage_body = f"[Ticket Alert] Found new listings on Tixxa with >= {args.qty} tickets!\n"
        for t in tickets_to_alert:
            imessage_body += f"\n- {t['details']} ({t['qty']} tickets, {t['price']} THB/ticket)\n  Link: {t['link']}\n"
        imessage_success = send_imessage_via_applescript(args.imessage, imessage_body)
        
    if email_success or imessage_success:
        active_notified_ids = [nid for nid in new_notified_ids if nid in current_ids or nid in [t['id'] for t in tickets_to_alert]]
        save_notified_state(state_file, active_notified_ids)

if __name__ == "__main__":
    main()

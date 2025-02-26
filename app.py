from flask import Flask, request, jsonify
import os
import requests
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)

# Load Google Sheets credentials
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
import json
creds_json = json.loads(os.getenv("GOOGLE_CREDENTIALS"))
creds = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
client = gspread.authorize(creds)

# Google Sheets info
SHEET_ID = "1aE6ZDZ8W1qozc985MDMJLilLFGYDEHRyAhZnBeA_gWM"
cars_sheet = client.open_by_key(SHEET_ID).worksheet("cars")  # Open "cars" sheet

# WhatsApp API Details
WHATSAPP_PHONE_NUMBER_ID = "525298894008965"
WHATSAPP_ACCESS_TOKEN = "EAASmeEcmWYcBOzeSVfNZBv0KqYBHCVzZAvwdTV8mO8ZACReuwiBj1gTXxRUlXmFTWHvPqm4GlfTcl2nSZAJ6332CGHZArIyCEvO8qeP1aNXKJRUoZAyhpATRGpj5PBjDCWS9MNYbwqFNdJ2UPmheS1n7fWuJQZCQsx5pJZABFKHpN6JtujZBt7md5Bo6YZC1XWDlorJ3RBLv59pNhNKZCmtqhCjegmkonys0ORZCAKQqpg5DpHfRU9QnndkZD"
VERIFY_TOKEN = "my_custom_token"

# Track last search results for users
user_car_codes = {}

@app.route('/webhook', methods=['GET'])
def verify():
    """Webhook verification for WhatsApp API."""
    token_sent = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if token_sent == VERIFY_TOKEN:
        return challenge
    return "Verification failed", 403

@app.route('/webhook', methods=['POST'])
def receive_message():
    """Handles incoming messages from WhatsApp."""
    data = request.json
    print("Received:", data)  # Debugging log

    if "entry" in data and len(data["entry"]) > 0:
        changes = data["entry"][0].get("changes", [])
        if len(changes) > 0 and "value" in changes[0]:
            value = changes[0]["value"]

            if "messages" in value:
                msg = value["messages"][0]
                sender = msg["from"]

                if "text" in msg:
                    car_number = msg["text"]["body"].strip()
                    car_code = get_car_code(car_number)

                    if car_code:
                        # Store car code and send menu
                        user_car_codes[sender] = car_code
                        send_menu(sender)
                    else:
                        send_message(sender, "רכב זה לא נמצא")

                elif "interactive" in msg:
                    selection = msg["interactive"]["button_reply"]["id"]
                    
                    if selection == "get_car_code" and sender in user_car_codes:
                        send_message(sender, user_car_codes[sender])
                        del user_car_codes[sender]  # Remove after sending
                    elif selection == "option_2":
                        pass  # Do nothing for now

    return jsonify({"status": "received"}), 200

def send_menu(recipient):
    """Sends a button-based menu (instant selection)."""
    url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": "הרכב נמצא! נא לבחור אפשרות:"},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "get_car_code", "title": "קוד לרכב"}},
                    {"type": "reply", "reply": {"id": "option_2", "title": "אפשרות 2"}}
                ]
            }
        }
    }

    response = requests.post(url, headers=headers, json=data)
    print("Menu Sent:", response.json())  # Debugging log

def get_car_code(car_number):
    """Fetches car code from Google Sheets based on the provided car number (4th column)"""
    records = cars_sheet.get_all_values()  # Fetch all rows as raw values (not dictionary)
    
    print(f"Searching for car number: {car_number}")  # Debugging log
    
    for row in records[1:]:
        if len(row) >= 4 and row[3].strip() == car_number:  # Column D (4th column)
            if len(row) >= 7 and row[6].strip():  # Column G (7th column) is not empty
                return f"*הקוד הוא:* {row[6].strip()}"
    
    return None  # Return None if not found

def send_message(recipient, text):
    """Sends a WhatsApp text message"""
    url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "text",
        "text": {"body": text}
    }
    
    response = requests.post(url, headers=headers, json=data)
    print("Message Sent:", response.json())  # Debugging log

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))  # Ensure it matches Render's assigned port
    app.run(host="0.0.0.0", port=port)
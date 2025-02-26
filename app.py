from flask import Flask, request, jsonify
import os
import requests
import gspread
from google.oauth2.service_account import Credentials
import json

app = Flask(__name__)

# Load Google Sheets credentials
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds_json = json.loads(os.getenv("GOOGLE_CREDENTIALS"))
creds = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
client = gspread.authorize(creds)

# Google Sheets info
SHEET_ID = "1aE6ZDZ8W1qozc985MDMJLilLFGYDEHRyAhZnBeA_gWM"
cars_sheet = client.open_by_key(SHEET_ID).worksheet("cars")

# WhatsApp API Details
WHATSAPP_PHONE_NUMBER_ID = "525298894008965"
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
VERIFY_TOKEN = "my_custom_token"

# Track user selections
user_category_selection = {}

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
                        send_message(sender, car_code)
                    else:
                        send_category_menu(sender)

                elif "interactive" in msg:
                    if "list_reply" in msg["interactive"]:
                        selected_id = msg["interactive"]["list_reply"]["id"]

                        if selected_id.startswith("category_"):
                            category_name = selected_id.replace("category_", "")
                            user_category_selection[sender] = category_name
                            send_car_menu(sender, category_name)

                        elif selected_id.startswith("car_"):
                            car_number = selected_id.replace("car_", "")
                            car_code = get_car_code(car_number)

                            if car_code:
                                send_message(sender, car_code)
                            else:
                                send_message(sender, "רכב זה לא נמצא, נא לנסות שוב")

                    elif "button_reply" in msg["interactive"]:
                        selection = msg["interactive"]["button_reply"]["id"]

                        if selection == "get_car_code":
                            send_message(sender, "בחרת בקשת קוד לרכב, אך לא סופק מספר רכב.")

    return jsonify({"status": "received"}), 200

def send_category_menu(recipient):
    """Sends a list of available categories (Step 1)."""
    url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    records = cars_sheet.get_all_values()[1:]  # Skip headers
    categories = set()

    for row in records:
        if len(row) >= 12 and row[11].strip().lower() == "false":  # Column L must be "FALSE"
            if len(row) >= 9 and row[8].strip():  # Column I (Category)
                categories.add(row[8].strip())

    categories = list(categories)[:10]  # Limit to 10 categories
    if not categories:
        send_message(recipient, "אין קטגוריות זמינות כרגע.")
        return

    rows = [{"id": f"category_{category}", "title": category} for category in categories]

    data = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": "רכב זה לא נמצא, אנא בחר קטגוריה:"},
            "action": {
                "button": "בחר קטגוריה",
                "sections": [{"title": "קטגוריות זמינות", "rows": rows}]
            }
        }
    }

    response = requests.post(url, headers=headers, json=data)
    print("Category Menu Sent:", response.json())

def send_car_menu(recipient, category):
    """Sends a list of cars from the selected category (Step 2)."""
    url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    records = cars_sheet.get_all_values()[1:]
    car_list = []

    for row in records:
        if len(row) >= 12 and row[11].strip().lower() == "false":  # Column L must be "FALSE"
            if len(row) >= 9 and row[8].strip() == category and row[1].strip() and row[3].strip():
                car_list.append({
                    "id": f"car_{row[3].strip()}",  # Car number as ID
                    "title": row[1].strip(),  # Model name
                    "description": row[3].strip()  # Car number
                })

    car_list = car_list[:10]  # Limit to 10 cars
    if not car_list:
        send_message(recipient, f"אין רכבים זמינים בקטגוריה {category}.")
        return

    data = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": f"רשימת רכבים בקטגוריה {category}:"},
            "action": {
                "button": "בחר רכב",
                "sections": [{"title": "רכבים זמינים", "rows": car_list}]
            }
        }
    }

    response = requests.post(url, headers=headers, json=data)
    print("Car Menu Sent:", response.json())

def get_car_code(car_number):
    """Fetches car code from Google Sheets."""
    records = cars_sheet.get_all_values()

    print(f"Searching for car number: {car_number}")  # Debugging log

    for row in records[1:]:
        if len(row) >= 4 and row[3].strip() == car_number:  # Column D (Car number)
            if len(row) >= 7 and row[6].strip():  # Column G (Car code)
                return f"*הקוד הוא:* {row[6].strip()}"

    return None

def send_message(recipient, text):
    """Sends a simple WhatsApp text message."""
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
    print("Message Sent:", response.json())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))  # Ensure it matches Render's assigned port
    app.run(host="0.0.0.0", port=port)
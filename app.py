from flask import Flask, request, jsonify
import os
import requests
import gspread
from google.oauth2.service_account import Credentials
import json
import dropbox

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
WHATSAPP_ACCESS_TOKEN = "EAASmeEcmWYcBOxqXcYNBCGNJMMB1k3e6Fm5rOkKfFX2fx5xCnZBSYpBsJ7uwrx8md1ZChTtIKZA8kRD04euZCB8PbfZC8ovAuZBbPk3S6zZAL0vooppkN99TlwZB4VSd7tPk4BIoB28UuODWtJMz78Sf1ZBW7tStwcWFe1DXTfvusiZBhY2ZACmnXO803DHZCoIanzpKg9suw0EUNo8qb0nN9cdLREtoc5uXNNTjbZALSuCRveUMqhzfw7CCA"
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
                    car_info = get_car_info(car_number)

                    if car_info:
                        car_model, car_code = car_info
                        send_car_options_menu(sender, car_number, car_model)  # Send button menu
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
                            car_info = get_car_info(car_number)

                            if car_info:
                                car_model, car_code = car_info
                                send_car_options_menu(sender, car_number, car_model)  # Send button menu
                            else:
                                send_message(sender, "רכב זה לא נמצא, נא לנסות שוב")

                    elif "button_reply" in msg["interactive"]:
                        selection = msg["interactive"]["button_reply"]["id"]

                        if selection.startswith("get_code_"):
                            car_number = selection.replace("get_code_", "")
                            car_code = get_car_code(car_number)
                            if car_code:
                                send_message(sender, car_code)
                            else:
                                send_message(sender, "לא נמצא קוד לרכב זה.")

                        elif selection.startswith("get_insurance_"):
                            car_number = selection.replace("get_insurance_", "")
                            send_insurance_file(sender, car_number)

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

def send_car_options_menu(recipient, car_number, car_model):
    """Sends a button menu with car options."""
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
            "body": {"text": f"*נמצא רכב:* {car_model}\nבחר אפשרות:"},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": f"get_code_{car_number}", "title": "קוד לרכב"}},
                    {"type": "reply", "reply": {"id": f"get_insurance_{car_number}", "title": "ביטוח לרכב"}},
                ]
            }
        }
    }

    response = requests.post(url, headers=headers, json=data)
    print("Car Options Menu Sent:", response.json())

def send_message(recipient, text):
    """Sends a plain text message to the recipient."""
    url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "text": {"body": text}
    }
    response = requests.post(url, headers=headers, json=data)
    print("Message Sent:", response.json())


def get_car_info(car_number):
    """Fetches car model and code from Google Sheets."""
    records = cars_sheet.get_all_values()
    for row in records[1:]:
        if len(row) >= 4 and row[3].strip() == car_number:
            return row[1].strip(), row[6].strip() if len(row) >= 7 else None
    return None

def get_car_code(car_number):
    """Fetches the car code from Google Sheets."""
    records = cars_sheet.get_all_values()

    print(f"Searching for car number: {car_number}")  # Debugging log

    for row in records[1:]:  # Skip headers
        if len(row) >= 4 and row[3].strip() == car_number:  # Column D (Car number)
            if len(row) >= 7 and row[6].strip():  # Column G (Car code)
                return f"*הקוד הוא:* {row[6].strip()}"  # Formatting the response with bold "הקוד הוא"

    return None  # Return None if not found


# Initialize Dropbox Client
DROPBOX_ACCESS_TOKEN = os.getenv("DROPBOX_ACCESS_TOKEN")
dbx = dropbox.Dropbox(DROPBOX_ACCESS_TOKEN)

def send_insurance_file(recipient, car_number):
    print(f"🚀 send_insurance_file() called for car: {car_number}")
    """Fetches the insurance file from Dropbox and sends it via WhatsApp."""
    url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    dropbox_folder = "/Apps/whatsapp_bot/Insurance"

    try:
        print(f"🔍 Searching for insurance file for car: {car_number} in {dropbox_folder}")

        # List all files in the insurance folder
        result = dbx.files_list_folder(dropbox_folder)
        matching_files = [entry.name for entry in result.entries if entry.name.startswith(car_number)]
        print(f"✅ Matching files: {matching_files}")

        if not matching_files:
            print(f"⚠️ No file found for {car_number}")
            send_message(recipient, "⚠️ לא נמצא קובץ ביטוח לרכב זה.")
            return

        # Take the first matching file
        file_name = matching_files[0]
        dropbox_path = f"{dropbox_folder}/{file_name}"
        print(f"📄 Sending file: {file_name} (Dropbox path: {dropbox_path})")

        # Try to get or create a shared link
        try:
            shared_link_metadata = dbx.sharing_create_shared_link_with_settings(dropbox_path)
            file_url = shared_link_metadata.url.replace("?dl=0", "?dl=1")  # Force direct download
        except dropbox.exceptions.ApiError as e:
            if isinstance(e.error, dropbox.sharing.CreateSharedLinkWithSettingsError) and \
                    e.error.get_path().is_shared_link_already_exists():
                print("🔗 Shared link already exists. Retrieving existing link.")
                # Fetch existing shared links
                existing_links = dbx.sharing_list_shared_links(dropbox_path).links
                if existing_links:
                    file_url = existing_links[0].url.replace("?dl=0", "?dl=1")  # Force direct download
                else:
                    raise e  # Re-raise if no links exist (shouldn't happen)
            else:
                raise e  # Re-raise unexpected errors

        print(f"🔗 Dropbox file URL: {file_url}")

        data = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "document",
            "document": {
                "link": file_url,
                "filename": file_name
            }
        }

        response = requests.post(url, headers=headers, json=data)
        print(f"📨 Insurance File Sent: {response.json()}")

    except dropbox.exceptions.ApiError as e:
        print(f"❌ Error fetching file from Dropbox: {e}")
        send_message(recipient, "⚠️ שגיאה בגישה לקובץ הביטוח.")
                
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
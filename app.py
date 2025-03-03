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
WHATSAPP_ACCESS_TOKEN = "EAASmeEcmWYcBO2lGVpP5OSDthcD3KL4Q7ypblAM3ZB1y2N6HkZCRSvfDSgnrNIKjnEWb6ns1ZBiZAQCtLf4c9EshCr2OxiQLzXLQTT8EIq7u7R1iNFfNrVQwX0mRhGAAulZCb0zXCEQgHoJM4ibN3eFZCyfbleyZBfwnjBrtekGrpb09oaMBZCifNSBjAbHxQiAY7O5LkLLBFAiFVpT7pw6c1vkNLhMOZC78tu0aKb28RTcdZCnCbkljoZD"
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

                    if car_info and all(car_info):
                        car_number, car_model, car_code = car_info
                        send_car_options_menu(sender, car_number, car_model)
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
                                car_number, car_model, car_code = car_info
                                send_car_options_menu(sender, car_number)  # Send button menu
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
            "body": {"text": f"*נמצא רכב:* {car_model}\n*מספר רכב:* {car_number}\nבחר אפשרות"},
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


def get_car_info(query):
    """Fetches car number, car model, and car code based on car number or name from Google Sheets."""
    records = cars_sheet.get_all_values()

    # Search by car number (Column D)
    for row in records[1:]:
        if len(row) >= 4 and row[3].strip() == query:
            if len(row) >= 7 and all([row[3].strip(), row[1].strip(), row[6].strip()]):                # Return: car number, car model, car code if all are not None
                return row[3].strip(), row[1].strip(), row[6].strip()
            else:
                return None  # Return None if data is incomplete

    # If not found by number, search by car model (Column B)
    for row in records[1:]:
        if len(row) >= 2 and row[1].strip().lower() == query.lower():
            if len(row) >= 7 and all([row[3].strip(), row[1].strip(), row[6].strip()]):
                # Return: car number, car model, car code if all are not None
                return row[3].strip(), row[1].strip(), row[6].strip()
            else:
                return None  # Return None if data is incomplete

    # If not found, return None explicitly
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
    url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_NUMBER_ID}/media"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"
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
        print(f"📄 Found file: {file_name} (Dropbox path: {dropbox_path})")

        # Download the file from Dropbox
        metadata, file_content = dbx.files_download(dropbox_path)

        # Upload the file to WhatsApp as media
        files = {
            'file': (file_name, file_content.content, 'application/pdf')
        }
        data = {
            "messaging_product": "whatsapp"  # Add this line to fix the error
        }
        response = requests.post(url, headers=headers, files=files, data=data)
        media_response = response.json()
        print(f"📨 Media Upload Response: {media_response}")

        if "id" not in media_response:
            print("❌ Error uploading file to WhatsApp.")
            send_message(recipient, "⚠️ שגיאה בהעלאת הקובץ לוואטסאפ.")
            return

        media_id = media_response["id"]

        # Send the uploaded file as a document
        message_url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
        message_headers = {
            "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "document",
            "document": {
                "id": media_id,
                "filename": file_name
            }
        }

        # Send the document to WhatsApp API
        send_response = requests.post(message_url, headers=message_headers, json=data)
        print(f"📨 Insurance File Sent: {send_response.json()}")

    except dropbox.exceptions.ApiError as e:
        print(f"❌ Error fetching file from Dropbox: {e}")
        send_message(recipient, "⚠️ שגיאה בגישה לקובץ הביטוח.")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        send_message(recipient, "⚠️ אירעה שגיאה בלתי צפויה.")
                        
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
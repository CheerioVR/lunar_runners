import requests
import random
import json
import os
import base64
from flask import Flask, jsonify, request, Response
from datetime import datetime, timedelta
import secrets as noncethingy5
import string as noncethingy6
import sqlite3
import random
import time
import hashlib
from threading import Thread
import secrets as noncethingy3
import string as Noncethingy3
Noncethingy1 = str
Noncethingy2 = int

class GameInfo:

    def __init__(self):
        self.TitleId: str = "AB44B"
        self.SecretKey: str = "QZ7OIEIZD3PKD6OOWAGJCKD6JFUIYGE8GS1FZEKAU7Y6PKOFEK"
        self.ApiKey: str = "OC|1241139049093485|e3a75b066553541ea8abf902e168e658"
        self.photon_webhook_url = "https://discord.com/api/webhooks/1541533975334486066/wFvZTcqkUbs6YeI8ICH1nyPE3e4U73qhV3zglzWVIr5NegW_rp_kAW1usrMKpoPzJ2vk"

    def get_auth_headers(self):
        return {"Content-Type": "application/json", "X-SecretKey": self.SecretKey}
        
    
    @staticmethod
    def PrivacyStateIDtoName(name):
        return {"VISIBLE": 0, "PUBLIC_ONLY": 1, "HIDDEN": 2}.get(name, -1)


settings = GameInfo()
app = Flask(__name__)
players_file = "players.json"
CODES_FILE = "codes.json"
VOTES_FILE = "votes.json"
QUESTS_FILE = 'quests.json'
USERS_FILE = 'users.json'

def return_function_json(data, funcname, funcparam={}):
    user_id = data["FunctionParameter"]["CallerEntityProfile"]["Lineage"][
        "TitlePlayerAccountId"]

    response = requests.post(
        url=
        f"https://{settings.TitleId}.playfabapi.com/Server/ExecuteCloudScript",
        json={
            "PlayFabId": user_id,
            "FunctionName": funcname,
            "FunctionParameter": funcparam
        },
        headers=settings.get_auth_headers())

    if response.status_code == 200:
        return jsonify(response.json().get("data").get(
            "FunctionResult")), response.status_code
    else:
        return jsonify({}), response.status_code


def get_is_nonce_valid(nonce, oculus_id):
    response = requests.post(
        url=
        f'https://graph.oculus.com/user_nonce_validate?nonce={nonce}&user_id={oculus_id}&access_token={settings.ApiKey}',
        url1=
        f'https://graph.oculus.com/user_nonce_validate?nonce={nonce}&user_id={oculus_id}&access_token={settings.ApiKey1}',
        headers={"content-type": "application/json"})
    return response.json().get("is_valid")

@app.route('/nonce', methods=['GET'])
def noncethingy_endpoint():
    try:
        value = Noncethingy3.generate()
        return jsonify({'Nonce': value}), 200
    except Exception as error:
        return jsonify({'Error': str(error)}), 500



def load_votes():
    try:
        with open(VOTES_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Return default polls if file doesn't exist
        return [
            {
                "pollId": 2,
                "question": "IS OPLY TAG ON APPLAB BEST GAME",
                "voteOptions": ["YES", "NO"],
                "voteCount": [100, 150],
                "predictionCount": [100, 150],
                "startTime": "2025-03-17T18:00:00",
                "endTime": "2025-03-24T17:00:00",
                "isActive": False
            },
            {
                "pollId": 3,
                "question": "IS OPLY TAG IS BEST GAME ON APPLAB?",
                "voteOptions": ["YES", "NO"],
                "voteCount": [0, 0],
                "predictionCount": [0, 0],
                "startTime": "2025-03-24T18:00:00",
                "endTime": "2025-04-27T17:00:00",
                "isActive": True
            }
        ]

def save_votes(polls):
    with open(VOTES_FILE, 'w') as f:
        json.dump(polls, f, indent=4)
        
def load_players_data():
    try:
        with open(players_file, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_players_data(players_data):
    with open(players_file, "w") as file:
        json.dump(players_data, file, indent=4)

def load_codes():
    with open(CODES_FILE, 'r') as f:
        return json.load(f)

def find_code(codes, code_id):
    for code in codes:
        if code["id"].upper() == code_id:
            return code
    return None
def grant_cosmetic_to_player(playfab_id, cosmetic_id):
    url = f"https://{settings.TitleId}.playfabapi.com/Admin/GrantItemsToUsers"
    
    payload = json.dumps({
        "ItemGrants": [
            {
                "PlayFabId": playfab_id,
                "ItemId": cosmetic_id,
                "CatalogVersion": "DLC",
                "Annotation": "Redeeming Code"
            }
        ],
        "CatalogVersion": "DLC"
    })
    
    headers = settings.get_auth_headers()
    
    print("Sending GrantItemsToUsers request")
    print("URL:", url)
    print("Payload:", payload)
    print("Headers:", headers)

    response = requests.request("POST", url, headers=headers, data=payload)
    
    print("Response:", response.status_code, response.text)
    return response




def authenticate_ticket(ticket, expected_id=None):
    try:
        # Send authentication request to PlayFab
        res = requests.post(
            f"https://{settings.TitleId}.playfabapi.com/Server/AuthenticateSessionTicket",
            json={"SessionTicket": ticket},
            headers=settings.get_auth_headers()
        )

        # If the request fails, return None
        if res.status_code != 200:
            print(f"Authentication failed with status code: {res.status_code}")
            return None
        
        # Extract the PlayFabId from the response
        user_id = res.json().get("data", {}).get("UserInfo", {}).get("PlayFabId")
        
        if not user_id:
            print("Failed to extract PlayFabId from response")
            return None

        # Check if the expected user_id matches the authenticated user
        if expected_id and user_id != expected_id:
            print(f"User ID mismatch: expected {expected_id}, got {user_id}")
            return None
        
        return user_id
    
    except requests.exceptions.RequestException as e:
        # Handle exceptions (e.g., connection errors, timeouts)
        print(f"Error during authentication: {str(e)}")
        return None

WEEKLY_CAP = 100
DAILY_RESET_HOUR = 0  # Midnight
WEEKLY_RESET_DAY = 0  # Monday

def load_data():
    with open(QUESTS_FILE, 'r') as f:
        quests = json.load(f)
    with open(USERS_FILE, 'r') as f:
        users = json.load(f)
    return quests, users

def save_data(quests, users):
    with open(QUESTS_FILE, 'w') as f:
        json.dump(quests, f, indent=2)
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

def get_current_periods():
    now = datetime.utcnow()
    
    # Daily period key (YYYY-MM-DD)
    daily_key = now.strftime("%Y-%m-%d")
    
    # Weekly period key (Monday of current week)
    weekly_start = now - timedelta(days=now.weekday())
    weekly_key = weekly_start.strftime("%Y-%m-%d")
    
    return daily_key, weekly_key

def get_or_create_user(users, playfab_id):
    if playfab_id not in users:
        users[playfab_id] = {
            'total_points': 0,
            'daily_points': {},
            'weekly_points': {},
            'unclaimed_points': 0
        }
    return users[playfab_id]





@app.route("/api/CheckForBadName", methods=["POST"])
def check_for_bad_name():
    # Log headers and raw body
    print("[Incoming Request] Headers:", dict(request.headers))
    print("[Incoming Request] Body:", request.get_data(as_text=True))

    data = request.get_json(silent=True) or {}
    rjson = data.get("FunctionArgument", {})  # Correct use

    name = (rjson.get("name") or "").upper().strip()
    print(f'Someone just entered {name} into the system.')

    playfab_id = data.get("CallerEntityProfile", {}).get("Lineage", {}).get("MasterPlayerAccountId")

    # Normal bad words
    bad_words = {
        "KKK", "PENIS", "NIGG", "NEG", "NIGA", "MONKEYSLAVE", "SLAVE", "FAG",
        "NAGGI", "TRANNY", "QUEER", "KYS", "DICK", "PUSSY", "VAGINA", "BIGBLACKCOCK",
        "DILDO", "HITLER", "KKX", "XKK", "NIGE", "NIG", "NI6", "PORN",
        "JEW", "JAXX", "SEX", "COCK", "CUM", "FUCK", "NIGGA", "NICKER", "NICKA",
        "NII", "@HERE", "NIGGER", "IHATENIGGERS", "@EVERYONE", "RACIST", "HAILHITLER"
    }

    offensive_patterns = [
        "FUCK CAM", "CAMRACIST", "ICAMTRUMP", "RACISTCAM",
        "CAM", "UACISTCAM", "FUCKCAM", "", 
        "RACNSTCAM", "CAM", "CAM", "CAM", 
        "CAM", "CAM"
    ]

    banned = False  # <-- Flag

    # First check offensive patterns
    for offensive_pattern in offensive_patterns:
        if offensive_pattern in name:
            if playfab_id:
                ban_user(playfab_id, name=name, reason="DEFAMATION DETECTED. CONTINUED USE WILL RESULT IN LEGAL ACTION")
                banned = false
            break

    # Only check bad words if NOT already banned
    if not banned:
        for bad_word in bad_words:
            if bad_word in name:
                if playfab_id:
                    ban_user(playfab_id, name=name, reason=f"BAD NAME. NAME: {name}")
                break
    

    embed = {
        "title": "GorillaComputer Entry",
        "color": 0xFF5733 if banned else 0x4CAF50,
        "fields": [
            {
                "name": "Entry",
                "value": name or "N/A",
                "inline": True
            },
            {
                "name": "PlayFab ID",
                "value": playfab_id or "Unknown",
                "inline": True
            },
            {
                "name": "Action Taken",
                "value": ban_reason if banned else "No ban",
                "inline": False
            }
        ]
    }

    try:
        requests.post(
            "",
            json={"embeds": [embed]},
            headers={"Content-Type": "application/json"}
        )
    except Exception as e:
        print(f"Failed to send Discord embed: {e}")

    # Always return success
    return jsonify({
        "result": 0,
        "banLength": -1
    })

def get_discord_id_from_playfab(playfab_id):
    db_path = "mongodb://localhost:27017"
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT discord_id FROM links WHERE playfab_id = ?", (playfab_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return row[0]
    except Exception as e:
        print(f"Database error: {e}")
    return None

DISCORD_BOT_TOKEN = "MTQwMTMyMjEzMDI2MzUwNzA1Nw.Gnr12q.m2WAeFAjNTcNzTSAK-tIfcqCZ0Zqk3G5PpUEW8"  # must have 'identify' scope
DISCORD_API_BASE = "https://discord.com/api/v10"

def get_discord_username(discord_id):
    try:
        headers = {
            "Authorization": f"Bot {DISCORD_BOT_TOKEN}"
        }
        response = requests.get(f"{DISCORD_API_BASE}/users/{discord_id}", headers=headers)
        if response.status_code == 200:
            user = response.json()
            return f"{user['username']}#{user['discriminator']}"  # or user['global_name'] for newer accounts
    except Exception as e:
        print(f"Error fetching Discord user: {e}")
    return None

@app.route("/re/api/SetPrivacyState", methods=["POST"])
@app.route("/api/SetPrivacyState", methods=["POST"])
def SetPrivacyState():
    rjson = request.get_json()
    playfab_id = rjson.get("PlayFabId", "")
    privacy_state = rjson.get("PrivacyState", "VISIBLE")
    playfab_ticket = rjson.get("PlayFabTicket", "")

    if not playfab_id or not playfab_ticket or settings.PrivacyStateIDtoName(privacy_state) == -1:
        return "", 400

    auth_session = requests.post(
        f"https://{settings.TitleId}.playfabapi.com/Server/AuthenticateSessionTicket",
        json={"SessionTicket": playfab_ticket},
        headers=settings.get_auth_headers()
    )

    if auth_session.status_code != 200 or auth_session.json()["data"]["UserInfo"]["PlayFabId"] != playfab_id:
        return "", 400

    requests.post(
        f"https://{settings.TitleId}.playfabapi.com/Server/UpdateUserInternalData",
        headers=settings.get_auth_headers(),
        json={"PlayFabId": playfab_id, "Data": {"PrivacyState": privacy_state}}
    )

    return jsonify({"statusCode": 200, "error": None}), 200


@app.route("/", methods=["POST", "GET"])
def main():
    return jsonify({
    
  "MOTD": "WELCOME TO C00L TAGGERS REBORN",
  "CreditsData": "[{\"Title\":\"DEV TEAM\",\"Entries\":[\"SIGMA\"]",
  "MuteThresholds": "{\"thresholds\":[{\"name\":\"low\",\"threshold\":20},{\"name\":\"high\",\"threshold\":50}]}",
  "VStumpFeaturedMapPoster": "4641648",
  "VStumpFeaturedMapPosterText": "\"https://discord.gg/XzwSY9dU\"",
  "latestVersionKey": "\"CLAWG\"",
  "playFabKey": "\"2023.11.30\"",
  "UseLegacyIAP": "false",
  "Versions": "{\"CreditsData\":10,\"MOTD_1.1.38\":8,\"MOTD_1.1.39\":7,\"bundleData\":1,\"BundleLargeSign_1.1.40\":1,\"BundleBoardSign_1.1.40\":0,\"BundleKioskSign_1.1.40\":1,\"BundleKioskButton_1.1.40\":0,\"SeasonalStoreBoardSign_1.1.40\":0,\"MOTD_1.1.40\":0,\"MOTD_1.1.42\":2,\"MOTD_1.1.43\":0,\"SeasonalStoreBoardSign_1.1.43\":0,\"MOTD_1.1.45\":7,\"MOTD_1.1.46\":1}",
  "COC": "Owners: Risk, Camify CO owner: Vibes Mod: Olivia, Neb, Bagel, enforced Forest Guide: Ri, Blu, ketchup, MallcopGT",
  "LatestPrivacyPolicyVersion": "\"2024.09.20\"",
  "LatestTOSVersion": "\"2024.09.20\"",
  "PrivacyPolicy_2024.03.07": "\"PRIVACY POLICY AND NOTICE AT COLLECTION\\n\\nEffective Date: March 07, 2024\\n \\nAnother Axiom Inc., a Delaware corporation (\\u201CAnother Axiom\\u201D, \\u201Cwe,\\u201D \\u201Cus,\\u201D \\u201Cour,\\u201D and their derivatives) provides Gorilla Tag\\u2122 and other video games, including any playtest program (collectively, our \\u201CGames\\u201D), websites, including https://www.gorillatagvr.com/ and https://www.anotheraxiom.com/ and their respective subdomains (collectively, our \\u201CWebsites\\u201D), and other online services (with our Games and Websites, collectively, our \\u201CServices\\u201D).\\n\\n    1. What does this Notice cover?  \\n\\nThis Privacy Policy and Notice at Collection (this \\u201CNotice\\u201D) sets forth how we collect, use, protect, store, disclose, and otherwise process your Personal Information (defined below). This Notice does NOT apply to information you provide to any third party or is collected by any third party (except as otherwise provided below). \\n\\nBy using our Services, you are confirming that you understand English well enough to understand this Notice. Should you have questions about this Notice, please contact us by completing a support ticket at https://support.gorillatagvr.com/ or emailing us at support@anotheraxiom.com, so we can clarify and address your questions.\\n\\n    2. How do we process Children\\u2019s Personal Information?  \\n\\nIn accordance with the policies of Meta\\u00AE, our Games are available to Quest Pro, Quest 2, Quest 3, and next-gen headset users at least 10 years of age, and Quest 1 and Rift users at least 13 years of age. In accordance with the policies of Valve\\u00AE, our Games are available to Steam users at least 13 years of age. \\n\\nIf you become aware that an underage user has provided us with Personal Information, please contact us by completing a support ticket at https://support.gorillatagvr.com/ or emailing us at support@anotheraxiom.com, so we may delete their Personal Information. \\n\\nParent-Managed Accounts for Oculus Users 10-12 Years of Age\\n\\nIf you self-identify or are identified by Meta\\u00AE as being between 10-12 years of age (each, a \\u201CPreteen User\\u201D), your gameplay experience will automatically be restricted, unless your parent or legal guardian permits otherwise. For example, Preteen Users are automatically restricted from communicating with or otherwise making their Personal Information publicly available to other users of our Games. Preteen Users will only be able to use monkey sounds to communicate with other users, will be assigned randomly-generated name badges, will be prohibited from joining private servers using room codes, and will be restricted from purchasing in-Game items.  \\n\\nWe do not administer Parent-Managed Accounts for Preteen Users. For more information on creating and managing an account for a Preteen User, please review Meta\\u2019s education hub at https://www.meta.com/quest/safety-center/parental-supervision/. \\n\\n    3. What categories of Personal Information do we collect?\\n\\nWe may collect different types of information from you depending on how you use our Services, including Personal Information. \\u201CPersonal Information\\u201D means information that relates to an identified or identifiable natural person. The categories of Personal Information we may collect are listed below. Certain types of Personal Information may fall under more than one category. \\n\\nWe do not knowingly or intentionally process any sensitive Personal Information.\\n\\nWe may also collect information that does not generally identify you but may become associated with your account. We may use information that does not identify you for any permissible business or operational purpose under applicable law.\\n\\nGames\\n\\nWhen you play our Games, we may process your: \\n\\n    \\u2022 Identifiers: usernames (Game username and Steam username), email address, unique or online ID (such as a third party ID from PlayStation, Oculus, Viveport, or PlayFab), Internet Protocol address, and hardware ID and hardware information; \\n    \\u2022 Geolocation: country; \\n    \\u2022 Commercial information: purchase history of in-game items and DLCs; \\n    \\u2022 Internet or other similar network activity: gameplay information, Game settings, and user preferences and language; \\n    \\u2022 Audio, electronic, visual, thermal, olfactory, or similar information: movement data (tracking your hands and head) and voice data; and \\n    \\u2022 Other: Oculus age category (i.e., child, teen, or adult) and information from the content that you send to us directly by submitting a support ticket.  \\n\\nWebsites\\n\\nWhen you visit our Websites, we may process your: \\n\\n    \\u2022 Identifiers: first and last name, Oculus ID, and email address;  \\n    \\u2022 Internet or other similar network activity: interaction with our Websites; \\n    \\u2022 Personal Information categories listed in the California Customer Records statute (Cal. Civ. Code \\u00A7 1798.80(e)): first and last name; and \\n    \\u2022 Other: information from the content that you send to us directly by completing the \\u201CContact Us\\u201D form on our Websites or by submitting a support ticket.\\n\\nGame Discord Channel\\n\\nWhen you visit our Game Discord Channel, we may process your: \\n\\n    \\u2022 Identifiers: Discord username, Discord user ID, and email address; and \\n    \\u2022 Other: information from the content that you share publicly on Discord.\\n\\n    4. From what sources do we collect Personal Information?\\n\\nDirectly From You\\n\\nWe may collect your Personal Information when you provide it to us directly, including the examples below.\\n\\n    \\u2022 When you create an account for our Games, we may collect your username and Internet Protocol address. \\n    \\u2022 When you play our Games, we may collect your movement data (tracking your hands and head) and voice data. \\n    \\u2022 When you contact us through the \\u201CContact Us\\u201D form on our Websites, we may collect your first and last name, email address, and records and copies of your correspondence. \\n    \\u2022 When you submit a support ticket, we may collect your email address, and records and copies of your correspondence. \\n    \\u2022 When you respond to a survey or questionnaire, we may collect the information you provide.\\n\\nAutomatically From You\\n\\nWe may collect your Personal Information automatically as you use our Services. For example, we may collect your Personal Information as you interact with our Websites or as you play our Games. For more information about our and third parties\\u2019 use of cookies and other automatic data collection technologies and certain choices we offer to you with respect to them, please see Section 5 below.\\n\\nFrom Third Parties\\n\\nWe may receive your Personal Information from or through third parties that help us provide or facilitate your access to our Services. For example, we may receive your Personal Information from the below third parties. \\n\\n    \\u2022 Game publishers such as Sony\\u00AE, Meta\\u00AE, and Valve\\u00AE: When you play our Games, we may receive your Oculus age category (i.e., child, teen, or adult), PlayStation account, online, and NP IDs, email address, gameplay information, Game settings, and user preferences and language, and when you purchase in-Game items or DLCs, we may receive your purchase history. By way of another example, when you submit a support ticket, we may receive your Oculus ID. \\n\\n    \\u2022 Backend providers such as Microsoft Azure PlayFab\\u00AE or Unity\\u00AE: When you play our Games, we may receive your PlayFab ID (and associated Oculus ID, Steam username, or Viveport ID). When you are banned from our Games, we may receive your hardware ID.\\n\\n    \\u2022 Social media platforms such as Discord\\u00AE: When you join our Game Discord channel, we may receive your Discord username, user ID, and the information that you share publicly on our Discord channel. When you appeal against being banned from our Game Discord channel, we may receive your email address. \\n\\nWe abide by this Notice when we use Personal Information provided to us by third parties. However, we may not control the Personal Information that third parties collect or how they use that Personal Information. You should review the third parties\\u2019 privacy policies for more information about how they collect, use, and share the Personal Information they obtain and use. \\n\\n    5. How do we and third parties use cookies and other automatic data collection technologies? \\n\\nCookies are small pieces of text sent to your browser by a website you visit. They help that website remember information about your visit, which can both make it easier to visit the site again and make the site more useful to you. \\n\\nOur Cookies and Other Automatic Data Collection Technologies \\n\\nWe may use cookies and other automatic data collection technologies on our Services to collect Personal Information, for example, regarding your interaction with our Websites. By way of another example, when you play our Games, we may automatically collect your Internet Protocol address, gameplay information, and user preferences.\\n\\u00A0\\nThird Party Cookies and Other Automatic Data Collection Technologies \\n\\nCookies and other automatic data collection technologies on our Services may come from third parties as listed below. These cookies and other automatic data collection technologies improve your experience by helping us better tailor our Services to you. \\n\\n    \\u2022 Google Analytics\\u00AE and YouTube\\u00AE: Google Analytics is a web analysis service and YouTube is a video sharing and social media platform of Google Inc., 1600 Amphitheatre Parkway, Mountain View, CA 94043, United States. The Personal Information collected by Google in connection with your use of our Websites is transmitted to a server of Google in the United States, where it is stored and analyzed. Google\\u2019s collection and use of Personal Information is subject to Google's privacy policy: www.google.com/policies/privacy/partners/.\\n\\nChoices about Cookies\\n\\nYou may set your browser to refuse all or some browser cookies or to alert you when cookies are being sent (for Google: https://tools.google.com/dlpage/gaoptout). Please note that, if you disable or refuse cookies or other automatic data collection technologies, some aspects of our Services may be inaccessible or not function properly.\\n\\n    6. For what purposes do we collect your Personal Information?\\n\\nWe may collect your Personal Information for the below purposes. \\n\\n    \\u2022 To provide or improve our Services: We may use your Personal Information to process your requests to access our Services and certain of their features and to generally present and improve our Services. For example, we may use your Personal Information to create your account for our Games, to grant you access to our Games, to fulfill in-Game purchases, and to improve our Games or Websites. \\n\\n    \\u2022 To administer our Services: We may use your Personal Information for any lawful business or operational purpose in connection with administering our Services. For example, we may use your Personal Information to respond to support tickets or business or media inquiries sent by you.\\n\\n    \\u2022 To market our Services: We may use your Personal Information to market our Services to you. For example, with your prior consent, we may share news and updates about our Services through our Game Discord channel.\\n\\n    \\u2022 In furtherance of legal and safety objectives: We may access, use, and share with others your Personal Information for purposes of safety and other matters in the public interest. We may also provide access to your Personal Information to cooperate with official investigations or legal proceedings (e.g., in response to subpoenas, search warrants, court orders, or other legal processes). We may also provide access to your Personal Information to protect our rights and property and those of our agents, users, and others, including to enforce our agreements, policies, and our Terms of Service. For example, we may use your Personal Information to respond to inappropriate or reported conduct in-Game, to enforce user bans for our Games and Game Discord channel, and for moderation and enforcement of Discord channel policies.\\n\\n    \\u2022 In connection with a sale or other transfer of our business: In the event all or some of our assets are sold, assigned, or transferred to or acquired by another company due to a sale, merger, divestiture, restructuring, reorganization, dissolution, financing, bankruptcy, or otherwise, your Personal Information may be among the transferred assets.\\n\\n    \\u2022 As we may describe to you when collecting your Personal Information: There may be other situations when we collect your Personal Information and simultaneously describe the purpose for that collection. \\n\\nLawful Basis \\n\\nWe only collect, use, or store your Personal Information for a lawful basis such as: \\n\\n    \\u2022 you voluntarily provide it to us with your specific, informed, and unambiguous consent (for example, through our Game Discord channel); \\n    \\u2022 it is necessary to provide you with a Service that you have requested (for example, providing you access to our Games);\\n    \\u2022 we have a legitimate business interest that is not outweighed by your privacy rights (for example, to ban users); or  \\n    \\u2022 it is necessary to protect your vital interests or the vital interests of others (for example, where necessary to protect the safety of one of our users or someone else).\\n\\n    7. In what situations do we disclose your Personal Information?\\n\\nWe may disclose your Personal Information to a third party, such as a service provider or contractor for a business or operational purpose, or with your consent. When we disclose Personal Information for a business or operational purpose, we enter into a contract with the service provider or contractor that describes the purpose and requires the service provider or contractor to both keep that Personal Information confidential and not use it for any purpose except performing the contract. These service providers and contractors include our:\\n\\n    \\u2022 backend platform service providers such as for error and crash reporting;\\n    \\u2022 email service providers; \\n    \\u2022 game analytics providers; and \\n    \\u2022 customer support representatives and providers.\\n\\nWe may also disclose your Personal Information:\\n\\n    \\u2022 to our subsidiaries and affiliates;\\n    \\u2022 to our lawyers, consultants, accountants, business advisors, and similar third parties who owe us duties of confidentiality;\\n    \\u2022 to a buyer or other successor in the event of a sale, merger, divestiture, restructuring, reorganization, dissolution, or other transfer of some or all of our assets, whether as a going concern or as part of bankruptcy, liquidation, or similar proceeding, in which Personal Information retained by us pertaining to the users of our Services is among the assets transferred;\\n    \\u2022 to comply with any court order, law, or legal process, such as responding to a government or regulatory request;\\n    \\u2022 to enforce any contract we may have in effect with you; \\n    \\u2022 if we believe disclosure is necessary or appropriate to protect the rights, property, or safety of us, our users, or others; and \\n    \\u2022 if you have consented to such a disclosure. \\n\\nWe do not sell, rent, or share your Personal Information for cross contextual behavioral or targeted advertising, automated decision-making, or profiling purposes.\\n\\n    8. How is my Personal Information protected?\\n\\nOur Retention, Purpose Limitation, and Security Policies\\n\\nWe protect your Personal Information through a combination of collection, security, and retention policies.\\n\\n    \\u2022 Limited retention: We retain each category of Personal Information only for as long as necessary to fulfill the purposes for which the Personal Information was provided to us or, if longer, to comply with any legal obligations, to resolve disputes, and to enforce contracts. For example, we may retain Personal Information collected about you to prevent repeated violations or suspected violations of our Terms of Service if your account has been banned or your access to our Services has been disabled for any reason. To determine the appropriate retention period for Personal Information, we consider the amount, nature, and sensitivity of the Personal Information, the potential risk of harm from unauthorized use or disclosure of the Personal Information, the purposes for which we process the Personal Information and whether we can achieve those purposes through other means, and the applicable legal requirements. For example, subject to the foregoing considerations, it is our policy to delete your Personal Information if we stop operating our Games or the feature through which the Personal Information was acquired.\\n\\n    \\u2022 Purpose limitation: We will use your Personal Information only for our Services you choose to access and for the purposes notified to you, unless we otherwise obtain your consent. We limit the collection of Personal Information to what is adequate, relevant, and reasonably necessary for those purposes.  \\n\\n    \\u2022 Security measures: We use reasonable security measures to ensure a level of security appropriate to the volume and nature of Personal Information processed and risk involved, considering the size, scope, and type of our business, and have implemented contractual, technical, administrative, and physical security measures designed to protect your Personal Information from unauthorized access, disclosure, use, and modification. As part of our privacy compliance processes, we review these security procedures on an ongoing basis to consider new technology and methods as necessary. However, please understand that our implementation of security measures as described in this Notice does not guarantee the security of your Personal Information. In the event of a security breach, we will notify the proper regulatory authorities and any affected users of the breach within 72 hours after we become aware of the breach to the extent required by applicable law.\\n\\nYour Practices and Activities\\n\\nYour practices and activities are likewise very important for the protection of your Personal Information. You should take certain steps to help protect your Personal Information, such as being mindful of what you share publicly in our Games or Game Discord channel, including the below. \\n\\n    \\u2022 Do not use your real name when selecting a username.\\n\\n    \\u2022 Do not share your real name or anything private about yourself or anyone else with other users of any Game or Game Discord channel.\\n\\n    \\u2022 Do not pick a password that is easy to guess, and do not share your password.  \\n\\nPlease remember that we have no control over what other users do with the content of your communications and no responsibility or obligation regarding other users.\\n\\n    9. How do we treat Personal Information transferred to the United States?\\n\\nPlace of Business\\n\\nWe may store or process your Personal Information outside of the country where we collect the information or the country in which you reside. Our primary place of business is in the United States. You should understand that we may transfer some or all of your Personal Information to the United States to carry out certain operational and processing needs as described in this Notice.\\n\\nTransfer Mechanisms\\n\\nWhen transferring Personal Information out of foreign countries, we implement technical, organizational, and physical safeguards to protect your Personal Information. We use European Commission approved standard contractual clauses and implement related measures where required by applicable law. Please contact us if you have questions related to the relevant transfer mechanism for your Personal Information.\\n\\n    10. What rights do you have to your Personal Information?\\n\\nRight to Access, Correct, Delete, or Restrict Processing\\n\\nSubject to any limitations and exceptions under applicable law, you have the right to request access to your Personal Information and exercise the below rights.  \\n\\n    \\u2022 You have the right to correct or update certain types of Personal Information. In many cases, you can review or update your account information by accessing your account online. \\n\\n    \\u2022 You have the right to request deletion of your Personal Information. If you choose to have your Personal Information removed from our Services, we will carry out your request within 30 days of account verification, subject to extension, and we will only retain minimal Personal Information to document your request and the actions we took to carry out your request. \\n\\n    \\u2022 You have the right to restrict certain processing of your Personal Information and the right to object to some types of processing of your Personal Information.  \\n\\n    \\u2022 You have the right to withdraw your consent at any time. \\n\\n    \\u2022 You have the right to lodge a complaint regarding our collection, storage, or processing of your Personal Information with a data protection supervisory authority in the country where you live or work.\\n\\nWe will comply with your requests in accordance with, and subject to, applicable law. For example, we are not required to delete your Personal Information if we have an overriding legitimate ground for retaining that information, such as to prevent fraud. Please note that we are legally prohibited from carrying out requested actions in some instances, including (1) when we are unable to confirm your identity or (2) where doing so would adversely affect the rights or freedoms of others.  Further, we are not required to carry out a requested action in some instances, including where the request is considered excessive.\\n\\nWe are Here to Help\\n\\nPlease complete a support ticket at https://support.gorillatagvr.com/ or email us at support@anotheraxiom.com with the subject line \\u201CPrivacy Request\\u201D if you would like to exercise any of the rights described above or if you have questions regarding your rights. \\n\\n    11. \\tAdditional Notice for California, Colorado, Connecticut, Utah, and Virginia Residents \\n\\nCalifornia Online Privacy Protection Act\\n\\nThe following applies to California residents: \\n\\n    \\u2022 We do not track users of our Services over time and across third party websites or online services and therefore do not respond to Do Not Track signals. We are not aware of any third party that tracks users of our Services over time and across third party websites or online services. Please note that Do Not Track is a different privacy mechanism than the Global Privacy Control, a legally recognized browser-based control that indicates whether you would like to opt out of the processing of your Personal Information for certain purposes.\\n\\nCalifornia Shine the Light Law\\n\\nThe following applies to California residents:\\n\\n    \\u2022 California residents may request information from us concerning any disclosures of Personal Information we may have made in the prior calendar year to third parties for direct marketing purposes. If you are a California resident and you wish to request information about our compliance with this law or our privacy practices, please contact us by completing a support ticket at https://support.gorillatagvr.com/  or emailing us at support@anotheraxiom.com. \\n\\nState Privacy Laws \\n\\nThe following applies to California, Colorado, Connecticut, Utah, and Virginia residents (in the event of a conflict between this Section 11 and any other section in this Notice, this Section 11 controls): \\n\\n    \\u2022 Right to Know and Access: You have the right to request that we disclose certain information to you about our collection and use of your Personal Information. Once we receive and confirm your verifiable consumer request, we will disclose to you the following, to the extent retained by us:\\n\\n        \\u25E6 the categories of Personal Information we collected about you; \\n        \\u25E6 the categories of sources for the Personal Information we collected about you; \\n        \\u25E6 our business or commercial purpose for collecting, selling, or sharing that Personal Information; \\n        \\u25E6 the categories of third parties with whom we disclose that Personal Information;\\n        \\u25E6 the specific pieces of Personal Information we collected about you (also known as a data portability request); and \\n        \\u25E6 if we sold or shared your Personal Information, two separate lists disclosing (1) sales, identifying the Personal Information categories that each category of recipient purchased, and (2) disclosures for a business or operational purpose, identifying the Personal Information categories that each category of recipient obtained.\\n\\n    \\u2022 Right to Deletion: You have the right to request that we delete any of your Personal Information that we collected from you and retained, subject to certain exceptions. Once we receive and confirm your verifiable consumer request, we will delete (and direct our service providers and contractors to delete) your Personal Information from our records, unless an exception under applicable law applies. We may deny your deletion request if retaining the information is necessary for us or our service providers or contractors to: \\n\\n        \\u25E6 complete the transaction for which we collected the Personal Information, fulfill the terms of a written warranty or product recall conducted in accordance with federal law, provide our Services that you requested, take actions reasonably anticipated within the context of our ongoing business relationship with you, or otherwise perform our contract with you; \\n        \\u25E6 help to ensure the security and integrity of our Services to the extent the use of your Personal Information is reasonably necessary and proportionate to those purposes; \\n        \\u25E6 debug our Services to identify and repair errors that impair existing intended functionality; \\n        \\u25E6 exercise free speech, ensure the right of another user to exercise their free speech rights, or exercise another right provided for by law; \\n        \\u25E6 comply with the California Electronic Communications Privacy Act; \\n        \\u25E6 engage in public or peer-reviewed scientific, historical, or statistical research in the public interest that adheres to all other applicable ethics and privacy laws, when the Personal Information\\u2019s deletion may likely render impossible or seriously impair the research\\u2019s achievement, if you previously provided consent; \\n        \\u25E6 enable solely internal uses that are reasonably aligned with user expectations based on your relationship with us and compatible with the context in which you provided the Personal Information; or \\n        \\u25E6 comply with a legal obligation.\\n\\n    \\u2022 Right to Correction: You have the right to request that we correct inaccurate Personal Information. Once we receive and confirm your verifiable consumer request, we will use commercially reasonable efforts to correct the inaccurate Personal Information, taking into account to the nature of the Personal Information and the purposes of the processing of the Personal Information.\\n\\nNo Discrimination \\n\\nWe will not discriminate against you for exercising any of your privacy rights under applicable law. Unless permitted by applicable law, we will not:\\n\\n    \\u2022 deny you our Services; \\n    \\u2022 charge you different prices or rates for our Services, including through granting discounts or other benefits, or imposing penalties; \\n    \\u2022 provide you a different level or quality of our Services; or \\n    \\u2022 suggest that you may receive a different price or rate for our Services or a different level or quality of our Services.\\n\\nVerifiable Consumer Requests \\n\\nTo exercise your rights described above, please complete a support ticket at https://support.gorillatagvr.com/  or email us at support@anotheraxiom.com with the subject line \\u201CState Privacy Rights.\\u201D Only you, or someone legally authorized to act on your behalf, may make a verifiable consumer request related to your Personal Information. The verifiable consumer request must:\\n\\n    \\u2022 provide sufficient information that allows us to reasonably verify you are the person about whom we collected Personal Information or an authorized representative; and \\n    \\u2022 describe your request with sufficient detail that allows us to properly understand, evaluate, and respond to it.\\n\\nWe cannot respond to your request or provide you with Personal Information if we cannot verify your identity or authority to make the request and confirm that the Personal Information relates to you. We will only use Personal Information provided in a verifiable consumer request to verify your identity or authority to make the request.\\n\\nResponse Timing and Format \\n\\nWe endeavor to respond to a verifiable consumer request within 45 days of its receipt. If we require more time, we will inform you of the reason and extension period in writing. If you have an account with us, we will deliver our written response to that account. If you do not have an account with us, we will deliver our written response by mail or electronically, at your option.\\n\\nAny disclosures we provide will only cover the 12-month period preceding the receipt of verifiable consumer request, unless you request a longer period of time for Personal Information we collected about you after January 1, 2022. The response we provide will also explain the reasons we cannot comply with a request, if applicable. \\n\\nTo appeal a decision regarding your verifiable consumer request, please submit your appeal using one of the two methods above. Your appeal should include an explanation of the reason you disagree with our decision. Within 60 days of receipt of an appeal, we will inform you in writing of any action taken or not taken in response to the appeal, including a written explanation of the reasons for the decisions.\\n\\nFor data portability requests, we will select a format to provide your Personal Information that is readily useable, easy-to-understand, and should allow you to transmit the information from one entity to another entity without hindrance. \\n\\nWe do not charge a fee to process or respond to your verifiable consumer request unless it is excessive, repetitive, or manifestly unfounded. If we determine that the request warrants a fee, we will tell you why we made that decision and provide you with a cost estimate before completing your request.\\n\\n    12. How will we notify you of changes to this Notice?\\n\\nWe reserve the right to change this Notice from time to time consistent with applicable law. If we make changes to this Notice, we will notify you by revising the date at the top of this Notice and provide you with additional notice such as an in-Game notice or email notification.\\n\\n    13. How can you contact us?\\n\\nIf you have questions, you may complete a support ticket at https://support.gorillatagvr.com/ or email us at support@anotheraxiom.com. \\n\\nIf you are a law enforcement agency, please email us at support@anotheraxiom.com with your request for Personal Information with the subject line \\u201CLaw Enforcement Request.\\u201D\"",
  "BundleData": "{\"Items\":[{\"isActive\":false,\"skuName\":\"2024_pumpkin_patch_pack\",\"shinyRocks\":0,\"playFabItemName\":\"LSABS.\",\"majorVersion\":1,\"minorVersion\":1,\"minorVersion2\":90,\"displayName\":\"Pumpkin Patch Pack\"},{\"isActive\":false,\"skuName\":\"2024_monkes_wild_pack\",\"shinyRocks\":10000,\"playFabItemName\":\"LSABR.\",\"majorVersion\":1,\"minorVersion\":1,\"minorVersion2\":89,\"displayName\":\"Monkes Wild Pack\"},{\"isActive\":false,\"skuName\":\"CLIMBSTOPPERSBUN\",\"shinyRocks\":10000,\"playFabItemName\":\"CLIMBSTOPPERSBUN\",\"majorVersion\":1,\"minorVersion\":1,\"minorVersion2\":0,\"displayName\":\"CLIMB STOPPERS BUNDLE\"},{\"isActive\":false,\"skuName\":\"GLAMROCKERBUNDLE\",\"shinyRocks\":10000,\"playFabItemName\":\"GLAMROCKERBUNDLE\",\"majorVersion\":1,\"minorVersion\":1,\"minorVersion2\":0,\"displayName\":\"GLAM ROCKER BUNDLE\"},{\"isActive\":false,\"skuName\":\"2024_cyber_monke_pack\",\"shinyRocks\":10000,\"playFabItemName\":\"LSABP.\",\"majorVersion\":1,\"minorVersion\":1,\"minorVersion2\":87,\"displayName\":\"Cyber Monke Pack\"},{\"isActive\":false,\"skuName\":\"2024_splash_dash_pack\",\"shinyRocks\":10000,\"playFabItemName\":\"LSABO.\",\"majorVersion\":1,\"minorVersion\":1,\"minorVersion2\":85,\"displayName\":\"Splash and Dash Pack\"},{\"isActive\":false,\"skuName\":\"2024_shiny_rock_special\",\"shinyRocks\":2200,\"playFabItemName\":\"LSABN.\",\"majorVersion\":1,\"minorVersion\":1,\"minorVersion2\":83,\"displayName\":\"Shiny Rock Special\"},{\"isActive\":false,\"skuName\":\"2024_climb_stoppers_pack\",\"shinyRocks\":10000,\"playFabItemName\":\"LSABM.\",\"majorVersion\":1,\"minorVersion\":1,\"minorVersion2\":82},{\"isActive\":true,\"skuName\":\"2024_glam_rocker_pack\",\"shinyRocks\":10000,\"playFabItemName\":\"LSABL.\",\"majorVersion\":1,\"minorVersion\":1,\"minorVersion2\":80},{\"isActive\":false,\"skuName\":\"2024_monke_monk_pack\",\"shinyRocks\":10000,\"playFabItemName\":\"LSABK.\",\"majorVersion\":1,\"minorVersion\":1,\"minorVersion2\":78},{\"isActive\":false,\"skuName\":\"2024_leaf_ninja_pack\",\"shinyRocks\":10000,\"playFabItemName\":\"LSABJ.\",\"majorVersion\":1,\"minorVersion\":1,\"minorVersion2\":76},{\"isActive\":false,\"skuName\":\"2024_gt_monke_plush\",\"shinyRocks\":0,\"playFabItemName\":\"LSABI.\",\"majorVersion\":1,\"minorVersion\":1,\"minorVersion2\":73},{\"isActive\":false,\"skuName\":\"2024_beekeeper_pack\",\"shinyRocks\":10000,\"playFabItemName\":\"LSABH.\",\"majorVersion\":1,\"minorVersion\":1,\"minorVersion2\":73},{\"isActive\":false,\"skuName\":\"2024_i_lava_you_pack\",\"shinyRocks\":10000,\"playFabItemName\":\"LSABG.\",\"majorVersion\":1,\"minorVersion\":1,\"minorVersion2\":71},{\"isActive\":false,\"skuName\":\"2024_mad_scientist_pack\",\"shinyRocks\":10000,\"playFabItemName\":\"LSABF.\",\"majorVersion\":1,\"minorVersion\":1,\"minorVersion2\":69},{\"isActive\":false,\"skuName\":\"2023_holiday_fir_pack\",\"shinyRocks\":10000,\"playFabItemName\":\"LSABE.\",\"majorVersion\":1,\"minorVersion\":1,\"minorVersion2\":63},{\"isActive\":false,\"skuName\":\"2023_spider_monke_bundle\",\"shinyRocks\":10000,\"playFabItemName\":\"LSABD.\",\"majorVersion\":1,\"minorVersion\":1,\"minorVersion2\":59},{\"isActive\":false,\"skuName\":\"2023_caves_bundle\",\"shinyRocks\":10000,\"playFabItemName\":\"LSABC.\",\"majorVersion\":1,\"minorVersion\":1,\"minorVersion2\":54},{\"isActive\":false,\"skuName\":\"2023_summer_splash_bundle\",\"shinyRocks\":10000,\"playFabItemName\":\"LSABA.\",\"majorVersion\":1,\"minorVersion\":1,\"minorVersion2\":46},{\"isActive\":false,\"skuName\":\"2023_march_pot_o_gold\",\"shinyRocks\":5000,\"playFabItemName\":\"LSAAU.\",\"majorVersion\":1,\"minorVersion\":1,\"minorVersion2\":39},{\"skuName\":\"2023_sweet_heart_bundle\",\"playFabItemName\":\"LSAAS.\",\"shinyRocks\":0,\"isActive\":false},{\"skuName\":\"2022_launch_bundle\",\"playFabItemName\":\"LSAAP2.\",\"shinyRocks\":10000,\"isActive\":false},{\"skuName\":\"early_access_supporter_pack\",\"playFabItemName\":\"Early Access Supporter Pack\",\"shinyRocks\":0,\"isActive\":false}]}",
  "BundleBoardSign": "\"THE SPLASH N DASH PACK WITH 10,000 SHINY ROCKS IN THIS LIMITED TIME DLC!\"",
  "BundleKioskButton": "\"THE ... (43 KB left)

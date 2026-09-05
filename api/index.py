from flask import Flask, request, jsonify
import hashlib
import uuid


TitleId = "1DEFB"
DeveloperSecretKey = "PJXPUDS6GKBYY1ZAKHPAG8YZWOURXJ6I77F4M3JGSDQ1MIBGJ6"
PHOTON_WEBHOOK_URL = "https://1DEFB.playfablogic.com/webhook/1/prod/ZZFBBCDGWYSX97AQHZY3FRGBHJH8F1E575ECFUAD1SETEC5OB4"
ApiKey = "OC|9511338942260576|c22abe803b219e35739f634d02556f08"

app = Flask(__name__)

def authkey() -> dict:
    return {"content-type": "application/json", "X-SecretKey": DeveloperSecretKey}

@app.route("/", methods=["POST", "GET"])
def retard():
    return "blabla"

@app.route("/api/photon", methods=["POST"])
def photonauth():
    data = request.get_json()

    playfab_id = data.get("PlayFabId")
    org_scoped_id = data.get("OrgScopedId")
    custom_id = data.get("CustomID")
    platform = data.get("Platform")
    nonce = data.get("Nonce")
    user_id = data.get("UserId")
    master_player = data.get("Master")
    gorilla_tagger = data.get("GorillaTagger")
    cosmetics_in_room = data.get("CosmeticsInRoom")
    shared_group_data = data.get("SharedGroupData")
    update_cosmetics = data.get("UpdatePlayerCosmetics")
    master_client = data.get("MasterClient")
    item_ids = data.get("ItemIds")
    player_count = data.get("PlayerCount")
    cosmetic_auth_v2 = data.get("CosmeticAuthenticationV2")
    rpcs = data.get("RPCS")
    broadcast_room = data.get("BroadcastMyRoomV2")
    dlc_ownership = data.get("DLCOwnerShipV2")
    currency = data.get("GorillaCorpCurrencyV1")
    dead_monke = data.get("DeadMonke")
    ghost_counter = data.get("GhostCounter")
    dirty_cosmetic_spawner = data.get("DirtyCosmeticSpawnnerV2")
    room_joined = data.get("RoomJoined")
    virtual_stump = data.get("VirtualStump")
    player_room_count = data.get("PlayerRoomCount")
    app_version = data.get("AppVersion")
    app_id = data.get("AppId")
    tagged_distance = data.get("TaggedDistance")
    tagged_client = data.get("TaggedClient")
    oculus_id = data.get("OCULUSId")
    title_id = data.get("TitleId")
    if nonce is None:
        return jsonify({'Error': 'Bad request', 'Message': 'Not Authenticated!'}), 304
    if title_id and TitleId != 'TItleID RIGHT HERE':                                                      #aye, look at this line!
        return jsonify({'Error': 'Bad request', 'Message': 'Invalid titleid!'}), 403
    if platform != 'Quest':
        return jsonify({'Error': 'Bad request', 'Message': 'Invalid platform!'}), 403

    webhook_payload = {
        "username": "PhotonAuthBot",
        "embeds": [
            {
                "title": "Photon Auth Event",
                "color": 0x00ff99,
                "fields": [
                    {"name": "UserId", "value": user_id or "N/A", "inline": True},
                    {"name": "Platform", "value": platform or "Unknown", "inline": True},
                    {"name": "CustomId", "value": custom_id or "N/A", "inline": True},
                    {"name": "PlayFabId", "value": playfab_id or "N/A", "inline": True},
                    {"name": "OrgScopedID", "value": org_scoped_id or "N/A", "inline": False},
                    {"name": "AppId", "value": app_id or "Unknown", "inline": True},
                    {"name": "AppVersion", "value": app_version or "Unknown", "inline": True},
                    {"name": "Nonce", "value": nonce or "Missing", "inline": False}
                ],
                "footer": {"text": "Photon Authentication Event"}
            }
        ]
    }

    try:
        requests.post(PHOTON_WEBHOOK_URL, json=webhook_payload)
    except Exception as e:
        print(f"[WEBHOOK ERROR] {e}")

    return jsonify({
        "ResultCode": 1,
        "StatusCode": 200,
        "Message": "authed with photon",
        "Result": 0,
        "UserId": user_id,
        "AppId": app_id,
        "AppVersion": app_version,
        "Ticket": ticket,
        "Token": token,
        "Nonce": nonce,
        "Platform": platform,
        "Username": username,
        "PlayerRoomCount": player_room_count,
        "GorillaTagger": gorilla_tagger,
        "CosmeticAuthentication": cosmetic_auth_v2,
        "CosmeticsInRoom": cosmetics_in_room,
        "UpdatePlayerCosmetics": update_cosmetics,
        "DLCOwnerShip": dlc_ownership,
        "Currency": currency,
        "RoomJoined": room_joined,
        "VirtualStump": virtual_stump,
        "DeadMonke": dead_monke,
        "GhostCounter": ghost_counter,
        "BroadcastRoom": broadcast_room,
        "TaggedClient": tagged_client,
        "TaggedDistance": tagged_distance,
        "RPCS": rpcs
    }), 200

@app.route("/api/pfauthenticate", methods=["POST"])
def playfab_authentication():
    rjson = request.get_json()
    if not rjson:
        return jsonify({
            "Message": "Invalid JSON in request body",
            "Error": "BadRequest-InvalidJSON"
        }), 400

    required_fields = ["CustomId", "Nonce", "AppId", "Platform", "OculusId"]
    missing_fields = [field for field in required_fields if not rjson.get(field)]

    if missing_fields:
        return jsonify({
            "Message": f"Missing parameter(s): {', '.join(missing_fields)}",
            "Error": f"BadRequest-No{missing_fields[0]}"
        }), 400

    if rjson.get("AppId") != titleider:
        return jsonify({
            "Message": "Request sent for the wrong App ID",
            "Error": "BadRequest-AppIdMismatch"
        }), 400

    custom_id = rjson.get("CustomId", "")
    if not custom_id.startswith(("OC", "PI")):
        return jsonify({
            "Message": "Bad request",
            "Error": "BadRequest-NoOCorPIPrefix"
        }), 400

    url = f"https://{TitleId}.playfabapi.com/Server/LoginWithServerCustomId"
    login_request = requests.post(
        url=url,
        json={
            "ServerCustomId": custom_id,
            "CreateAccount": True
        },
        headers=authkey()
    )

    if login_request.status_code == 200:
        data = login_request.json().get("data", {})
        session_ticket = data.get("SessionTicket")
        entity_token_data = data.get("EntityToken", {})
        entity_token = entity_token_data.get("EntityToken")
        playfab_id = data.get("PlayFabId")
        entity_data = entity_token_data.get("Entity", {})
        entity_type = entity_data.get("Type"),
        entity_id = entity_data.get("Id"),

        link_response = requests.post(
            url=f"https://{TitleId}.playfabapi.com/Server/LinkServerCustomId",
            json={
                "ForceLink": True,
                "PlayFabId": playfab_id,
                "ServerCustomId": custom_id,
            },
            headers=authkey()
        )

        if link_response.status_code != 200:
            link_response_json = link_response.json()
            error_message = link_response_json.get('errorMessage', 'Unknown error')
            error_details = link_response_json.get('errorDetails', {})
            return jsonify({
                "ErrorMessage": error_message,
                "ErrorDetails": error_details
            }), link_response.status_code

        return jsonify({
            "PlayFabId": playfab_id,
            "SessionTicket": session_ticket,
            "EntityToken": entity_token,
            "EntityId": entity_id,
            "EntityType": entity_type,
        }), 200
    else:
        if login_request.status_code == 403:
            ban_info = login_request.json()
            if ban_info.get('errorCode') == 1002:
                ban_message = ban_info.get('errorMessage', "No ban message provided.")
                ban_details = ban_info.get('errorDetails', {})
                ban_expiration_key = next(iter(ban_details.keys()), None)
                ban_expiration_list = ban_details.get(ban_expiration_key, [])
                ban_expiration = ban_expiration_list[0] if len(ban_expiration_list) > 0 else "No expiration date provided."
                print(ban_info)
                return jsonify({
                    'BanMessage': ban_expiration_key,
                    'BanExpirationTime': ban_expiration
                }), 403
            else:
                error_message = ban_info.get('errorMessage', 'Forbidden without ban information.')
                return jsonify({
                    'Error': 'PlayFab Error',
                    'Message': error_message
                }), 403
        else:
            error_info = login_request.json()
            error_message = error_info.get('errorMessage', 'An error occurred.')
            return jsonify({
                'Error': 'PlayFab Error',
                'Message': error_message
            }), login_request.status_code

@app.route("/iap", methods=["POST"])   #iap = In app purschase or wtv, idont know to spell oi.
def consume_oculus_iap():
    rjson = request.get_json()

    access_token = rjson.get("userToken")
    user_id = rjson.get("userID")
    nonce = rjson.get("nonce")
    sku = rjson.get("sku")

    response = requests.post(
        url=f"https://graph.oculus.com/consume_entitlement?nonce={nonce}&user_id={user_id}&sku={sku}&access_token={ApiKey}",
        headers={"content-type": "application/json"}
    )

    if response.json().get("success"):
        return jsonify({"result": True})
    else:
        return jsonify({"error": True})

@app.route("/api/GetAcceptedAgreements", methods=['POST'])
def GetAcceptedAgreements():
    received_data = request.get_json()

    return jsonify({
        "ResultCode": 1,
        "StatusCode": 200,
        "Message": '',
        "result": 0,
        "CallerEntityProfile": received_data['CallerEntityProfile'],
        "TitleAuthenticationContext": received_data['TitleAuthenticationContext']
    })

@app.route("/api/SubmitAcceptedAgreements", methods=['POST'])
def SubmitAcceptedAgreements():
    received_data = request.get_json()

    return jsonify({
        "ResultCode": 1,
        "StatusCode": 200,
        "Message": '',
        "result": 0,
        "CallerEntityProfile": received_data['CallerEntityProfile'],
        "TitleAuthenticationContext": received_data['TitleAuthenticationContext'],
        "FunctionArgument": received_data['FunctionArgument']
    })

def save_accepted_agreements(agreements):
    with open('accepted_agreements.json', 'w') as file:
        json.dump(agreements, file)

@app.route("/api/K-ID", methods=["POST"])
def k_id():
    data = request.get_json()

    if not data:
        return jsonify({"error": "Missing JSON body"}), 400

    required_fields = ["Age", "Permissions", "GetSubmittedAge", "VoiceChat", "CustomNames", "PhotonPermission"]
    missing = [field for field in required_fields if field not in data]
    if missing:
      return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400


    user_age = data.get("Age")
    permissions = data.get("Permissions")
    submitted_age = data.get("GetSubmittedAge")
    voice_chat = data.get("VoiceChat")
    custom_name = data.get("CustomNames")
    photon_permission = data.get("PhotonPermission")

    response = {
        "status": "success",
        "UserAge": user_age,
        "Permissions": permissions,
        "GetSubmittedAge": submitted_age,
        "VoiceChat": voice_chat,
        "CustomNames": custom_name,
        "PhotonPermission": photon_permission,
        "AnnouncementData": {
            "ShowAnnouncement": "false",
            "AnnouncementID": "kID_Prelaunch",
            "AnnouncementTitle": "IMPORTANT NEWS",
            "Message": (
                "We're working to make Gorilla Tag a better, more age-appropriate experience "
                "in our next update. To learn more, please check out our Discord."
            )
        }
    }

    return jsonify(response), 200


if __name__ == "__main__":
    app.run(port=82080)

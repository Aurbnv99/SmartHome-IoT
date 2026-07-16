import threading
import time
import json
import paho.mqtt.client as mqtt

from config import TOPIC_STATUS

# Local MQTT client (for the main gateway)
mqtt_client_ref = None

# TTN MQTT client
ttn_client = None

## ******************************************** TTN CONFIGURATION (UPLINK ONLY)

TTN_APP_ID = "testing-room-3"              # Application ID on TTN
TTN_TENANT = "ttn"                        # Usually "ttn"
TTN_API_KEY = "NNSXS.VS3C7JVBRJPB3RKYRFDOW2G23L7JESBSKO3YGCA.C5MBBIK4LXV73IUC5ADQQ37GFUWJVFHJ37WGVQO7YDWWX3TQCOLA"
TTN_REGION = "nam1"
TTN_BROKER = f"nam1.cloud.thethings.network"
TTN_PORT = 1883

TTN_USERNAME = f"{TTN_APP_ID}@{TTN_TENANT}"
TTN_PASSWORD = TTN_API_KEY

# Map rooms to TTN Device IDs
# Insert the exact End Device ID registered on TTN for the Arduino
LORA_DEVICES = {
    "room3": "arduino-room-3"  
}

## ******************************************** INITIALIZATION

def init_lora(mqtt_client):
    global mqtt_client_ref, ttn_client
    mqtt_client_ref = mqtt_client

    print("[LORA-TTN] Initializing connection to The Things Network (RX Only)...")

    # Create an MQTT client to communicate with TTN
    ttn_client = mqtt.Client()
    ttn_client.username_pw_set(TTN_USERNAME, TTN_PASSWORD)
    
    # Callbacks
    ttn_client.on_connect = on_ttn_connect
    ttn_client.on_message = on_ttn_message

    try:
        ttn_client.connect(TTN_BROKER, TTN_PORT, 60)
        # Start MQTT loop in background
        ttn_client.loop_start()
    except Exception as e:
        print(f"[LORA-TTN ERROR] Failed to connect to TTN: {e}")

def on_ttn_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[LORA-TTN] Connected successfully to TTN Broker")
        # Subscribe to receive data (Uplink) from ALL devices in this app
        uplink_topic = f"v3/{TTN_USERNAME}/devices/+/up"
        client.subscribe(uplink_topic)
        print(f"[LORA-TTN] Subscribed to {uplink_topic}")
    else:
        print(f"[LORA-TTN ERROR] Connection failed with code {rc}")


## ******************************************** RECEIVE FROM TTN (UPLINK)

def on_ttn_message(client, userdata, msg):
    """
    Receives packets from TTN, extracts the payload (Base64 or decoded by TTN)
    and passes it to the local system.
    """
    try:
        payload_json = json.loads(msg.payload.decode('utf-8'))
        
        # Extract device ID to know who sent it
        device_id = payload_json.get("end_device_ids", {}).get("device_id", "unknown")
        
        # 1. Try to read the payload if a "Payload Formatter" is set on TTN
        decoded_payload = payload_json.get("uplink_message", {}).get("decoded_payload", {})
        data = decoded_payload.get("text", "")

        # 2. If no formatter on TTN, data is in "frm_payload" (Base64). Decode it.
        if not data:
            import base64
            b64_data = payload_json.get("uplink_message", {}).get("frm_payload", "")
            if b64_data:
                data = base64.b64decode(b64_data).decode('utf-8', errors='ignore')

        if data:
            #print(f"[LORA-TTN RX] From {device_id}: {data}")
            handle_incoming(data)

    except Exception as e:
        print(f"[LORA-TTN READ ERROR] {e}")


## ******************************************** DOWNLINK FUNCTION (DISABLED)

def send_to_lora(room, payload):
    """
    Intentionally empty function.
    Prevents the protocol_router from crashing the system if it attempts to send a command.
    """
    print(f"[LORA-TTN] Downlink disabled. Ignoring command '{payload}' for {room}.")


## ******************************************** HANDLE INCOMING FROM ARDUINO (LOCAL MQTT PARSING)

def handle_incoming(data):
    """
    Translates text received from Arduino into JSON messages for the Gateway.
    Supports single formats ("Light_R3 = 0") and combined formats ("Motion_R3 = 1|Light_R3 = 1")
    """
    try:
        # 1. Split the incoming payload by the pipe symbol '|'
        # This converts "Motion_R3=1|Light_R3=1" into a list: ["Motion_R3=1", "Light_R3=1"]
        messages = data.split("|")
        
        # 2. Process each sensor reading individually
        for msg in messages:
            msg = msg.strip()
            
            if "Garage" in msg:
                if "Open" in msg or "open" in msg:
                    payload = {"room": "garage", "door": "open"}
                    mqtt_client_ref.publish(TOPIC_STATUS, json.dumps(payload))
                    print("[LORA PARSED] Garage Door: open")
                elif "Closed" in msg or "closed" in msg:
                    payload = {"room": "garage", "door": "closed"}
                    mqtt_client_ref.publish(TOPIC_STATUS, json.dumps(payload))
                    print("[LORA PARSED] Garage Door: closed")
                continue

            # Check if the string contains the equals sign
            if "=" not in msg:
                continue

            # Split the string into key and value
            parts = msg.split("=")
            if len(parts) < 2:
                continue

            # Clean up spaces
            key = parts[0].strip()   # e.g., "Light_R3" or "Motion_R3"
            value = parts[1].strip() # e.g., "0" or "1"

            target_room = None
            
            # Identify the room
            if "R3" in key:
                target_room = "room3"

            # If the room is identified, check which sensor triggered it
            if target_room:
                if "Light" in key:
                    state = "on" if value == "1" else "off"
                    payload = {"room": target_room, "light": state}
                    mqtt_client_ref.publish(TOPIC_STATUS, json.dumps(payload))
                    print(f"[LORA PARSED] Room 3 Light: {state}") # Optional debug print
                
                elif "Motion" in key:
                    state = "MOTION" if value == "1" else "NOMOTION"
                    payload = {"room": target_room, "motion": state}
                    mqtt_client_ref.publish(TOPIC_STATUS, json.dumps(payload))
                    print(f"[LORA PARSED] Room 3 Motion: {state}") # Optional debug print
                
    except Exception as e:
        print(f"[LORA PARSE ERROR] {e} | Raw data: {data}")
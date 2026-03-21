import json
#from config import SIMULATION_MODE

from drivers.zigbee_driver import send_to_zigbee
from drivers.lora_driver import send_to_lora

## ******************************************** ROOM → PROTOCOL MAPPING

ROOM_PROTOCOL_MAP = {
    "room1": "zigbee",
    "room2": "zigbee",
    "room3": "lora",
    "garage": "ble"
}


## ******************************************** TRANSLATION LOGIC (JSON -> ARDUINO STRING)

def translate_payload_for_arduino(room, payload):
    prefix = ""
    if room == "room1":
        prefix = "r1"
    elif room == "room2":
        prefix = "r2"
    elif room == "room3":
        prefix = "r3"
    else:
        # If it's the garage or an unknown room, pass raw text
        return str(payload)
        
    # If a dictionary arrives (e.g., {'light': 'on'})
    if isinstance(payload, dict):
        device = list(payload.keys())[0].lower()
        action = list(payload.values())[0].lower()
        return f"{prefix} {device} {action}"
        
    # If it arrives already as a string for some reason
    return f"{prefix} {str(payload).lower().strip()}"


## ******************************************** ROUTER FUNCTION

def route_command(room, payload):
    protocol = ROOM_PROTOCOL_MAP.get(room)

    if protocol is None:
        print(f"[ROUTER ERROR] Unknown room: {room}")
        return

    # TRANSLATE (Python Dict -> Arduino String)
    arduino_cmd = translate_payload_for_arduino(room, payload)
    
    if not arduino_cmd:
        print(f"[ROUTER] No translatable command for {room}")
        return

    print("--------------------------------------------------")
    print(f"[ROUTER] Room      : {room}")
    print(f"[ROUTER] Protocol  : {protocol}")
    print(f"[ROUTER] Original  : {payload}")
    print(f"[ROUTER] Sending   : '{arduino_cmd}'")
    print("--------------------------------------------------")

    try:
        if protocol == "zigbee":
            # Send the translated string (e.g., "R1 HEAT HIGH")
            send_to_zigbee(room, arduino_cmd)

        elif protocol == "lora":
            send_to_lora(room, arduino_cmd)

        elif protocol == "ble":
            # BLE usually handles JSON or specific bytes, depends on the ESP32 code
            # For now pass the raw payload
            print(f"[ROUTER] BLE not fully implemented in this script")

        else:
            print(f"[ROUTER ERROR] Unsupported protocol: {protocol}")

    except Exception as e:
        print(f"[ROUTER ERROR] Failed to send command -> {e}")
import threading
import time
import json
import sys
import serial

from config import SIMULATION_MODE, LORA_PORT, BAUDRATE, TOPIC_STATUS

try:
    from lora_e220 import LoRaE220, Configuration
    from lora_e220_operation_constant import ResponseStatusCode
except ImportError:
    print("ERROR: Library 'lora_e220' not found.")
    sys.exit()

lora_module = None
mqtt_client_ref = None

## EBYTE E220 PINS ON GPIO RASPBERRY PI 5
AUX_PIN = 18
M0_PIN = 23
M1_PIN = 24

## ******************************************** DIRECT COMMUNICATION CONFIGURATION (POINT-TO-POINT)

LORA_PARAMETERS = {
    "room3": {
        "ADDH": 0x00, 
        "ADDL": 0x03, 
        "CHAN": 23    
    }
}

## ******************************************** INITIALIZATION

def init_lora(mqtt_client):
    global lora_module, mqtt_client_ref
    mqtt_client_ref = mqtt_client

    if SIMULATION_MODE:
        print("[LORA] Running in SIMULATION MODE (No Serial)")
        return

    try:
        # Serial and LoRa Module Initialization
        ser_lora = serial.Serial(LORA_PORT, BAUDRATE, timeout=1)
        lora_module = LoRaE220('900T22D', ser_lora, aux_pin=AUX_PIN, m0_pin=M0_PIN, m1_pin=M1_PIN)
        
        code = lora_module.begin()
        print(f"[LORA] Connected to {LORA_PORT}. Init Status: {ResponseStatusCode.get_description(code)}")

        # Fetch module configuration
        print("[LORA] Fetching module configuration...")
        conf_code, configuration = lora_module.get_configuration()
        if conf_code == ResponseStatusCode.SUCCESS:
            print("[LORA] Current Configuration:")
            for key, value in vars(configuration).items():
                if hasattr(value, '__dict__'):
                    print(f"   {key}:")
                    for sub_key, sub_value in vars(value).items():
                        print(f"      {sub_key}: {sub_value}")
                else:
                    print(f"   {key}: {value}")
        else:
            print(f"[LORA] Failed to fetch config: {ResponseStatusCode.get_description(conf_code)}")

        # Start the listening thread
        t = threading.Thread(target=read_loop, daemon=True)
        t.start()

    except Exception as e:
        print(f"[LORA ERROR] Failed to connect: {e}")


## ******************************************** FUNCTION (Called by Router)

def send_to_lora(room, payload):
    if SIMULATION_MODE:
        simulate(room, payload)
    else:
        real_serial_send(room, payload)


## ******************************************** SIMULATION MODE [Used for testing]

def simulate(room, payload):
    print(f"[SIM LORA] Room: {room} | Payload: {payload}")
    fake_status = {"room": room}
    payload_str = str(payload).lower()
    
    if "light" in payload_str:
        fake_status["light"] = "on" if "on" in payload_str else "off"
    elif "heater" in payload_str:
        fake_status["heater"] = "on" if "on" in payload_str else "off"
    mqtt_client_ref.publish(TOPIC_STATUS, json.dumps(fake_status))
    print("[SIM LORA STATUS SENT]", fake_status)


## ******************************************** REAL UART MODE (SEND)

def real_serial_send(room, payload):
    if not lora_module:
        print("[LORA] Not connected")
        return

    room_3 = LORA_PARAMETERS.get(room)
    if not room_3:
        print(f"[LORA TX ERROR] Room 3 not found")
        return
    command_string = str(payload) + "\n"

    try:
        code = lora_module.send_fixed_message(
            room_3["ADDH"], 
            room_3["ADDL"], 
            room_3["CHAN"], 
            command_string
        )
        if code == ResponseStatusCode.SUCCESS:
            print(f"[LORA TX] {command_string.strip()}")
        else:
            status_desc = ResponseStatusCode.get_description(code)
            print(f"[LORA TX ERROR] {status_desc}")
    except Exception as e:
        print(f"[LORA SEND ERROR] {e}")


## ******************************************** READ LOOP (RECEIVE)

def read_loop():
    while True:
        if lora_module and lora_module.available() > 0:
            # print(f"[LORA] Data available: {lora_module.available()} bytes") # DEBUG
            try:
                # Read the message using the library
                code, value = lora_module.receive_message(rssi=False)
                
                if code == ResponseStatusCode.SUCCESS:
                    line = str(value).strip()
                    if line:
                        # Raw print and pass to MQTT parsing function
                        print(f"[LORA RX] {line}") # DEBUG
                        handle_incoming(line)
                else:
                    description = ResponseStatusCode.get_description(code)
                    print(f"[LORA RX ERROR] Status: {description}")

            except Exception as e:
                print(f"[LORA READ ERROR] {e}")
        
        time.sleep(0.1)


## ******************************************** HANDLE INCOMING FROM ARDUINO

def handle_incoming(data):
    try:
        if "Light" in data:
            state = None
            target_room = None
            
            # Identify the room
            if "R3" in data:
                target_room = "room3"
            
            # Parse state (0 = off, 1 = on)
            if " = " in data:
                parts = data.split(" = ")
                if len(parts) >= 2:
                    state = "on" if parts[1].strip() == "1" else "off"

            if target_room and state:
                payload = {
                    "room": target_room,
                    "light": state
                }
                mqtt_client_ref.publish(TOPIC_STATUS, json.dumps(payload))
                #print(f"[MQTT STATUS UPDATE] {payload}") ## Debug
            return
    
    except (ValueError, IndexError) as e:
        print(f"[LORA PARSE ERROR] {e} | Raw data: {data}")
import threading
import time
import json
import sys
import serial

from config import LORA_PORT, BAUDRATE, TOPIC_STATUS
#from config import SIMULATION_MODE

try:
    from lora_e220 import LoRaE220, Configuration
    from lora_e220_operation_constant import ResponseStatusCode
except ImportError:
    print("ERROR: Library 'lora_e220' not found.")
    sys.exit()

lora_module = None
mqtt_client_ref = None
ack_received_event = threading.Event() # Event to synchronize the ACK

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

    # if SIMULATION_MODE:
    #     print("[LORA] Running in SIMULATION MODE (No Serial)")
    #     return

    try:
        # Serial and LoRa Module Initialization
        ser_lora = serial.Serial(LORA_PORT, BAUDRATE, timeout=1)
        lora_module = LoRaE220('900T22D', ser_lora, aux_pin=AUX_PIN, m0_pin=M0_PIN, m1_pin=M1_PIN)
        
        code = lora_module.begin()
        print(f"[LORA] Connected to {LORA_PORT}. Initialization Status: {ResponseStatusCode.get_description(code)}")

        # Start the listening thread
        t = threading.Thread(target=_read_loop, daemon=True)
        t.start()

    except Exception as e:
        print(f"[LORA ERROR] Failed to connect: {e}")


## ******************************************** FUNCTION (Called by Router)

def send_to_lora(room, payload):
    # if SIMULATION_MODE:
    #     simulate(room, payload)
    # else:
        real_serial_send_with_retry(room, payload)


## ******************************************** SIMULATION MODE [Used for testing]

# def simulate(room, payload):
#     print(f"[SIM LORA] Room: {room} | Payload: {payload}")
#     # ... simulation code unchanged ...
#     fake_status = {"room": room}
#     payload_str = str(payload).lower()
#     if "light" in payload_str:
#         fake_status["light"] = "on" if "on" in payload_str else "off"
#     mqtt_client_ref.publish(TOPIC_STATUS, json.dumps(fake_status))


## ******************************************** REAL UART MODE (SEND WITH RETRY)

def real_serial_send_with_retry(room, payload):
    if not lora_module:
        print("[LORA] Not connected")
        return

    room_3 = LORA_PARAMETERS.get(room)
    if not room_3:
        print(f"[LORA TX ERROR] Room 3 not found")
        return
    
    command_string = str(payload)
    max_retries = 3
    attempt = 1
    sent_successfully = False

    while attempt <= max_retries and not sent_successfully:
        print(f"[LORA TX] '{command_string}' -> {room} (Attempt {attempt}/{max_retries})")
        
        ack_received_event.clear()
        try:
            code = lora_module.send_fixed_message(
                room_3["ADDH"], 
                room_3["ADDL"], 
                room_3["CHAN"], 
                command_string
            )
            
            # Wait for the ACK for 2 seconds
            if code == ResponseStatusCode.SUCCESS:
                # Blocks the current thread until the ACK is received from the read thread
                # or until the 2 seconds expire
                if ack_received_event.wait(timeout=2.0):
                    print(f"[LORA TX] ACK Received! Message delivered.")
                    sent_successfully = True
                else:
                    print(f"[LORA TX] No ACK received (Timeout).")
            else:
                print(f"[LORA TX ERROR] Send failed: {ResponseStatusCode.get_description(code)}")

        except Exception as e:
            print(f"[LORA SEND ERROR] {e}")

        if not sent_successfully:
            attempt += 1
            time.sleep(0.5) # Pause before the next attempt

    if not sent_successfully:
        print(f"[LORA TX FAILED] Max retries reached for '{command_string}'")


## ******************************************** READ LOOP (RECEIVE + SEND ACK BACK)

def read_loop():
    while True:
        if lora_module and lora_module.available() > 0:
            # print(f"[LORA] Data available: {lora_module.available()} bytes") # DEBUG
            try:
                code, value = lora_module.receive_message(rssi=False)
                
                if code == ResponseStatusCode.SUCCESS:
                    line = str(value).strip()
                    if line:
                        print(f"[LORA RX] {line}") # DEBUG
                        
                        # --- ACK MANAGEMENT ---
                        if "ACK" in line or "ack" in line:
                            ack_received_event.set()
                        else:
                            handle_incoming(line)
                            
                            # SEND AN ACK BACK IMMEDIATELY
                            send_ack_reply("room3") 
                else:
                    print(f"[LORA RX ERROR] Status: {ResponseStatusCode.get_description(code)}")

            except Exception as e:
                print(f"[LORA READ ERROR] {e}")
        
        time.sleep(0.1)

# Helper function to send only the ACK without waiting for a reply (otherwise infinite loop)
def send_ack_reply(room_name):
    room_3 = LORA_PARAMETERS.get(room_name)
    if room_3:
        try:
            lora_module.send_fixed_message(
                room_3["ADDH"], 
                room_3["ADDL"], 
                room_3["CHAN"], 
                "ACK_OK"
            )
            print(f"[LORA RX] Sent ACK to {room_name}")
        except:
            pass


## ******************************************** HANDLE INCOMING FROM ARDUINO (MQTT PARSING)

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
import serial
import threading
import json
import time

from config import ZIGBEE_PORT, BAUDRATE, TOPIC_STATUS
#from config import SIMULATION_MODE

zigbee_serial = None
mqtt_client = None


## ******************************************** INIT

def init_zigbee(mqtt):
    global zigbee_serial, mqtt_client

    mqtt_client = mqtt

    # if SIMULATION_MODE:
    #     print("[ZIGBEE] Running in SIMULATION MODE")
    #     return

    try:
        zigbee_serial = serial.Serial(ZIGBEE_PORT, BAUDRATE, timeout=1)
        # Empty buffers to clear out any junk data before start
        zigbee_serial.flushInput()
        zigbee_serial.flushOutput()
        print("[ZIGBEE] Serial connected")

        # Start the listening thread
        t = threading.Thread(target=read_loop, daemon=True)
        t.start()

    except Exception as e:
        print(f"[ZIGBEE ERROR] Failed to connect: {e}")


## ******************************************** FUNCTION CALLED BY ROUTER

def send_to_zigbee(room, payload):
    # if SIMULATION_MODE:
    #     simulate(room, payload)
    # else:
        real_serial_send(room, payload)


## ******************************************** SIMULATION MODE

# def simulate(room, payload):
#     print(f"[SIM ZIGBEE] Room: {room} | Payload: {payload}")
#     fake_status = {"room": room}
#     payload_str = str(payload).lower()
#     if "light" in payload_str:
#         fake_status["light"] = "on" if "on" in payload_str else "off"
#     elif "heater" in payload_str:
#         fake_status["heater"] = "on" if "on" in payload_str else "off"
#     mqtt_client.publish(TOPIC_STATUS, json.dumps(fake_status))
#     print("[SIM ZIGBEE STATUS SENT]", fake_status)


## ******************************************** REAL SERIAL MODE

def real_serial_send(room, payload):
    if not zigbee_serial:
        print("[ZIGBEE] Not connected")
        return

    command_string = str(payload) + "\n"

    try:
        zigbee_serial.write(command_string.encode('utf-8'))
        print(f"[ZIGBEE SENT] {command_string.strip()}")
    except Exception as e:
        print(f"[ZIGBEE ERROR] Failed to write to serial: {e}")


## ******************************************** READ LOOP

def read_loop():
    while True:
        try:
            if zigbee_serial and zigbee_serial.in_waiting > 0:
                line = zigbee_serial.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    print(f"[ZIGBEE RX] {line}") # DEBUG
                    handle_incoming(line)

        except Exception as e:
            print(f"[ZIGBEE READ ERROR] {e}")


## ******************************************** HANDLE INCOMING DATA FROM ARDUINO

def handle_incoming(data):
    try:
        if ":" in data and data.startswith("R"):
            parts = data.split(":")
            if len(parts) >= 4:
                room_id = parts[0]
                temperature = float(parts[1])
                humidity = float(parts[2])
                pressure = float(parts[3])

                room_name = room_id.replace("R", "room")

                payload = {
                    "room": room_name,
                    "temperature": temperature,
                    "humidity": humidity,
                    "pressure": pressure
                }

                mqtt_client.publish(TOPIC_STATUS, json.dumps(payload))
                #print(f"[MQTT STATUS UPDATE] {payload}") #DEBUG

        elif "Light" in data:
            # Understands if the light is ON or OFF
            state = None
            target_room = None

            # Identify the room
            if "R1" in data:
                target_room = "room1"
            elif "R2" in data:
                target_room = "room2"
            
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
                mqtt_client.publish(TOPIC_STATUS, json.dumps(payload))
                #print(f"[MQTT STATUS UPDATE] {payload}") # DEBUG
            else:
                print(f"[ZIGBEE PARSE ERROR] Invalid Light data: {data}")
        
        elif "Heater" in data:
            # Heater format: "Heater_R1 = 1" or "Heater_R1 = 0"
            state = None
            target_room = None

            # Identify the room
            if "R1" in data:
                target_room = "room1"
            elif "R2" in data:
                target_room = "room2"
            
            # Parse state (0 = off, 1 = on)
            if " = " in data:
                parts = data.split(" = ")
                if len(parts) >= 2:
                    state = "on" if parts[1].strip() == "1" else "off"
            
            if target_room and state:
                payload = {
                    "room": target_room,
                    "heater": state
                }
                #print(f"[DEBUG ZIGBEE] Built Payload Dictionary: {payload}") # DEBUG
                mqtt_client.publish(TOPIC_STATUS, json.dumps(payload))
                #print(f"[MQTT STATUS UPDATE] {payload}") # DEBUG
            else:
                print(f"[ZIGBEE PARSE ERROR] Invalid Heater data: {data}")

        elif "Motion" in data:
            # Motion format: "Motion_R1 = 1" or "Motion_R1 = 0"
            state = None
            target_room = None

            # Identify the room
            if "R1" in data:
                target_room = "room1"
            elif "R2" in data:
                target_room = "room2"
            
            # Parse state (0 = NOMOTION, 1 = MOTION)
            if " = " in data:
                parts = data.split(" = ")
                if len(parts) >= 2:
                    state = "MOTION" if parts[1].strip() == "1" else "NOMOTION"
            
            if target_room and state:
                payload = {
                    "room": target_room,
                    "motion": state
                }
                mqtt_client.publish(TOPIC_STATUS, json.dumps(payload))
                #print(f"[MQTT STATUS UPDATE] {payload}") # DEBUG
            else:
                print(f"[ZIGBEE PARSE ERROR] Invalid Motion data: {data}")
                
    except (ValueError, IndexError) as e:
        print(f"[ZIGBEE PARSE ERROR] {e} | Raw data: {data}")
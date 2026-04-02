import time
import threading
import json
from datetime import datetime
import sys
import os
import csv
from collections import deque

import numpy as np
import pandas as pd
import joblib
import requests
import paho.mqtt.client as mqtt
from tensorflow import keras 
import RPi.GPIO as GPIO

from google.oauth2 import service_account
import google.auth.transport.requests 

from protocol_router import route_command
from ai_features import build_proxy_features

from drivers.zigbee_driver import init_zigbee
from drivers.lora_driver import init_lora

from config import (
    MQTT_BROKER, MQTT_PORT,
    TOPIC_COMMAND_SUB, TOPIC_STATUS
)

# ********************** CSV LOGGING INITIALIZATION
CSV_FILENAME = "real_vs_ai_log.csv"
if not os.path.exists(CSV_FILENAME):
    with open(CSV_FILENAME, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["timestamp", "actual_load_kw", "predicted_load_kw"])
# **********************

## ******************************************** SMART HOME STATE

home_state = {
    "room1": {
        "temperature": 22.0,
        "humidity": 50,
        "pressure": 1012,
        "light": "off",
        "heater": "off",
        "motion": "NOMOTION"
    },
    "room2": {
        "temperature": 21.0,
        "humidity": 45,
        "pressure": 1010,
        "light": "off",
        "heater": "off"
    },
    "room3": {
        "light": "off",
        "motion": "NOMOTION"
    },
    "garage": {
        "door": "closed"
    }
}


## ******************************************** LOAD AI MODEL + SCALER

MODEL_PATH = "../AI_Model/model/energy_model_optimized.keras"
SCALER_PATH = "../AI_Model/model/robust_scaler.pkl"

print("Loading AI model...")
try:
    model = keras.models.load_model(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    print("AI Model Loaded\n")
except Exception as e:
    print(" Error loading model/scaler:", e)
    raise SystemExit(1)


## ******************************************** FIREBASE NOTIFICATIONS

PROJECT_ID = "smart-energy-consumption-52ef0"
FCM_URL = f"https://fcm.googleapis.com/v1/projects/{PROJECT_ID}/messages:send"
SERVICE_ACCOUNT_FILE = "service_account.json"
DEVICE_TOKEN = "d5IO5XQLSpOP281x8gu3WT:APA91bGTlQ2j0IQk3jsJUQRC_cHjo_KM5ybRhIM-ZJTaT13cTlQcPNA1rcge_wcBjW77HCC7jTvUpje2zCAGK9WZNm88BRNLUB8YK36Ow10hpIT3SpX01SY"

def get_access_token():
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/firebase.messaging"],
    )
    req = google.auth.transport.requests.Request()
    credentials.refresh(req)
    return credentials.token

def send_notification(title, body):
    try:
        token = get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; UTF-8",
        }
        message = {
            "message": {
                "token": DEVICE_TOKEN,
                "notification": {"title": title, "body": body},
            }
        }
        requests.post(FCM_URL, headers=headers, json=message, timeout=10)
    except Exception as e:
        print("Notification error:", e)


## ******************************************** ALERT SYSTEM

ALERT_COOLDOWN = 120  # Seconds between same alert
last_alert_time = {}  # Timers for each specific rule
alert_state = {}      # Current state for each rule
current_alert_level = 0
ALERT_LEVELS = {"INFO": 1, "WARNING": 2, "CRITICAL": 3}

def safe_notify(rule_id, level, title, msg):

    global current_alert_level
    now = time.time()
    rule_level = ALERT_LEVELS.get(level, 1)

    # Global Priority Check: suppress lower priority if higher is active
    if rule_level < current_alert_level:
        return

    # Individual Cooldown Check: prevents spam for the same rule
    if alert_state.get(rule_id) == "active":
        if rule_id in last_alert_time and (now - last_alert_time[rule_id] < ALERT_COOLDOWN):
            return

    # State Update
    current_alert_level = rule_level
    last_alert_time[rule_id] = now
    alert_state[rule_id] = "active"

    # Trigger Firebase Notification
    print(f">> {level} ALERT: {title} | {msg}")
    #send_notification(title, msg)

def clear_state(rule_id):
    global current_alert_level
    
    if alert_state.get(rule_id) == "active":
        alert_state[rule_id] = "cleared"
        # Reset global level to allow other alerts to pass through
        current_alert_level = 0
        print(f"Rule {rule_id} is back to normal.")


## ******************************************** AUTO CONTROL SYSTEM

AUTO_MODE = True
AUTO_COOLDOWN = 120
last_auto_action = {}

def safe_auto_action(action_id, room, payload, custom_cooldown=None):
    now = time.time()
    # Use of customized cooldown, default otherwise
    cooldown = custom_cooldown if custom_cooldown is not None else AUTO_COOLDOWN
    if action_id in last_auto_action:
        if now - last_auto_action[action_id] < AUTO_COOLDOWN:
            return
    last_auto_action[action_id] = now
    print(f"AUTO ACTION: {room} | {payload}")
    route_command(room, payload)
    

def choose_device_to_turn_off(raw): # Selects the device with the highest consumption among the active ones.
    controllable_devices = {}
    
    # HEATER: sum of active heaters
    heater_consumption = 0
    for room in ["room1", "room2"]:
        if home_state[room].get("heater") == "on":
            heater_consumption += raw.get("furnace_1" if room == "room1" else "furnace_2", 0)
    
    if heater_consumption > 0.1:
        controllable_devices["heater"] = heater_consumption

    if not controllable_devices:
        return None
    
    device = max(controllable_devices, key=controllable_devices.get)
    return device


def choose_room_for_heater(): # Selects the room where the heater should be turned off.
                              # Priority: first room with an active heater.
    for room in ["room1", "room2"]:
        if home_state[room].get("heater") == "on":
            return room
    return "room1"


## ******************************************** MQTT HANDLERS

mqtt_client = None

def publish_status():
    for room, values in home_state.items():
        payload = {"room": room}
        payload.update(values)
        mqtt_client.publish(TOPIC_STATUS, json.dumps(payload))


def _room_from_topic(topic):
    parts = topic.split("/")
    if len(parts) == 3 and parts[0] == "home" and parts[2] == "command":
        return parts[1]
    return None


def on_connect(client, userdata, flags, rc, properties=None):
    print("[MQTT] Connected:", rc)

    # Subscribe
    client.subscribe(TOPIC_COMMAND_SUB)
    client.subscribe(TOPIC_STATUS)

    init_zigbee(client)
    init_lora(client)

    print("[DRIVERS] Initialized")


def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode()

    try:
        data = json.loads(payload)

        # Hardware Status Update
        # This updates the AI when a physical button or relay changes state
        if topic == TOPIC_STATUS:
            room = data.get("room")
            if room and room in home_state:
                # Update home_state with all the real sensor values received
                for key, value in data.items():
                    if key != "room":
                        home_state[room][key] = value
            return
        
        # Smart Home Commands (From Dashboard to Hardware)
        room = _room_from_topic(topic)
        if room and room in home_state:
            changed = False

            if "light" in data and "light" in home_state[room]:
                val = str(data["light"]).lower()
                if val in ["on", "off"]:
                    home_state[room]["light"] = val
                    changed = True

            if "heater" in data and "heater" in home_state[room]:
                val = str(data["heater"]).lower()
                if val in ["on", "off"]:
                    home_state[room]["heater"] = val
                    changed = True

            if changed:
                route_command(room, data)
                publish_status()

    except Exception as e:
        print("MQTT Error:", e)


## ******************************************** AI ENERGY THREAD

FEATURES = [
    'house_overall', 'dishwasher', 'furnace_1', 'furnace_2', 'fridge', 'microwave',
    'living_room', 'temperature', 'humidity', 'pressure',
    'hour', 'day_of_week', 'month', 'is_weekend',
    'hour_sin', 'hour_cos', 'day_sin', 'day_cos',
    'peak_morning', 'peak_evening', 'is_night'
]
WINDOW_STATS = 20  # Values to calculate the moving average
K_SIGMA = 1.5      # System sensitivity (1.5 = sensitive, 2.5 = conservative)
MAX_HISTORY = 300
#HISTORY_FILE = "dashboard_data.json"
history = []

def ai_energy_thread():
    global history

    SEQUENCE_LENGTH   = 60   
    PRED_INTERVAL     = 5    # prediction every 5 s
    CSV_LOG_INTERVAL  = 60
    PRINT_INTERVAL    = 10

    # Use a deque so appending is O(1) and the oldest entry auto-drops
    buffer = deque(maxlen=SEQUENCE_LENGTH)

    # METER LIMITS
    MAX_HOUSE_KW = 2.5
    overload_counter = 0

    # State flags & timers
    pred_real       = 0.0
    model_ready     = False  # True once buffer has 60 entries
    last_pred_time  = 0.0
    last_csv_time   = 0.0
    last_print_time = 0.0

    # ********************* BIAS
    # Tracked the rolling mean of (actual - raw_prediction) over the
    # last BIAS_WINDOW inferences and add it back to every new output.
    # Needs at least 3 samples before it activates (safe cold-start).
    # *********************

    BIAS_WINDOW  = 10   # number of past inferences used for correction
    bias_errors  = []   # stores (curr_kw - pred_raw) per inference call

    # Noise variables
    last_noise_update     = 0
    NOISE_UPDATE_INTERVAL = 300
    appliance_noise = {
        'furnace_1':       0.0,
        'furnace_2':       0.0,
        'dishwasher':      0.0,
        'microwave':       0.0,
        'living_room_idle': 0.0015,
    }

    print(">> AI Energy System Started.")
    print(f">> Collecting {SEQUENCE_LENGTH} s of data before predictions begin...\n")

    while True:
        try:
            now              = datetime.now()
            current_time_sec = time.time()

            # ********************* BUILD PROXY FEATURES
            
            raw_original = build_proxy_features(now, home_state)
            raw = raw_original.copy()

            # Noise refresh every 5 min
            if current_time_sec - last_noise_update >= NOISE_UPDATE_INTERVAL:
                appliance_noise['furnace_1']        = float(np.random.uniform(-0.02,   0.02))
                appliance_noise['furnace_2']        = float(np.random.uniform(-0.02,   0.02))
                appliance_noise['dishwasher']       = float(np.random.uniform(-0.02,   0.02))
                appliance_noise['microwave']        = float(np.random.uniform(-0.001,  0.001))
                appliance_noise['living_room_idle'] = float(np.random.uniform( 0.0010, 0.0020))
                last_noise_update = current_time_sec

            # Unit / range conversions to match training-data distribution
            if 'temperature' in raw:
                raw['temperature'] = (raw['temperature'] * 9/5) + 32
            if 'humidity' in raw:
                raw['humidity'] = raw['humidity'] / 100.0

            current_minute = now.minute
            if 'fridge' in raw:
                fridge_target = 0.2252 if (current_minute % 30) < 15 else 0.0043
                prev_fridge   = raw.get('fridge', fridge_target)
                raw['fridge'] = float(
                    prev_fridge * 0.92 + fridge_target * 0.08
                    + appliance_noise['furnace_1'] * 0.1
                )
                raw['fridge'] = max(0.0043, min(raw['fridge'], 0.2252))

            if 'living_room' in raw:
                if raw['living_room'] < 0.01:
                    raw['living_room'] = appliance_noise['living_room_idle']
                else:
                    raw['living_room'] = min(float(raw['living_room']), 0.3397)

            for furnace, baseline_min, max_cap in [('furnace_1', 0.0117, 0.5621),
                                                    ('furnace_2', 0.0616, 0.7256)]:
                if furnace in raw:
                    if raw[furnace] < 0.01:
                        raw[furnace] = float(np.random.uniform(baseline_min, baseline_min + 0.003))
                    else:
                        raw[furnace] = min(float(raw[furnace]) + appliance_noise[furnace], max_cap)

            if 'dishwasher' in raw:
                if raw['dishwasher'] < 0.01:
                    raw['dishwasher'] = float(np.random.uniform(0.0, 0.000283))
                else:
                    raw['dishwasher'] = min(float(raw['dishwasher']) + appliance_noise['dishwasher'], 1.3453)

            if 'microwave' in raw and raw['microwave'] >= 0.01:
                raw['microwave'] = min(float(raw['microwave']) + appliance_noise['microwave'], 0.0063)

            # Propagate component deltas back into house_overall
            diff_lr    = raw.get('living_room', 0) - raw_original.get('living_room', 0)
            diff_fridge= raw.get('fridge',       0) - raw_original.get('fridge',       0)
            diff_f1    = raw.get('furnace_1',     0) - raw_original.get('furnace_1',     0)
            diff_f2    = raw.get('furnace_2',     0) - raw_original.get('furnace_2',     0)
            diff_dw    = raw.get('dishwasher',    0) - raw_original.get('dishwasher',    0)
            diff_mw    = raw.get('microwave',     0) - raw_original.get('microwave',     0)

            if 'house_overall' in raw:
                raw['house_overall'] = max(
                    0.0,
                    raw['house_overall'] + diff_lr + diff_fridge + diff_f1 + diff_f2 + diff_dw + diff_mw
                )

            curr_kw = float(raw['house_overall'])


            df_row = pd.DataFrame([raw])[FEATURES]
            buffer.append(df_row.values[0])   # deque auto-drops oldest


            if len(buffer) == SEQUENCE_LENGTH:
                if not model_ready:
                    model_ready = True
                    pred_real   = curr_kw          # seed with actual so no flat-zero spike
                    print(f"\n[{now.strftime('%H:%M:%S')}] Buffer ready – AI predictions are now live!\n")

                if current_time_sec - last_pred_time >= PRED_INTERVAL:
                    df_seq     = pd.DataFrame(list(buffer), columns=FEATURES)
                    scaled_seq = scaler.transform(df_seq)
                    input_seq  = scaled_seq.reshape(1, SEQUENCE_LENGTH, -1)

                    pred_scaled = model.predict(input_seq, verbose=0)[0][0]

                    dummy       = np.zeros((1, len(FEATURES)))
                    dummy[0, 0] = pred_scaled
                    # Raw inverse-scaled prediction before bias correction
                    pred_raw    = float(scaler.inverse_transform(dummy)[0][0])

                    # ********************* ROLLING BIAS

                    bias_errors.append(curr_kw - pred_raw)
                    if len(bias_errors) > BIAS_WINDOW:
                        bias_errors.pop(0)

                    bias_correction = float(np.mean(bias_errors)) if len(bias_errors) >= 3 else 0.0
                    pred_real       = pred_raw + bias_correction

                    last_pred_time = current_time_sec

                # Console update (throttled to PRINT_INTERVAL)
                if current_time_sec - last_print_time >= PRINT_INTERVAL:
                    # Show bias only once it's active (≥3 samples)
                    bias_str = f"  bias={float(np.mean(bias_errors)):+.3f} kW" if len(bias_errors) >= 3 else "  bias=warming up"
                    print(f"[{now.strftime('%H:%M:%S')}] AI UPDATE | "
                          f"Current: {curr_kw:05.2f} kW  >>>  AI Predicts: {pred_real:05.2f} kW{bias_str}")
                    last_print_time = current_time_sec

                # CSV log
                if current_time_sec - last_csv_time >= CSV_LOG_INTERVAL:
                    try:
                        with open(CSV_FILENAME, mode='a', newline='') as f:
                            csv.writer(f).writerow([
                                now.strftime("%Y-%m-%d %H:%M:%S"),
                                round(curr_kw,   4),
                                round(pred_real, 4),
                            ])
                        last_csv_time = current_time_sec
                    except Exception as csv_error:
                        print(f"CSV write error: {csv_error}")

            else:
                # during the 60-second warm-up, mirror curr_kw so the dashboard never shows a dead-flat 0 kW line.
                pred_real = curr_kw
                if current_time_sec - last_print_time >= 5:
                    remaining = SEQUENCE_LENGTH - len(buffer)
                    print(f"[{now.strftime('%H:%M:%S')}] Buffering: "
                          f"({len(buffer)}/{SEQUENCE_LENGTH}) – {remaining}s until live predictions")
                    last_print_time = current_time_sec

            # ********************* SMART METER LOGIC
            if model_ready:
                if pred_real > MAX_HOUSE_KW:
                    overload_counter += 1
                    print(f"WARNING: Predicted load {pred_real:.2f} kW > {MAX_HOUSE_KW} kW. "
                          f"Trip in {10 - overload_counter}s.")

                    if overload_counter >= 10:
                        safe_notify("METER_TRIP", "CRITICAL", "Main Breaker Warning",
                                    f"Sustained overload: {pred_real:.2f} kW. Emergency cutoff initiated.")
                        if AUTO_MODE:
                            device = choose_device_to_turn_off(raw)
                            if device == "heater":
                                target_room = choose_room_for_heater()
                                safe_auto_action("EMERGENCY_CUTOFF", target_room,
                                                 {"heater": "off"}, custom_cooldown=60)
                        overload_counter = 0
                else:
                    if overload_counter > 0:
                        print("Load back within limits. Danger timer reset.")
                        clear_state("METER_TRIP")
                    overload_counter = 0

            # Environmental rules
            if raw.get("temperature", 0) > 80.6:
                safe_notify("HIGH_TEMP", "INFO", "High Temperature", "Consider turning on AC.")
            else:
                clear_state("HIGH_TEMP")

            # ********************* Debug JSON
            # sample = {
            #     "timestamp":   now.strftime("%H:%M:%S"),
            #     "house":       curr_kw,
            #     "prediction":  pred_real,
            #     "microwave":   float(raw["microwave"]),
            #     "dishwasher":  float(raw["dishwasher"]),
            #     "furnace":     float(raw["furnace_1"] + raw["furnace_2"]),
            #     "temp":        float((raw["temperature"] - 32) * 5/9) if 'temperature' in raw else 0.0,
            #     "model_ready": model_ready,
            # }
            # history.append(sample)
            # if len(history) > MAX_HISTORY:
            #     history.pop(0)

            # temp_file = HISTORY_FILE + ".tmp"
            # with open(temp_file, "w") as f:
            #     json.dump(history, f)
            # os.replace(temp_file, HISTORY_FILE)

            time.sleep(1)

        except Exception as e:
            print(f"[AI ERROR] {e}")
            time.sleep(5)


## ******************************************** MAIN

if __name__ == "__main__":
    print(" ********************** SMART HOME + REAL SENSORS + AI SYSTEM STARTED **********************")

    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    # Start AI Thread
    threading.Thread(target=ai_energy_thread, daemon=True).start()

    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()

        # Keep main thread alive
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n ********************** System stopping ********************** ")
        try:
            print("Releasing GPIO resources")
            GPIO.cleanup()
        except Exception as e:
            print(f"Error during cleanup: {e}")
            
        sys.exit()

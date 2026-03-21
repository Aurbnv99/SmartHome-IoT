import numpy as np

# ********************** Translates real sensor data (from home_state) 
# ********************** into the 21 features
# ********************** expected by my model.

def build_proxy_features(now, home_state):
    
    hour = now.hour
    dow = now.weekday()
       
    # From Room 1 and Room 2 [Temperature, Humidity, Pressure]
    temp_r1 = float(home_state.get("room1", {}).get("temperature", 22.0))
    temp_r2 = float(home_state.get("room2", {}).get("temperature", 22.0))
    temp = (temp_r1 + temp_r2) / 2.0  # Average house temperature to adapt it with the dataset
    
    hum_r1 = float(home_state.get("room1", {}).get("humidity", 50.0))
    hum_r2 = float(home_state.get("room2", {}).get("humidity", 50.0))
    hum = (hum_r1 + hum_r2) / 2.0     # Average house humidity to adapt it with the dataset

    press_r1 = float(home_state.get("room1", {}).get("pressure", 1012.0))
    press_r2 = float(home_state.get("room2", {}).get("pressure", 1012.0))
    press = (press_r1 + press_r2) / 2.0 # Average house pressure to adapt it with the dataset
    
    # From Rooms [Light, Heater, Motion]
    light_r1 = (home_state.get("room1", {}).get("light", "off") == "on")
    light_r2 = (home_state.get("room2", {}).get("light", "off") == "on")
    light_r3 = (home_state.get("room3", {}).get("light", "off") == "on")
    
    heater_r1 = (home_state.get("room1", {}).get("heater", "off") == "on")
    heater_r2 = (home_state.get("room2", {}).get("heater", "off") == "on")
    
    motion_r1 = (home_state.get("room1", {}).get("motion", "NOMOTION") == "MOTION")
    motion_r2 = (home_state.get("room2", {}).get("motion", "NOMOTION") == "MOTION")
    motion_r3 = (home_state.get("room3", {}).get("motion", "NOMOTION") == "MOTION")
    
    # ********************** INFER APPLIANCE USAGE (Proxy Logic)
    
    # Fridge: Always running background load (Constant)
    fridge = 0.15  # 150 Watts

    # Microwave Logic:
    # IF motion is detected in Room 1 (Kitchen) AND it is "meal time", 
    # THEN assume microwave is running (1.2 kW). Otherwise 0.
    if motion_r1 and (11 <= hour <= 14 or 18 <= hour <= 21):
        microwave = 1.2 
    else:
        microwave = 0.0

    # Dishwasher Logic:
    # Assume it runs if specifically toggled in home_state, 
    # OR if it's late evening (peak saving time) as a simulation fallback.
    dishwasher_active = (home_state.get("kitchen", {}).get("dishwasher", "off") == "on")
    if dishwasher_active:
        dishwasher = 1.0 # 1000 Watts
    elif 20 <= hour <= 22:
        dishwasher = 1.0
    else:
        dishwasher = 0.0

    # Heater / Furnace Logic:
    # If the heater relay is ON, add the load of the furnace.
    furnace_1 = 1.5 if heater_r1 else 0.0
    furnace_2 = 1.0 if heater_r2 else 0.0

    # Living Room Logic:
    # If the Light is ON, assume other electronics (TV, etc.) might be on too.
    living_room = 0.01
    if light_r1: living_room += 0.3 # 300W (Light + TV assumption)
    if light_r2: living_room += 0.3 # 300W (Light + TV assumption)
    if light_r3: living_room += 0.1 # 100W Garage Light only
    

    # ********************** CALCULATE TOTAL HOUSE LOAD
    
    house = (
        fridge + dishwasher + furnace_1 +
        furnace_2 + microwave + living_room +
        float(np.random.uniform(0.01, 0.05)) # Small random noise for realism
    )

    # ********************** RETURN FEATURES FOR MODEL
    
    # This dictionary matches exactly the 21 columns my model was trained on.
    raw = {
        "house_overall": house,
        "dishwasher": dishwasher,
        "furnace_1": furnace_1,
        "furnace_2": furnace_2,
        "fridge": fridge,
        "microwave": microwave,
        "living_room": living_room,
        "temperature": temp,
        "humidity": hum,
        "pressure": press,
        "hour": hour,
        "day_of_week": dow,
        "month": now.month,
        "is_weekend": 1 if dow >= 5 else 0,
        "hour_sin": float(np.sin(2*np.pi*hour/24)),
        "hour_cos": float(np.cos(2*np.pi*hour/24)),
        "day_sin": float(np.sin(2*np.pi*dow/7)),
        "day_cos": float(np.cos(2*np.pi*dow/7)),
        "peak_morning": 1 if 6 <= hour <= 9 else 0,
        "peak_evening": 1 if 17 <= hour <= 21 else 0,
        "is_night": 1 if (hour >= 22 or hour <= 6) else 0,
    }

    return raw
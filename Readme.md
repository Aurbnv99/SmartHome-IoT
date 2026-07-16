**Smart Home IoT & Predictive Energy Modeling**

This repository contains the full source code for an integrated Smart Home ecosystem featuring **Edge
Computing**, **Multi-protocol Networking (Zigbee, LoRa, BLE)**,
and **Predictive AI**.

**Project Structure**

-   *Gateway_Python/*: Core engine running on Raspberry Pi 5.
-   *Firmware_Arduino/*: Code for Zigbee (Rooms 1 & 2) and LoRa (Garage)
    nodes.
-   *Smart_Energy_Consumption.zip*: Flutter dashboard source code.


**1. Hardware Setup**

Connect the sensors and actuators as illustrated in
the Report and in the Hardware Schematics pictures.

-   **Indoor Nodes:** Arduino + BME280 + TSL2561 + PIR + XBee.

-   **Outdoor Node:** Arduino + ESP32 (BLE) + LoRA/GPS Arduino Shield v1.3 (HAT).

-   **Gateway:** Raspberry Pi 5 + XBee Adapter.

**2. Software Requirements**

**Python (Gateway)**

Install dependencies via terminal:
```bash
pip install -r requirements.txt
```
**Arduino (Nodes)**

Ensure the following libraries are installed in your Arduino IDE:

-   Adafruit BME280 by Adafruit

-   Adafruit TSL2561 by Adafruit

-   IBM LMIC Framework by IBM (v1.5.1)

Ensure the following boards are installed in your Arduino IDE:

-   Esp32 by EspressIf

-   Arduino AVR Boards by Arduino

**Flutter (Mobile App)**

Ensure you have the Flutter SDK installed on your machine.

**Firebase Configuration**

For security reasons, Firebase credentials are NOT included in this
public repository. To run the project, you must provide your own
Firebase keys:

Python Gateway: Add your service_account.json to the root of the
Gateway_Python folder (it is ignored by Git).

Flutter App: Place your google-services.json in
smart_energy_consumption/android/app/ and your GoogleService-Info.plist
in smart_energy_consumption/ios/Runner/.

**3. Execution**

**Hardware & Gateway:**

1.  **Flash** the Arduinos with the respective ".ino" files.

2.  **Start the MQTT Broker** on the Raspberry Pi.

3.  **Run the Gateway**:
```python
python3 gateway_smart_home.py
```
**Mobile Dashboard:**

Navigate to the app directory:

```python
cd Mobile_App
```
Install the Flutter dependencies:

```python
flutter pub get
```
Run the application (ensure an emulator or physical device is
connected):

```python
flutter run
```

#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

#define ARDUINO_PIN 12

#define SERVICE_UUID "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"

BLEServer *pServer = NULL;
BLECharacteristic *pCharacteristic = NULL;

bool deviceConnected = false;
bool oldDeviceConnected = false;
bool dataReceived = false;

String receivedData = "";
String CODE = "1234";

//********************************************// SERVER CALLBACKS
class MyServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *pServer) {
    deviceConnected = true;
    Serial.println("Device Connected!");
  };

  void onDisconnect(BLEServer *pServer) {
    deviceConnected = false;
    Serial.println("Device Disconnected!");
  }
};
//********************************************// SERVER CALLBACKS

//********************************************// CHARACTERISTIC CALLBACKS
class MyCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *pCharacteristic) {
    String rxValue = pCharacteristic->getValue();

    if (rxValue.length() > 0) {
      receivedData = rxValue;
      dataReceived = true;
      receivedData.trim();
      Serial.print("Received: ");
      Serial.println(rxValue);
    }
  }
};
//********************************************// CHARACTERISTIC CALLBACKS


void setup() {
  Serial.begin(115200);

  // Create the BLE Device
  BLEDevice::init("ESP32-Room3(Gate)");

  // Create the BLE Server
  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());

  // Create the BLE Service
  BLEService *pService = pServer->createService(SERVICE_UUID);

  // Create a BLE Characteristic
  pCharacteristic = pService->createCharacteristic(
    CHARACTERISTIC_UUID,
    BLECharacteristic::PROPERTY_READ | 
    BLECharacteristic::PROPERTY_WRITE | 
    BLECharacteristic::PROPERTY_NOTIFY | 
    BLECharacteristic::PROPERTY_INDICATE);

  pCharacteristic->addDescriptor(new BLE2902());
  pCharacteristic->setCallbacks(new MyCallbacks());

  // Start the service
  pService->start();

  // Start advertising
  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setScanResponse(false);
  BLEDevice::startAdvertising();

  pinMode(ARDUINO_PIN, OUTPUT);
  digitalWrite(ARDUINO_PIN, LOW);

  Serial.println("BLE Smart Gate Ready...");
}

void loop() {
  if (dataReceived) {
    if(receivedData == CODE){
      Serial.println("Correct PIN");
      digitalWrite(ARDUINO_PIN, HIGH);
      delay(100);
    } else {
      Serial.println("Wrong PIN");
      pCharacteristic->setValue("ERROR");
      pCharacteristic->notify();
    }
    digitalWrite(ARDUINO_PIN, LOW);
    dataReceived = false;
    receivedData = "";
  }

  // notify changed value
  if (deviceConnected) {
    pCharacteristic->setValue("CONNECTED");
    pCharacteristic->notify();
    delay(500);
  }
  // disconnecting
  if (!deviceConnected && oldDeviceConnected) {
    delay(500);                   // Give the bluetooth stack the chance to get things ready
    pServer->startAdvertising();  // Restart advertising
    Serial.println("Restarting Advertising ...");
    oldDeviceConnected = deviceConnected;
  }
  // connecting
  if (deviceConnected && !oldDeviceConnected) {
    oldDeviceConnected = deviceConnected;
  }

  delay(50);  //Small delay for connection stability
}

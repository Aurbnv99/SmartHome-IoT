#include <Arduino.h>
#include <lmic.h>
#include <hal/hal.h>
#include <SPI.h>

//******************************************** LoRAWAN Parameters
static const PROGMEM u1_t NWKSKEY[16] = { 0xE9, 0xE9, 0xC0, 0x42, 0xF3, 0x33, 0x99, 0x41, 0xB8, 0x98, 0x71, 0x64, 0x6A, 0xF4, 0x1C, 0xBA };
static const u1_t PROGMEM APPSKEY[16] = { 0xF6, 0xAE, 0x41, 0xBB, 0x50, 0x0D, 0xB3, 0xEC, 0xA9, 0x75, 0x48, 0xAF, 0x9E, 0xB7, 0x1B, 0x8C };
static const u4_t DEVADDR = 0x260CAE55;

void os_getArtEui(u1_t* buf) {}
void os_getDevEui(u1_t* buf) {}
void os_getDevKey(u1_t* buf) {}

// Pinmap for Dragino Shield v1.4
const lmic_pinmap lmic_pins = {
  .nss = 10,
  .rxtx = LMIC_UNUSED_PIN,
  .rst = 9,
  .dio = { 2, 6, 7 },
};
//******************************************** LoRAWAN Parameters

#define PIR_PIN A0
#define LED_PIN 3
#define ESP_PIN A5

int lastESPstate = LOW;
int currentESPstate;

//******************************************** PIR + LIGHT
int valPIR = 0;
int calibrationTime = 2;         // the calibration time for the sensor (10-60 seconds)
long unsigned int lowIn;         // time when the sensor outputs a low pulse
long unsigned int pause = 2000;  // the number of milliseconds the output must be low
// it is assumed that there is no movement
boolean lockLow = true;
boolean takeLowTime;
//******************************************** PIR + LIGHT


void setup() {
  while (!Serial) {};
  Serial.begin(9600);
  delay(500);

  pinMode(PIR_PIN, INPUT);   // sets pirPin as INPUT
  pinMode(LED_PIN, OUTPUT);  // sets redledPin as OUTPUT
  pinMode(ESP_PIN, INPUT);
  digitalWrite(PIR_PIN, LOW);  // default, no movement

  //********************************************// LoRAWAN
  os_init();
  LMIC_reset();
  delay(500);

  uint8_t appskey[sizeof(APPSKEY)];
  uint8_t nwkskey[sizeof(NWKSKEY)];
  memcpy_P(appskey, APPSKEY, sizeof(APPSKEY));
  memcpy_P(nwkskey, NWKSKEY, sizeof(NWKSKEY));
  LMIC_setSession(0x13, DEVADDR, nwkskey, appskey);

  #if defined(CFG_us915)
    for (int c = 0; c < 72; c++) {
      LMIC_disableChannel(c);
    }
    LMIC_enableChannel(8); // Channel 8 (903.9 MHz)
  #endif
  
  #if defined(MAX_CLOCK_ERROR)
    LMIC_setClockError(MAX_CLOCK_ERROR * 20 / 100); // 20% tolerance window
  #endif
  
  LMIC_setDrTxpow(DR_SF7, 14);
  LMIC.dn2Freq = 923300000;
  LMIC.dn2Dr = 13;
  LMIC_setDrTxpow(DR_SF7, 14);
  LMIC_setLinkCheckMode(0);
  LMIC_setAdrMode(0);

  //********************************************// LoRAWAN


  Serial.println("Starting PIR sensor calibration ");  // Waiting for calibration
  for (int i = 0; i < calibrationTime; i++) {          // loop from 0 to the set calibration time
    Serial.print(".");
  }

  //delay(5000);
  Serial.println("Calibration done");
  Serial.println("PIR SENSOR ACTIVE");
  Serial.println("Waiting for commands from ESP32...");
  Serial.flush();

}//SETUP

void loop() {
  os_runloop_once(); // Internal LMIC timer and radio management

  // --- SERIAL MONITOR DEBUG INPUT ---
  if (Serial.available() > 0) {
    String debugMessage = Serial.readStringUntil('\n');
    debugMessage.trim(); // Removes accidental spaces or carriage returns

    if (debugMessage.length() > 0) {
      Serial.print(F("Manual input detected: "));
      Serial.println(debugMessage);
      sendLoRaWANData(debugMessage);
    }
  }

  //********************************************// ESP32 - BLE
  currentESPstate = digitalRead(ESP_PIN);

  if (currentESPstate == HIGH && lastESPstate == LOW) {
    Serial.println("Received from ESP32 the code");
    sendLoRaWANData("Garage Open");
  }
  lastESPstate = currentESPstate;
  //********************************************// ESP32 - BLE


  //********************************************// PIR + LIGHT
  valPIR = digitalRead(PIR_PIN);  // reads the state of the PIR sensor
  if (valPIR == HIGH) {
    digitalWrite(LED_PIN, HIGH);  // Turns LED ON
    if (lockLow) {
      lockLow = false;

      Serial.println("---");
      Serial.println("Movement detected");

      sendLoRaWANData("Motion_R3 = 1|Light_R3 = 1");
    }
    takeLowTime = true;
  }

  if (valPIR == LOW) {
    if (takeLowTime) {
      lowIn = millis();     // saves the time of the transition from high to LOW
      takeLowTime = false;  // ensures this happens only at the beginning of a LOW phase
    }
    // if the sensor is low for more than the indicated pause, we assume there are no more movements
    if (!lockLow && millis() - lowIn > pause) {
      // ensures this block of code is executed again only after
      lockLow = true;              // a new sequence of movements has been detected
      digitalWrite(LED_PIN, LOW);  // Turns LED OFF
      Serial.println("Movement ended ");

      sendLoRaWANData("Motion_R3 = 0|Light_R3 = 0");
    }
  }
  //********************************************// PIR + LIGHT

}//LOOP

//******************************************** LoRAWAN void Functions
void onEvent(ev_t ev) {
  switch (ev) {
    case EV_TXCOMPLETE:
      Serial.println(F("LoRAWAN: EV_TXCOMPLETE"));
      if (LMIC.txrxFlags & TXRX_ACK)
        Serial.println(F("Received ack"));
      if (LMIC.dataLen) {
        Serial.print(F("Received "));
        Serial.print(LMIC.dataLen);
        Serial.println(TXRX_PORT);
        Serial.println(F(" byte of payload."));

        Serial.print(F("HEX: "));
        for (int i = 0; i < LMIC.dataLen; i++) {
          if (LMIC.frame[LMIC.dataBeg + i] < 0x10) {
            Serial.print(F("0"));
          }
          Serial.print(LMIC.frame[LMIC.dataBeg + i], HEX);
          Serial.print(F(" "));
        }
        Serial.println();

        Serial.print(F("Text: "));
        for (int i = 0; i < LMIC.dataLen; i++) {
          Serial.print((char)LMIC.frame[LMIC.dataBeg + i]);
        }
        Serial.println();
      }
      break;
    case EV_RXCOMPLETE:
      // data received in ping slot
      Serial.println(F("EV_RXCOMPLETE"));
      break;
    default:
      Serial.println(F("Unknown event from LoRAWAN"));
      break;
  }
}

void sendLoRaWANData(String text) {
  // Check if the radio is already busy with another transmission
  if (LMIC.opmode & OP_TXRXPEND) {
    Serial.print(F("Radio busy! Packet lost in the air: "));
    Serial.println(text);
  } else {
    // Convert the dynamic string into a byte array for LMIC
    uint8_t dataBuffer[text.length() + 1];
    text.getBytes(dataBuffer, sizeof(dataBuffer));
    
    // Send on FPort 1, without requesting an ACK (final parameter is 0)
    LMIC_setTxData2(1, dataBuffer, text.length(), 0);
    
    Serial.print(F("LoRaWAN -> Packet queued successfully: "));
    Serial.println(text);
  }
}
//******************************************** LoRAWAN void Functions

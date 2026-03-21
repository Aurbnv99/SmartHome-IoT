#include <SoftwareSerial.h>
#include <LoRa_E220.h>
#include <Arduino.h>

#define PIR_PIN A0
#define LED_PIN 2
#define ESP_PIN 13

// QoS CONFIGURATION
#define MAX_RETRIES 3      // Maximum number of attempts
#define ACK_TIMEOUT 2000   // ACK wait time in milliseconds

SoftwareSerial mySerial(8, 10);         // Arduino RX <-- e220 TX, Arduino TX --> e220 RX
LoRa_E220 e220ttl(&mySerial, 4, 7, 6);  // AUX M0 M1

int lastESPstate = LOW;
int currentESPstate;

long unsigned int count;

//******************************************** PIR + LIGHT
int valPIR = 0;
int calibrationTime = 2;        // the calibration time for the sensor (10-60 seconds)
long unsigned int lowIn;         // time when the sensor outputs a low pulse
long unsigned int pause = 5000;  // the number of milliseconds the output must be low
// it is assumed that there is no movement
boolean lockLow = true;
boolean takeLowTime;
//******************************************** PIR + LIGHT

// QoS FUNCTION PROTOTYPE
void sendFixedMessageWithRetry(byte ADDH, byte ADDL, byte CHAN, String message);
void printParameters(struct Configuration configuration);

void setup() {

  pinMode(PIR_PIN, INPUT);   // sets pirPin as INPUT
  pinMode(LED_PIN, OUTPUT);  // sets redledPin as OUTPUT
  pinMode(ESP_PIN, INPUT);
  digitalWrite(PIR_PIN, LOW);  // default, no movement

  Serial.begin(9600);
  while (!Serial) {};
  delay(1000);

  e220ttl.begin();

  //********************************************// LORAWAN
  ResponseStructContainer c;
  c = e220ttl.getConfiguration();
  // It's important get configuration pointer before all other operation
  Configuration configuration = *(Configuration*)c.data;
  Serial.println(c.status.getResponseDescription());
  Serial.println(c.status.code);

  printParameters(configuration);

  c.close();
  
  // QoS MODIFICATION: Send with retry
  sendFixedMessageWithRetry(0, 1, 23, "Hello from ROOM_3 ");
  Serial.println("Start receiving LoRA!");
  //********************************************// LORAWAN


  Serial.println("Starting PIR sensor calibration ");  // Waiting for calibration
  for (int i = 0; i < calibrationTime; i++) {          // loop from 0 to the set calibration time
    Serial.print(".");
  }

  //delay(5000);
  Serial.println("Calibration done");
  Serial.println("PIR SENSOR ACTIVE");
  Serial.println("Waiting for commands from ESP32...");
  Serial.flush();
  mySerial.flush();

}  //SETUP

void loop() {
  //Debug LoRA
  // if (millis() - count > 1000) {
  //   ResponseStatus rs = e220ttl.sendFixedMessage(0, 1, 23, "ciao");
  //   Serial.println(rs.getResponseDescription());
  //   Serial.flush();
  //   delay(100);
  //   count = millis();
  // }


  //********************************************// LORAWAN
  if (e220ttl.available() > 0) {
    delay(100);
    ResponseContainer rc = e220ttl.receiveMessage();
    if (rc.status.code == 1) {
      Serial.print("Ricevuto: ");
      Serial.println(rc.data);

      String command = rc.data;
      command.toLowerCase();

      // If it's an ACK, we ignore it in the main loop (handled by the send function)
      if (command.indexOf("ack") >= 0) {
         Serial.println("ACK received outside cycle (late?)");
      }

      if (command.indexOf("r3") || command.indexOf("room3") >= 0 ) {
        if (command.indexOf("light") >= 0) {
          if (command.indexOf("off") >= 0) {
            digitalWrite(LED_PIN, LOW);
            Serial.println(" --> LIGHT OFF <-- ");
            // QoS MODIFICATION: Confirm command execution with retry
            sendFixedMessageWithRetry(0, 1, 23, "Light_R3 = 0"); //Back command to Gateway [OFF]
          } else if (command.indexOf("on") >= 0) {
            digitalWrite(LED_PIN, HIGH);
            Serial.println(" --> LIGHT ON <-- ");
            // QoS MODIFICATION: Confirm command execution with retry
            sendFixedMessageWithRetry(0, 1, 23, "Light_R3 = 1"); //Back command to Gateway [ON]
          } 
        }
      }
    } else {
      Serial.println(rc.status.getResponseDescription());
      Serial.println("Error");
    }
    Serial.flush();
    delay(100);
  }
  // Reads serial monitor on Arduino IDE to debug LoRA
  if (Serial.available()) {
    delay(100);
    String input = Serial.readStringUntil('\n');
    // QoS MODIFICATION: Manual debug with retry
    sendFixedMessageWithRetry(0, 1, 23, input);
    Serial.flush();
    delay(100);
  }
  //********************************************// LORAWAN

  //********************************************// ESP32 - BLE
  currentESPstate = digitalRead(ESP_PIN);

  if (currentESPstate == HIGH && lastESPstate == LOW) {
    Serial.println("Received from ESP32 the code");
    // QoS MODIFICATION: Send ESP trigger with retry
    sendFixedMessageWithRetry(0, 1, 23, "Code Received");
    delay(500);
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

      // QoS MODIFICATION: Notify movement with retry
      String packetMotion = "Motion_R3 = 1";
      sendFixedMessageWithRetry(0, 1, 23, packetMotion);
      Serial.print("Sent: ");
      Serial.println(packetMotion);

      String packetLight = "Light_R3 = 1";
      sendFixedMessageWithRetry(0, 1, 23, packetLight);
      // Debug
      Serial.print("Sent: ");
      Serial.println(packetLight);
      
      delay(50);
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

      // QoS MODIFICATION
      String packetMotion = "Motion_R3 = 0";
      sendFixedMessageWithRetry(0, 1, 23, packetMotion);
      Serial.print("Sent: ");
      Serial.println(packetMotion);

      String packetLight = "Light_R3 = 0";
      sendFixedMessageWithRetry(0, 1, 23, packetLight);
      // Debug
      Serial.print("Sent: ");
      Serial.println(packetLight);
      
      delay(50);
    }
  }
  //********************************************// PIR + LIGHT

}//LOOP


// ********************************************//NEW FUNCTION FOR QoS MANAGEMENT (ACK and RETRY)
void sendFixedMessageWithRetry(byte ADDH, byte ADDL, byte CHAN, String message) {
  bool ackReceived = false;
  int attempt = 1;

  while (attempt <= MAX_RETRIES && !ackReceived) {
    Serial.print("Sending msg: '");
    Serial.print(message);
    Serial.print("' - Attempt: ");
    Serial.print(attempt);
    Serial.print("/");
    Serial.println(MAX_RETRIES);

    // Actual transmission
    ResponseStatus rs = e220ttl.sendFixedMessage(ADDH, ADDL, CHAN, message);
    Serial.println(rs.getResponseDescription());

    mySerial.flush();

    // Wait for ACK
    unsigned long startWait = millis();
    while (millis() - startWait < ACK_TIMEOUT) {
      if (e220ttl.available() > 1) { // Check for incoming response
        ResponseContainer rc = e220ttl.receiveMessage();
        String response = rc.data;
        response.toLowerCase();

        // Check if the received message contains "ack"
        if (response.indexOf("ack") >= 0) {
          ackReceived = true;
          Serial.println(">> ACK RECEIVED! Transmission OK.");
          break; // Exit the wait loop
        } else {
           // Optional: If a command is received while waiting for ACK, log it
           Serial.print(">> Received non-ACK data during wait: ");
           Serial.println(response);
        }
      }
    }

    if (!ackReceived) {
      Serial.println(">> No ACK received. Timeout.");
      attempt++;
      if (attempt <= MAX_RETRIES) {
        Serial.println(">> Retrying in 500ms...");
        delay(500); // Brief pause before next attempt
      } else {
        Serial.println(">> ERROR: Maximum retries reached. Message LOST.");
      }
    }
  }
}
// ********************************************//NEW FUNCTION FOR QoS MANAGEMENT (ACK and RETRY)

//LORAWAN GET-CONFIGURATION CLASS
void printParameters(struct Configuration configuration) {
  Serial.println("----------------------------------------");

  Serial.print(F("HEAD : "));
  Serial.print(configuration.COMMAND, HEX);
  Serial.print(" ");
  Serial.print(configuration.STARTING_ADDRESS, HEX);
  Serial.print(" ");
  Serial.println(configuration.LENGHT, HEX);
  Serial.println(F(" "));
  Serial.print(F("AddH : "));
  Serial.println(configuration.ADDH, HEX);
  Serial.print(F("AddL : "));
  Serial.println(configuration.ADDL, HEX);
  Serial.println(F(" "));
  Serial.print(F("Chan : "));
  Serial.print(configuration.CHAN, DEC);
  Serial.print(" -> ");
  Serial.println(configuration.getChannelDescription());
  Serial.println(F(" "));
  Serial.print(F("SpeedParityBit     : "));
  Serial.print(configuration.SPED.uartParity, BIN);
  Serial.print(" -> ");
  Serial.println(configuration.SPED.getUARTParityDescription());
  Serial.print(F("SpeedUARTDatte     : "));
  Serial.print(configuration.SPED.uartBaudRate, BIN);
  Serial.print(" -> ");
  Serial.println(configuration.SPED.getUARTBaudRateDescription());
  Serial.print(F("SpeedAirDataRate   : "));
  Serial.print(configuration.SPED.airDataRate, BIN);
  Serial.print(" -> ");
  Serial.println(configuration.SPED.getAirDataRateDescription());
  Serial.println(F(" "));
  Serial.print(F("OptionSubPacketSett: "));
  Serial.print(configuration.OPTION.subPacketSetting, BIN);
  Serial.print(" -> ");
  Serial.println(configuration.OPTION.getSubPacketSetting());
  Serial.print(F("OptionTranPower    : "));
  Serial.print(configuration.OPTION.transmissionPower, BIN);
  Serial.print(" -> ");
  Serial.println(configuration.OPTION.getTransmissionPowerDescription());
  Serial.print(F("OptionRSSIAmbientNo: "));
  Serial.print(configuration.OPTION.RSSIAmbientNoise, BIN);
  Serial.print(" -> ");
  Serial.println(configuration.OPTION.getRSSIAmbientNoiseEnable());
  Serial.println(F(" "));
  Serial.print(F("TransModeWORPeriod : "));
  Serial.print(configuration.TRANSMISSION_MODE.WORPeriod, BIN);
  Serial.print(" -> ");
  Serial.println(configuration.TRANSMISSION_MODE.getWORPeriodByParamsDescription());
  Serial.print(F("TransModeEnableLBT : "));
  Serial.print(configuration.TRANSMISSION_MODE.enableLBT, BIN);
  Serial.print(" -> ");
  Serial.println(configuration.TRANSMISSION_MODE.getLBTEnableByteDescription());
  Serial.print(F("TransModeEnableRSSI: "));
  Serial.print(configuration.TRANSMISSION_MODE.enableRSSI, BIN);
  Serial.print(" -> ");
  Serial.println(configuration.TRANSMISSION_MODE.getRSSIEnableByteDescription());
  Serial.print(F("TransModeFixedTrans: "));
  Serial.print(configuration.TRANSMISSION_MODE.fixedTransmission, BIN);
  Serial.print(" -> ");
  Serial.println(configuration.TRANSMISSION_MODE.getFixedTransmissionDescription());
  Serial.println("----------------------------------------");
}  //LORAWAN GET-CONFIGURATION CLASS

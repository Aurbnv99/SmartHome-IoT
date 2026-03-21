#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME280.h>
#include <Adafruit_TSL2561_U.h>
#include <SoftwareSerial.h>


const String ROOM_ID = "R2";

SoftwareSerial Xbee(10, 11);
Adafruit_TSL2561_Unified tsl = Adafruit_TSL2561_Unified(TSL2561_ADDR_FLOAT, 12345);
Adafruit_BME280 bme;

char incomingByte;
unsigned status;

//******************************************** PIR + LIGHT
const char PIR_PIN = A0;
const int LED_PIN = 13;
int valPIR = 0;
int calibrationTime = 2;        // the calibration time for the sensor (10-60 seconds)
long unsigned int lowIn;         // time when the sensor outputs a low pulse
long unsigned int pause = 2000;  // the number of milliseconds the output must be low
// it is assumed that there is no movement
boolean lockLow = true;
boolean takeLowTime;
//******************************************** PIR + LIGHT

long unsigned int count;  // Counter made for sending parameter every 1 second [TX Debug Zigbee]

//******************************************** L298N [RELAYS]
// Motor ROOM1 connections
const int enA = 9;
const int in1 = 8;
const int in2 = 7;
// Motor B connections
const int enB = 3;
const int in3 = 5;
const int in4 = 4;

const int SPEED_LOW = 53;
const int SPEED_MID = 58;
const int SPEED_HIGH = 62;
//******************************************** L298N [RELAYS]

String inputString = "";
boolean stringComplete = false;

void setup(void) {
  Serial.begin(9600);
  while (!Serial) {};
  stopMotors();
  delay(1000);

  Xbee.begin(9600);

  status = bme.begin(0x76);
  if (!status) {
    Serial.println("Could not find a valid BME280 sensor, check wiring, address, sensor ID!");
    Serial.print("SensorID was: 0x");
    Serial.println(bme.sensorID(), 16);
    while (1) delay(10);
  }
  Serial.println("BME280 OK");

  /* Initialise the Luminority sensor */
  if (!tsl.begin()) {
    /* There was a problem detecting the TSL2561 ... check your connections */
    Serial.print("Ooops, no TSL2561 detected ... Check your wiring or I2C ADDR!");
    while (1) delay(10);
    ;
  }
  Serial.println("TSL OK");

  /* Display some basic information on this sensor */
  //displaySensorDetails();
  /* Setup the sensor gain and integration time */
  configureSensor();

  Serial.println("Starting PIR sensor calibration ");  // Waiting for calibration
  for (int i = 0; i < calibrationTime; i++) {          // loop from 0 to the set calibration time
    Serial.print(".");
    delay(1000);  // sets 1 second delay
  }

  pinMode(LED_PIN, OUTPUT);
  pinMode(PIR_PIN, INPUT);
  digitalWrite(PIR_PIN, LOW);

  //MotorROOM2 [Heater]
  pinMode(enA, OUTPUT);
  pinMode(in1, OUTPUT);
  pinMode(in2, OUTPUT);
  stopMotors();

  Xbee.println("Hello from ROOM_2 ");
  delay(1000);
}


void loop(void) {
  sensors_event_t event;
  tsl.getEvent(&event);

  // Sending Temp:Hum:Press every 30 seconds
  if (millis() - count > 30000) {
    String packetTemp = ROOM_ID;
    packetTemp += ":";
    packetTemp += String(bme.readTemperature(), 1);
    packetTemp += ":";
    packetTemp += String(bme.readHumidity(), 1);
    packetTemp += ":";
    packetTemp += String((bme.readPressure() / 100.0F), 1);
    Xbee.println(packetTemp);
    count = millis();
    Serial.println(packetTemp);
  }

  //********************************************// RELAY MANAGEMENT
  while (Xbee.available()) {
    char inChar = (char)Xbee.read();

    if (inChar == '\n') {
      stringComplete = true;
    } else {
      inputString += inChar;
    }
  }

  if (stringComplete) {
    Serial.println("Ricevuto: " + inputString); // Debug
    parseCommand(inputString);
    inputString = "";
    stringComplete = false;
  }
  //********************************************// RELAY MANAGEMENT


  //********************************************// PIR + LIGHT
  valPIR = digitalRead(PIR_PIN);

  // If motion is detected
  if (valPIR == HIGH) {
    if (lockLow) {
      lockLow = false;

      Serial.println("---");
      Serial.println("Movement detected");
      
      // Send Motion to Gateway
      String packetMotion = "Motion_R1 = 1";
      Xbee.println(packetMotion); 
      Serial.print("Sent: ");
      Serial.println(packetMotion);

      // Turn on the light only if is dark inside
      if (event.light < 400) {
        digitalWrite(LED_PIN, HIGH);
        String packetLight = "Light_R1 = 1";
        Xbee.println(packetLight); 
        Serial.print("Sent: "); //Debug
        Serial.println(packetLight);
      }

      delay(50);
    }
    takeLowTime = true;
  }

  // If there is no motion
  if (valPIR == LOW) {
    if (takeLowTime) {
      lowIn = millis();     // saves the transition time from HIGH to LOW
      takeLowTime = false;  // ensures this happens only at the beginning of the LOW phase
    }
    
    // if the sensor is low for more than the indicated pause, we assume there are no more movements
    if (!lockLow && millis() - lowIn > pause) {
      // ensures this block of code is executed again only after
      lockLow = true; // a new sequence of movements has been detected
      Serial.println("Movement ended");

      // Send message of No Motion
      String packetMotion = "Motion_R1 = 0";
      Xbee.println(packetMotion);
      Serial.print("Sent: ");
      Serial.println(packetMotion);

      digitalWrite(LED_PIN, LOW);  // Turns LED OFF
      String packetLight = "Light_R1 = 0";
      Xbee.println(packetLight);
      Serial.print("Sent: ");
      Serial.println(packetLight);

      delay(50);
    }
  }
  //********************************************// PIR + LIGHT

    //********************************************// SERIAL MONITOR DEBUG (MANUAL COMMANDS)
  // Allows sending commands directly from the Arduino IDE Serial Monitor
  if (Serial.available()) {
    String debugCommand = Serial.readStringUntil('\n');
    Serial.println("Manual Input: " + debugCommand);
    parseCommand(debugCommand); // Reuse the same logic used for Xbee commands
  }
  //********************************************// SERIAL MONITOR DEBUG (MANUAL COMMANDS)
}

void displaySensorDetails(void) {
  sensor_t sensor;
  tsl.getSensor(&sensor);
  Serial.println("------------------------------------");
  Serial.print("Sensor:       ");
  Serial.println(sensor.name);
  Serial.print("Driver Ver:   ");
  Serial.println(sensor.version);
  Serial.print("Unique ID:    ");
  Serial.println(sensor.sensor_id);
  Serial.print("Max Value:    ");
  Serial.print(sensor.max_value);
  Serial.println(" lux");
  Serial.print("Min Value:    ");
  Serial.print(sensor.min_value);
  Serial.println(" lux");
  Serial.print("Resolution:   ");
  Serial.print(sensor.resolution);
  Serial.println(" lux");
  Serial.println("------------------------------------");
  Serial.println("");
  delay(500);
}

void configureSensor(void) {
  /* You can also manually set the gain or enable auto-gain support */
  // tsl.setGain(TSL2561_GAIN_1X);      /* No gain ... use in bright light to avoid sensor saturation */
  tsl.setGain(TSL2561_GAIN_16X); /* 16x gain ... use in low light to boost sensitivity */
  //tsl.enableAutoRange(true);            /* Auto-gain ... switches automatically between 1x and 16x */

  /* Changing the integration time gives you better sensor resolution (402ms = 16-bit data) */
  tsl.setIntegrationTime(TSL2561_INTEGRATIONTIME_101MS); /* fast but low resolution */
  // tsl.setIntegrationTime(TSL2561_INTEGRATIONTIME_101MS);  /* medium resolution and speed   */
  // tsl.setIntegrationTime(TSL2561_INTEGRATIONTIME_402MS);  /* 16-bit data but slowest conversions */
}

//********************************************// RELAY MANAGEMENT
void stopMotors() {
  analogWrite(enA, 0);
  analogWrite(enB, 0);

  digitalWrite(in1, LOW);
  digitalWrite(in2, LOW);
  digitalWrite(in3, LOW);
  digitalWrite(in4, LOW);
}

void parseCommand(String command) {
  // Cleanup and standardization
  command.trim();  
  command.toLowerCase();

  // Room ID Verification ("r1" or "room1")
  if (command.indexOf("r2") == -1 && command.indexOf("room2") == -1) {
    return;
  }

  // Heater Commands
  if (command.indexOf("heater") >= 0) {
    if (command.indexOf("off") >= 0) {
      stopMotors();
      Serial.println(" --> HEATER OFF <-- ");
      Xbee.println("Heater_R2 = 0");        //Back command to Gateway [OFF]
    } else if (command.indexOf("on") >= 0) {
      digitalWrite(in1, LOW);
      digitalWrite(in2, HIGH);
      analogWrite(enA, SPEED_HIGH);
      Serial.print(" --> HEATER ON at HIGH <-- ");
      Serial.println(SPEED_HIGH);
      Xbee.println("Heater_R2 = 1");        //Back command to Gateway [ON]
    }
    return;
  }
  
  // Light Commands
  if (command.indexOf("light") >= 0) {
    if (command.indexOf("off") >= 0) {
      digitalWrite(LED_PIN, LOW);
      Serial.println(" --> LIGHT OFF <-- "); 
      Xbee.println("Light_R2 = 0");         //Back command to Gateway [OFF]
    } else if (command.indexOf("on") >= 0) {
      digitalWrite(LED_PIN, HIGH);
      Serial.println(" --> LIGHT ON <-- "); 
      Xbee.println("Light_R2 = 1");         //Back command to Gateway [ON]
    }  
    return;
  }

  // // Determine Direction (Heating or Cooling)
  // // Searching for lowercase keywords to match the standardized string
  // bool isCool = (command.indexOf("cooler") >= 0);
  // bool isHeat = (command.indexOf("heater") >= 0);

  // // If the Gateway AI sends only "on" during emergency, default to HEATER
  // if (command.indexOf("on") >= 0 && !isCool && !isHeat) {
  //     isHeat = true; 
  // }

  // // If neither cooling nor heating is requested, exit
  // if (!isCool && !isHeat) {
  //     return;
  // }

  // // Extract Speed (PWM Management)
  // // Defaulting to HIGH if the Gateway AI does not specify speed
  // int pwmValue = SPEED_HIGH; 
  
  // if (command.indexOf("low") >= 0) {
  //     pwmValue = SPEED_LOW;
  // } else if (command.indexOf("mid") >= 0) {
  //     pwmValue = SPEED_MID;
  // } else if (command.indexOf("high") >= 0) {
  //     pwmValue = SPEED_HIGH;
  // }

  // // Drive Motor (L298N H-Bridge)
  // if (isCool) {
  //   // Set direction for Cooling
  //   digitalWrite(in1, HIGH);
  //   digitalWrite(in2, LOW);
  //   analogWrite(enA, pwmValue);
  //   Serial.print(" Executed: COOLER at PWM: ");
  //   Serial.println(pwmValue);
  // } else if (isHeat) {
  //   // Set direction for Heating
  //   digitalWrite(in1, LOW);
  //   digitalWrite(in2, HIGH);
  //   analogWrite(enA, pwmValue);
  //   Serial.print(" Executed: HEATER at PWM: ");
  //   Serial.println(pwmValue);
  // }

}
//********************************************// RELAY MANAGEMENT

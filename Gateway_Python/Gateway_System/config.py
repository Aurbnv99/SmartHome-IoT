SIMULATION_MODE = False  

## ******************************************** MQTT
MQTT_BROKER = "localhost"
MQTT_PORT = 1883

TOPIC_COMMAND_SUB = "home/+/command"
TOPIC_STATUS = "home/status"
TOPIC_GET_STATUS = "home/get_status"

## ******************************************** SERIAL PORTS 
# CHECK THESE on Pi if not working (ls /dev/tty*)
ZIGBEE_PORT = "/dev/ttyUSB0"  
LORA_PORT = "/dev/ttyAMA0"
BAUDRATE = 9600
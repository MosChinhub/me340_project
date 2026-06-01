import RPi.GPIO as GPIO
import time, json

from functools import partial
from sensor import (sensor_names, sensor_counts, ir_sensor_callback)

def main(jsonpath: str):
    SENSOR_1 = 17  # GPIO 17 (Pin 11)
    SENSOR_2 = 27  # GPIO 27 (Pin 13)

    # Load counts from JSON file
    try:
        with open(jsonpath, "r") as f:
            sensor_counts.update(json.load(f))
    except FileNotFoundError:
        raise ValueError (f"{jsonpath} not found. Upload {jsonpath}.")

    #------------------------------------------------------
    # Pin setup
    #------------------------------------------------------

    sensor_names[SENSOR_1] = "Sensor 1"
    sensor_names[SENSOR_2] = "Sensor 2"

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(SENSOR_1, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(SENSOR_2, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    #------------------------------------------------------
    # Detect both rising and falling edge
    #------------------------------------------------------

    GPIO.add_event_detect(
        SENSOR_1, 
        GPIO.BOTH, 
        callback=partial(ir_sensor_callback, savepath=jsonpath),
        bouncetime=20)
    GPIO.add_event_detect(
        SENSOR_2,
        GPIO.BOTH,
        callback=partial(ir_sensor_callback, savepath=jsonpath),
        bouncetime=20)

    print("Monitoring IR sensors... Press CTRL+C to stop")

    try:
        while True:
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nStopped.")

    finally:
        GPIO.cleanup()

if __name__ == '__main__':
    ir_data_json ="ir_data.json"
    main(jsonpath=ir_data_json)
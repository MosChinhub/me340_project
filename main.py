import RPi.GPIO as GPIO
import time, json
from pathlib import Path

from functools import partial
from sensor import (sensor_names, sensor_counts, ir_sensor_callback, load_sensor_config,create_data_json)

def main(jsonpath: str, configpath: str):
    configured_sensors = load_sensor_config(configpath)

    if not Path(jsonpath).exists():
        create_data_json(configured_sensors,jsonpath)


    # Load counts from JSON file
    try:
        with open(jsonpath, "r") as f:
            sensor_counts.update(json.load(f))
    except FileNotFoundError:
        raise ValueError (f"{jsonpath} not found. Upload {jsonpath}.")

    #------------------------------------------------------
    # Pin setup
    #------------------------------------------------------

    GPIO.setmode(GPIO.BCM)

    for name, pin in configured_sensors.items():
        sensor_names[pin] = name
        sensor_counts.setdefault(name, 0)
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    #------------------------------------------------------
    # Detect both rising and falling edge
    #------------------------------------------------------

    for pin in configured_sensors.values():
        GPIO.add_event_detect(
            pin,
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
    ir_data_json = "data.json"
    config_json = "config.json"
    main(jsonpath=ir_data_json, configpath=config_json)

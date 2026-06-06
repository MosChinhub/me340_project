import json
import time
import threading
from pathlib import Path
from functools import partial
 
import RPi.GPIO as GPIO
 
from sensor import (
    sensor_names,
    sensor_counts,
    ir_sensor_callback,
    load_sensor_config,
    create_data_json,
    reset_counts,
)
from display import WouldYouRatherDisplay
 
# ─────────────────────────────────────────────
#  Paths
# ─────────────────────────────────────────────
DATA_PATH   = "data.json"
CONFIG_PATH = "config.json"
SCORES_PATH = "scores.json"
 
 
def run_gpio(jsonpath: str, configpath: str):
    configured_sensors = load_sensor_config(configpath)

    if not Path(jsonpath).exists():
        create_data_json(configured_sensors, jsonpath)

    try:
        with open(jsonpath, "r") as f:
            sensor_counts.update(json.load(f))
    except FileNotFoundError:
        raise ValueError(f"{jsonpath} not found.")

    GPIO.setmode(GPIO.BCM)

    for name, pin in configured_sensors.items():
        sensor_names[pin] = name
        sensor_counts.setdefault(name, 0)
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # Track last state for each pin
    last_states = {pin: GPIO.input(pin) for pin in configured_sensors.values()}

    print("Monitoring IR sensors... Press CTRL+C to stop")

    try:
        while True:
            for pin in configured_sensors.values():
                current = GPIO.input(pin)
                if current != last_states[pin]:
                    if current == GPIO.LOW:  # falling = beam broken = vote
                        ir_sensor_callback(pin, savepath=jsonpath)
                    last_states[pin] = current
            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        GPIO.cleanup()
 
 
def main():
    # ── Run GPIO loop in background thread ───
    if not Path(SCORES_PATH).exists():
        with open(SCORES_PATH,"w") as f:
            json.dump({},f, indent=4)

    gpio_thread = threading.Thread(
        target=run_gpio,
        args=(DATA_PATH, CONFIG_PATH),
        daemon=True,   # dies automatically when main thread exits
    )
    gpio_thread.start()
 
    # ── Run pygame display on main thread ────
    # (pygame must run on the main thread on most platforms)
    display = WouldYouRatherDisplay(
        reset_counts_callback=partial(reset_counts, DATA_PATH)
    )
    display.run()
 
 
if __name__ == "__main__":
    main()

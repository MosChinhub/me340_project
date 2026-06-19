import RPi.GPIO as GPIO
import json
import threading

sensor_names = {}
sensor_counts = {}
_save_lock = threading.Lock() # prevent save and reset at same time 

def save_counts(path:str):
    with _save_lock:
        with open(path,"w") as f:
            json.dump(sensor_counts, f)

def reset_counts(path: str, fresh_counts: dict[str, int]):
    with _save_lock:
        sensor_counts.clear()
        sensor_counts.update(fresh_counts)
        with open(path, "w") as f:
            json.dump(sensor_counts, f, indent=4)

def load_sensor_config(configpath: str, configkey: str) -> dict[str, int]:
    '''
    input: configpath, configkey: each type in config
    return dict inside each configkey
    '''
    try:
        with open(configpath, "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        raise ValueError(f"{configpath} not found. Create {configpath}.")

    sensors = config.get(configkey)
    if not isinstance(sensors, dict) or not sensors:
        raise ValueError(f"{configpath} must contain a non-empty 'sensors' object.")

    sensor_pins = {}
    for name, pin in sensors.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Each sensor name must be a non-empty string.")
        if not isinstance(pin, int):
            raise ValueError(f"GPIO pin for {name!r} must be an integer.")

        sensor_pins[name] = pin
    
    #return dic in config.json
    return sensor_pins

def create_data_json(sensor: dict,data_path: json):
    sensor_data={}

    for name, pin in sensor.items():
        sensor_data[name] = 0
    
    with open("ir_data.json", "w") as json_file:
        json.dump(sensor_data, json_file, indent=4)
        sensor_data={}

    for name, pin in sensor.items():
        sensor_data[name] = 0
    
    with open(data_path, "w") as json_file:
        json.dump(sensor_data, json_file, indent=4)

def ir_sensor_callback(channel, savepath):
    name = sensor_names.get(channel, f"GPIO {channel}")
    sensor_counts[name] = sensor_counts.get(name, 0) + 1
    print(f"{name}: Vote! Count = {sensor_counts[name]}")
    save_counts(path=savepath)

if __name__=='__main__':
    config_json = "config.json"
    sensor = load_sensor_config(configpath=config_json)
    print(sensor)
    for name, pin in sensor:
        print(name, pin)


import RPi.GPIO as GPIO
import json

sensor_names = {}
sensor_counts = {}

def save_counts(path:str):
    with open(path,"w") as f:
        json.dump(sensor_counts, f)

def ir_sensor_callback(channel,savepath):
    #channel is sensor gpio _
    name = sensor_names.get(channel, f"GPIO {channel}")

    if not GPIO.input(channel): #beam broken (obj between)

        sensor_counts[name] = sensor_counts.get(name, 0) + 1
        print(
            f"{name}: Object between beam!"
            f"Count = {sensor_counts[name]}"
        )

        save_counts(path=savepath)

    else:
        print(f"{name}: Beam Restored ")




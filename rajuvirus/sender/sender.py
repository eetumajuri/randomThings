import requests
from pynput import mouse


SERVER = "http://192.168.100.17:8000/event"

DEVICE_ID = "computer_001"


def send_event(data):

    try:

        response = requests.post(
            SERVER,
            json=data,
            timeout=3
        )

        print("Server:", response.json())


    except Exception as e:

        print("Virhe:", e)



def on_click(x, y, button, pressed):

    if pressed:

        event = {

            "device_id": DEVICE_ID,

            "type": "click",

            "x": x,

            "y": y,

            "button": str(button)

        }


        print("Klikkaus:", event)

        send_event(event)



print("Client käynnissä")
print("Kaikki klikkaukset lähetetään")


with mouse.Listener(
    on_click=on_click
) as listener:

    listener.join()

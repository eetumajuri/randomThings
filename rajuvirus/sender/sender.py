import requests


macro = {
    "device_id": "computer_001",

    "name": "oma ensimmäinen makro",

    "actions": [
        {
            "type": "click",
            "x": 500,
            "y": 300
        },
        {
            "type": "keypress",
            "key": "ENTER"
        }
    ]
}

response = requests.post(
    "http://192.168.57.2:8000/save_macro",
    json=macro
)


print(response.json())

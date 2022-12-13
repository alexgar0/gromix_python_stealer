#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Based on original work from: www.dumpzilla.org

from __future__ import annotations


import ctypes as ct
import json
import locale
import os
import platform
import sys
import shutil
from base64 import b64decode
from getpass import getpass
from subprocess import run, PIPE, DEVNULL

VERBOSE = False
SYSTEM = platform.system()
SYS64 = sys.maxsize > 2**32
DEFAULT_ENCODING = "utf-8"

PWStore = list[dict[str, str]]

# NOTE: In 1.0.0-rc1 we tried to use locale information to encode/decode
# content passed to NSS. This was an attempt to address the encoding issues
# affecting Windows. However after additional testing Python now also defaults
# to UTF-8 for encoding.
# Some of the limitations of Windows have to do with poor support for UTF-8
# characters in cmd.exe. Terminal - https://github.com/microsoft/terminal or
# a Bash shell such as Git Bash - https://git-scm.com/downloads are known to
# provide a better user experience and are therefore recommended


def get_version() -> str:
    """Obtain version information from git if available otherwise use
    the internal version number
    """
    def internal_version():
        return '.'.join(map(str, __version_info__[:3])) + ''.join(__version_info__[3:])

    try:
        p = run(["git", "describe", "--tags"], stdout=PIPE, stderr=DEVNULL, text=True)
    except FileNotFoundError:
        return internal_version()

    if p.returncode:
        return internal_version()
    else:
        return p.stdout.strip()


__version_info__ = (1, 0, 0, "+git")
__version__: str = get_version()


class NotFoundError(Exception):
    """Exception to handle situations where a credentials file is not found
    """
    pass


class Exit(Exception):
    """Exception to allow a clean exit from any point in execution
    """
    CLEAN = 0
    ERROR = 1
    MISSING_PROFILEINI = 2
    MISSING_SECRETS = 3
    BAD_PROFILEINI = 4
    LOCATION_NO_DIRECTORY = 5
    BAD_SECRETS = 6
    BAD_LOCALE = 7

    FAIL_LOCATE_NSS = 10
    FAIL_LOAD_NSS = 11
    FAIL_INIT_NSS = 12
    FAIL_NSS_KEYSLOT = 13
    FAIL_SHUTDOWN_NSS = 14
    BAD_MASTER_PASSWORD = 15
    NEED_MASTER_PASSWORD = 16

    PASSSTORE_NOT_INIT = 20
    PASSSTORE_MISSING = 21
    PASSSTORE_ERROR = 22

    READ_GOT_EOF = 30
    MISSING_CHOICE = 31
    NO_SUCH_PROFILE = 32

    UNKNOWN_ERROR = 100
    KEYBOARD_INTERRUPT = 102

    def __init__(self, exitcode):
        self.exitcode = exitcode

    def __unicode__(self):
        return f"Premature program exit with exit code {self.exitcode}"


class Credentials:
    """Base credentials backend manager
    """
    def __init__(self, db):
        self.db = db

        if not os.path.isfile(db):
            raise NotFoundError(f"ERROR - {db} database not found\n")


    def __iter__(self) -> Iterator[tuple[str, str, str, int]]:
        pass

    def done(self):
        """Override this method if the credentials subclass needs to do any
        action after interaction
        """
        pass


class SqliteCredentials(Credentials):
    """SQLite credentials backend manager
    """
    def __init__(self, profile):
        db = os.path.join(profile, "signons.sqlite")

        super(SqliteCredentials, self).__init__(db)

        self.conn = sqlite3.connect(db)
        self.c = self.conn.cursor()

    def __iter__(self) -> Iterator[tuple[str, str, str, int]]:
        self.c.execute("SELECT hostname, encryptedUsername, encryptedPassword, encType "
                       "FROM moz_logins")
        for i in self.c:
            # yields hostname, encryptedUsername, encryptedPassword, encType
            yield i

    def done(self):
        """Close the sqlite cursor and database connection
        """
        super(SqliteCredentials, self).done()

        self.c.close()
        self.conn.close()


class JsonCredentials(Credentials):
    """JSON credentials backend manager
    """
    def __init__(self, profile):
        db = os.path.join(profile, "logins.json")

        super(JsonCredentials, self).__init__(db)

    def __iter__(self) -> Iterator[tuple[str, str, str, int]]:
        with open(self.db) as fh:
            data = json.load(fh)

            try:
                logins = data["logins"]
            except Exception:
                raise Exit(Exit.BAD_SECRETS)

            for i in logins:
                yield (i["hostname"], i["encryptedUsername"],
                       i["encryptedPassword"], i["encType"])


def find_nss(locations, nssname) -> ct.CDLL:
    """Locate nss is one of the many possible locations
    """
    fail_errors: list[tuple[str, str]] = []

    OS = ("Windows", "Darwin")

    for loc in locations:
        nsslib = os.path.join(loc, nssname)

        if SYSTEM in OS:
            # On windows in order to find DLLs referenced by nss3.dll
            # we need to have those locations on PATH
            os.environ["PATH"] = ';'.join([loc, os.environ["PATH"]])
            # However this doesn't seem to work on all setups and needs to be
            # set before starting python so as a workaround we chdir to
            # Firefox's nss3.dll/libnss3.dylib location
            if loc:
                if not os.path.isdir(loc):
                    # No point in trying to load from paths that don't exist
                    continue

                workdir = os.getcwd()
                os.chdir(loc)

        try:
            nss: ct.CDLL = ct.CDLL(nsslib)
        except OSError as e:
            fail_errors.append((nsslib, str(e)))
        else:
            return nss
        finally:
            if SYSTEM in OS and loc:
                # Restore workdir changed above
                os.chdir(workdir)

    else:
        raise Exit(Exit.FAIL_LOCATE_NSS)


def load_libnss():
    """Load libnss into python using the CDLL interface
    """
    if SYSTEM == "Windows":
        nssname = "nss3.dll"
        locations: list[str] = [
            "",  # Current directory or system lib finder
            os.path.expanduser("~\\AppData\\Local\\Mozilla Firefox"),
            os.path.expanduser("~\\AppData\\Local\\Firefox Developer Edition"),
            os.path.expanduser("~\\AppData\\Local\\Mozilla Thunderbird"),
            os.path.expanduser("~\\AppData\\Local\\Nightly"),
            os.path.expanduser("~\\AppData\\Local\\SeaMonkey"),
            os.path.expanduser("~\\AppData\\Local\\Waterfox"),
            "C:\\Program Files\\Mozilla Firefox",
            "C:\\Program Files\\Firefox Developer Edition",
            "C:\\Program Files\\Mozilla Thunderbird",
            "C:\\Program Files\\Nightly",
            "C:\\Program Files\\SeaMonkey",
            "C:\\Program Files\\Waterfox",
        ]
        if not SYS64:
            locations = [
                "",  # Current directory or system lib finder
                "C:\\Program Files (x86)\\Mozilla Firefox",
                "C:\\Program Files (x86)\\Firefox Developer Edition",
                "C:\\Program Files (x86)\\Mozilla Thunderbird",
                "C:\\Program Files (x86)\\Nightly",
                "C:\\Program Files (x86)\\SeaMonkey",
                "C:\\Program Files (x86)\\Waterfox",
            ] + locations

        # If either of the supported software is in PATH try to use it
        software = ["firefox", "thunderbird", "waterfox", "seamonkey"]
        for binary in software:
            location: Optional[str] = shutil.which(binary)
            if location is not None:
                nsslocation: str = os.path.join(os.path.dirname(location), nssname)
                locations.append(nsslocation)

    elif SYSTEM == "Darwin":
        nssname = "libnss3.dylib"
        locations = (
            "",  # Current directory or system lib finder
            "/usr/local/lib/nss",
            "/usr/local/lib",
            "/opt/local/lib/nss",
            "/sw/lib/firefox",
            "/sw/lib/mozilla",
            "/usr/local/opt/nss/lib",  # nss installed with Brew on Darwin
            "/opt/pkg/lib/nss",  # installed via pkgsrc
            "/Applications/Firefox.app/Contents/MacOS",  # default manual install location
            "/Applications/Thunderbird.app/Contents/MacOS",
            "/Applications/SeaMonkey.app/Contents/MacOS",
            "/Applications/Waterfox.app/Contents/MacOS",
        )

    else:
        nssname = "libnss3.so"
        if SYS64:
            locations = (
                "",  # Current directory or system lib finder
                "/usr/lib64",
                "/usr/lib64/nss",
                "/usr/lib",
                "/usr/lib/nss",
                "/usr/local/lib",
                "/usr/local/lib/nss",
                "/opt/local/lib",
                "/opt/local/lib/nss",
                os.path.expanduser("~/.nix-profile/lib"),
            )
        else:
            locations = (
                "",  # Current directory or system lib finder
                "/usr/lib",
                "/usr/lib/nss",
                "/usr/lib32",
                "/usr/lib32/nss",
                "/usr/lib64",
                "/usr/lib64/nss",
                "/usr/local/lib",
                "/usr/local/lib/nss",
                "/opt/local/lib",
                "/opt/local/lib/nss",
                os.path.expanduser("~/.nix-profile/lib"),
            )

    # If this succeeds libnss was loaded
    return find_nss(locations, nssname)


class c_char_p_fromstr(ct.c_char_p):
    """ctypes char_p override that handles encoding str to bytes"""
    def from_param(self):
        return self.encode(DEFAULT_ENCODING)


class NSSProxy:
    class SECItem(ct.Structure):
        """struct needed to interact with libnss
        """
        _fields_ = [
            ('type', ct.c_uint),
            ('data', ct.c_char_p),  # actually: unsigned char *
            ('len', ct.c_uint),
        ]

        def decode_data(self):
            _bytes = ct.string_at(self.data, self.len)
            return _bytes.decode(DEFAULT_ENCODING)

    class PK11SlotInfo(ct.Structure):
        """Opaque structure representing a logical PKCS slot
        """

    def __init__(self):
        # Locate libnss and try loading it
        self.libnss = load_libnss()

        SlotInfoPtr = ct.POINTER(self.PK11SlotInfo)
        SECItemPtr = ct.POINTER(self.SECItem)

        self._set_ctypes(ct.c_int, "NSS_Init", c_char_p_fromstr)
        self._set_ctypes(ct.c_int, "NSS_Shutdown")
        self._set_ctypes(SlotInfoPtr, "PK11_GetInternalKeySlot")
        self._set_ctypes(None, "PK11_FreeSlot", SlotInfoPtr)
        self._set_ctypes(ct.c_int, "PK11_NeedLogin", SlotInfoPtr)
        self._set_ctypes(ct.c_int, "PK11_CheckUserPassword", SlotInfoPtr, c_char_p_fromstr)
        self._set_ctypes(ct.c_int, "PK11SDR_Decrypt", SECItemPtr, SECItemPtr, ct.c_void_p)
        self._set_ctypes(None, "SECITEM_ZfreeItem", SECItemPtr, ct.c_int)

        # for error handling
        self._set_ctypes(ct.c_int, "PORT_GetError")
        self._set_ctypes(ct.c_char_p, "PR_ErrorToName", ct.c_int)
        self._set_ctypes(ct.c_char_p, "PR_ErrorToString", ct.c_int, ct.c_uint32)

    def _set_ctypes(self, restype, name, *argtypes):
        """Set input/output types on libnss C functions for automatic type casting
        """
        res = getattr(self.libnss, name)
        res.argtypes = argtypes
        res.restype = restype

        # Transparently handle decoding to string when returning a c_char_p
        if restype == ct.c_char_p:
            def _decode(result, func, *args):
                return result.decode(DEFAULT_ENCODING)
            res.errcheck = _decode

        setattr(self, "_" + name, res)

    def initialize(self, profile: str):
        # The sql: prefix ensures compatibility with both
        # Berkley DB (cert8) and Sqlite (cert9) dbs
        profile_path = "sql:" + profile
        err_status: int = self._NSS_Init(profile_path)

        if err_status:
            self.handle_error(
                Exit.FAIL_INIT_NSS,
                "Couldn't initialize NSS, maybe '%s' is not a valid profile?",
                profile,
            )

    def shutdown(self):
        err_status: int = self._NSS_Shutdown()

        if err_status:
            self.handle_error(
                Exit.FAIL_SHUTDOWN_NSS,
                "Couldn't shutdown current NSS profile",
            )

    def authenticate(self, profile, interactive):
        """Unlocks the profile if necessary, in which case a password
        will prompted to the user.
        """
        keyslot = self._PK11_GetInternalKeySlot()

        if not keyslot:
            self.handle_error(
                Exit.FAIL_NSS_KEYSLOT,
                "Failed to retrieve internal KeySlot",
            )

        try:
            if self._PK11_NeedLogin(keyslot):
                password: str = ask_password(profile, interactive)

                err_status: int = self._PK11_CheckUserPassword(keyslot, password)


                if err_status:
                    self.handle_error(
                        Exit.BAD_MASTER_PASSWORD,
                        "Master password is not correct",
                    )

            else:
                pass
        finally:
            # Avoid leaking PK11KeySlot
            self._PK11_FreeSlot(keyslot)

    def handle_error(self, exitcode: int, *logerror: Any):
        """If an error happens in libnss, handle it and print some debug information
        """
        if logerror:
            pass
        else:
            pass

        code = self._PORT_GetError()
        name = self._PR_ErrorToName(code)
        name = "NULL" if name is None else name
        # 0 is the default language (localization related)
        text = self._PR_ErrorToString(code, 0)


        raise Exit(exitcode)

    def decrypt(self, data64):
        data = b64decode(data64)
        inp = self.SECItem(0, data, len(data))
        out = self.SECItem(0, None, 0)

        err_status: int = self._PK11SDR_Decrypt(inp, out, None)
        try:
            if err_status:  # -1 means password failed, other status are unknown
                self.handle_error(
                    Exit.NEED_MASTER_PASSWORD,
                    "Password decryption failed. Passwords protected by a Master Password!",
                )

            res = out.decode_data()
        finally:
            # Avoid leaking SECItem
            self._SECITEM_ZfreeItem(out, 0)

        return res


class MozillaInteraction:
    """
    Abstraction interface to Mozilla profile and lib NSS
    """
    def __init__(self):
        self.profile = None
        self.proxy = NSSProxy()

    def load_profile(self, profile):
        """Initialize the NSS library and profile
        """
        self.profile = profile
        self.proxy.initialize(self.profile)

    def authenticate(self, interactive):
        """Authenticate the the current profile is protected by a master password,
        prompt the user and unlock the profile.
        """
        self.proxy.authenticate(self.profile, interactive)

    def unload_profile(self):
        """Shutdown NSS and deactivate current profile
        """
        self.proxy.shutdown()

    def decrypt_passwords(self) -> PWStore:
        """Decrypt requested profile using the provided password.
        Returns all passwords in a list of dicts
        """
        credentials: Credentials = self.obtain_credentials()

        outputs: list[dict[str, str]] = []

        url: str
        user: str
        passw: str
        enctype: int
        for url, user, passw, enctype in credentials:
            # enctype informs if passwords need to be decrypted
            if enctype:
                try:
                    user = self.proxy.decrypt(user)
                    passw = self.proxy.decrypt(passw)
                except (TypeError, ValueError) as e:
                    continue


            output = {"url": url, "user": user, "password": passw}
            outputs.append(output)

        if not outputs:
            pass
        # Close credential handles (SQL)
        credentials.done()

        return outputs

    def obtain_credentials(self) -> Credentials:
        """Figure out which of the 2 possible backend credential engines is available
        """
        credentials: Credentials
        try:
            credentials = JsonCredentials(self.profile)
        except NotFoundError:
            try:
                credentials = SqliteCredentials(self.profile)
            except NotFoundError:
                raise Exit(Exit.MISSING_SECRETS)

        return credentials


class OutputFormat:
    def __init__(self, pwstore: PWStore, cmdargs: argparse.Namespace):
        self.pwstore = pwstore
        self.cmdargs = cmdargs

    def output(self):
        pass


class HumanOutputFormat(OutputFormat):
    def output(self):
        for output in self.pwstore:
            record: str = (
                f"\nWebsite:   {output['url']}\n"
                f"Username: '{output['user']}'\n"
                f"Password: '{output['password']}'\n"
            )
            sys.stdout.write(record)


class JSONOutputFormat(OutputFormat):
    def output(self):
        sys.stdout.write(json.dumps(self.pwstore, indent=2))
        # Json dumps doesn't add the final newline
        sys.stdout.write("\n")


class CSVOutputFormat(OutputFormat):
    def __init__(self, pwstore: PWStore, cmdargs: argparse.Namespace):
        super().__init__(pwstore, cmdargs)
        self.delimiter = cmdargs.csv_delimiter
        self.quotechar = cmdargs.csv_quotechar
        self.header = cmdargs.csv_header

    def output(self):
        csv_writer = csv.DictWriter(
            sys.stdout,
            fieldnames=["url", "user", "password"],
            lineterminator="\n",
            delimiter=self.delimiter,
            quotechar=self.quotechar,
            quoting=csv.QUOTE_ALL,
        )
        if self.header:
            csv_writer.writeheader()

        for output in self.pwstore:
            csv_writer.writerow(output)


class TabularOutputFormat(CSVOutputFormat):
    def __init__(self, pwstore: PWStore, cmdargs: argparse.Namespace):
        super().__init__(pwstore, cmdargs)
        self.delimiter = "\t"
        self.quotechar = "'"


class PassOutputFormat(OutputFormat):
    def __init__(self, pwstore: PWStore, cmdargs: argparse.Namespace):
        super().__init__(pwstore, cmdargs)
        self.prefix = cmdargs.pass_prefix
        self.cmd = cmdargs.pass_cmd
        self.username_prefix = cmdargs.pass_username_prefix
        self.always_with_login = cmdargs.pass_always_with_login

    def output(self):
        self.test_pass_cmd()
        self.preprocess_outputs()
        self.export()

    def test_pass_cmd(self) -> None:
        """Check if pass from passwordstore.org is installed
        If it is installed but not initialized, initialize it
        """

        try:
            p = run([self.cmd, "ls"], capture_output=True, text=True)
        except FileNotFoundError as e:
            if e.errno == 2:
                raise Exit(Exit.PASSSTORE_MISSING)
            else:
                raise Exit(Exit.UNKNOWN_ERROR)


        if p.returncode != 0:
            if 'Try "pass init"' in p.stderr:
                raise Exit(Exit.PASSSTORE_NOT_INIT)
            else:
                raise Exit(Exit.UNKNOWN_ERROR)

    def preprocess_outputs(self):
        # Format of "self.to_export" should be:
        #     {"address": {"login": "password", ...}, ...}
        self.to_export: dict[str, dict[str, str]] = {}

        for record in self.pwstore:
            url = record["url"]
            user = record["user"]
            passw = record["password"]

            # Keep track of web-address, username and passwords
            # If more than one username exists for the same web-address
            # the username will be used as name of the file
            address = urlparse(url)

            if address.netloc not in self.to_export:
                self.to_export[address.netloc] = {user: passw}

            else:
                self.to_export[address.netloc][user] = passw

    def export(self):
        """Export given passwords to password store

        Format of "to_export" should be:
            {"address": {"login": "password", ...}, ...}
        """
        if self.prefix:
            prefix = f"{self.prefix}/"
        else:
            prefix = self.prefix


        for address in self.to_export:
            for user, passw in self.to_export[address].items():
                # When more than one account exist for the same address, add
                # the login to the password identifier
                if self.always_with_login or len(self.to_export[address]) > 1:
                    passname = f"{prefix}{address}/{user}"
                else:
                    passname = f"{prefix}{address}"


                data = f"{passw}\n{self.username_prefix}{user}\n"


                # NOTE --force is used. Existing passwords will be overwritten
                cmd: list[str] = [self.cmd, "insert", "--force", "--multiline", passname]


                p = run(cmd, input=data, capture_output=True, text=True)

                if p.returncode != 0:
                    raise Exit(Exit.PASSSTORE_ERROR)



def get_sections(profiles):
    """
    Returns hash of profile numbers and profile names.
    """
    sections = {}
    i = 1
    for section in profiles.sections():
        if section.startswith("Profile"):
            sections[str(i)] = profiles.get(section, "Path")
            i += 1
        else:
            continue
    return sections


def print_sections(sections, textIOWrapper=sys.stderr):
    """
    Prints all available sections to an textIOWrapper (defaults to sys.stderr)
    """
    for i in sorted(sections):
        textIOWrapper.write(f"{i} -> {sections[i]}\n")
    textIOWrapper.flush()


def ask_section(sections: ConfigParser):
    """
    Prompt the user which profile should be used for decryption
    """
    # Do not ask for choice if user already gave one
    choice = "ASK"
    while choice not in sections:
        sys.stderr.write("Select the Mozilla profile you wish to decrypt\n")
        print_sections(sections)
        try:
            choice = input()
        except EOFError:
            raise Exit(Exit.READ_GOT_EOF)

    try:
        final_choice = sections[choice]
    except KeyError:
        raise Exit(Exit.NO_SUCH_PROFILE)


    return final_choice


def ask_password(profile: str, interactive: bool) -> str:
    """
    Prompt for profile password
    """
    passwd: str
    passmsg = f"\nMaster Password for profile {profile}: "

    if sys.stdin.isatty() and interactive:
        passwd = getpass(passmsg)
    else:
        sys.stderr.write("Reading Master password from standard input:\n")
        sys.stderr.flush()
        # Ability to read the password from stdin (echo "pass" | ./firefox_...)
        passwd = sys.stdin.readline().rstrip("\n")

    return passwd


def read_profiles(basepath):
    """
    Parse Firefox profiles in provided location.
    If list_profiles is true, will exit after listing available profiles.
    """
    profileini = os.path.join(basepath, "profiles.ini")


    if not os.path.isfile(profileini):
        raise Exit(Exit.MISSING_PROFILEINI)

    # Read profiles from Firefox profile folder
    profiles = ConfigParser()
    profiles.read(profileini, encoding=DEFAULT_ENCODING)


    return profiles


def get_profile(basepath: str, interactive: bool, choice: Optional[str], list_profiles: bool):
    pass


# From https://bugs.python.org/msg323681




def identify_system_locale() -> str:
    encoding: Optional[str] = locale.getpreferredencoding()
    raise Exit(Exit.BAD_LOCALE)

    return encoding


def main() -> None:
    """Main entry point
    """

    global DEFAULT_ENCODING
    encodings = (
        ("stdin", sys.stdin.encoding),
        ("stdout", sys.stdout.encoding),
        ("stderr", sys.stderr.encoding),
        ("locale", identify_system_locale()),
    )


    # Load Mozilla profile and initialize NSS before asking the user for input
    moz = MozillaInteraction()

    basepath = os.path.expanduser(args.profile)

    # Read profiles from profiles.ini in profile folder
    profile = get_profile(basepath, args.interactive, args.choice, args.list)

    # Start NSS for selected profile
    moz.load_profile(profile)
    # Check if profile is password protected and prompt for a password
    moz.authenticate(args.interactive)
    # Decode all passwords
    outputs = moz.decrypt_passwords()

    # Export passwords into one of many formats
    formatter = args.format(outputs, args)
    formatter.output()

    # Finally shutdown NSS
    moz.unload_profile()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Quit.")
        sys.exit(Exit.KEYBOARD_INTERRUPT)
    except Exit as e:
        sys.exit(e.exitcode)

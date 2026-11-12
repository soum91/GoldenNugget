"""``GoldenNugget rescue`` — race a SpringBoard boot loop with a one-file restore.

Written for the 2026-11-12 iPhone 17 / iOS 27.0.1 case: the Mond iPhone
windowing template's managed ``com.apple.springboard.plist`` sent SpringBoard
into a crash loop (Apple logo → black → Apple logo). Lockdown answers for a few
seconds each cycle, which is too short for the normal reset (a protective
backup first) and too short to do by hand.

This command waits for the device, and the moment usbmux lists it, sends the
smallest possible partial restore: an **empty dictionary** plist over
``ManagedPreferencesDomain/mobile/com.apple.springboard.plist`` (and, with
``--uikit``, ``com.apple.UIKit.plist``). It is the same single-pass partial
restore the app uses with ``GOLDENNUGGET_NO_PROTECTIVE_BACKUP=1``: no protective
backup, no iOS 27 three-phase flow, no security-recovery wipe. An empty dict,
never a zero-byte file (a zero-byte plist can itself boot-loop iOS 26.2+).

Every attempt is logged with its exact failure, classified as:
  * ``LOCKED``: iOS refused because the device has not been unlocked since
    boot (PasswordProtected / MBErrorDomain 208). If every attempt ends here,
    no tool can get in this way.
  * ``FIND MY``: Find My is on, and a restore is refused outright.
  * ``DROPPED``: the device vanished mid-attempt (the race was lost); retried.
  * ``OTHER``: anything else, printed in full.

Success = the device accepted the restore. It then reboots by itself; SpringBoard
should come up with stock settings.

The Windows build is a windowed executable with no console, so on Windows this
command opens its own console window, and every line is also written to
``goldennugget-rescue.log`` on the Desktop.
"""

from __future__ import annotations

import asyncio
import os
import plistlib
import sys
import time
from datetime import datetime
from pathlib import Path

_LOG_HANDLE = None


def add_parser(subp):
    parser = subp.add_parser(
        "rescue",
        help="Race a SpringBoard boot loop with a one-file restore",
        description="Wait for the device and immediately restore an empty managed "
                    "com.apple.springboard.plist (no protective backup), retrying "
                    "every time the device reappears.",
    )
    parser.add_argument("--udid", default=None, help="only target this device UDID")
    parser.add_argument("--uikit", action="store_true",
                        help="also reset ManagedPreferencesDomain mobile/com.apple.UIKit.plist")
    parser.add_argument("--minutes", type=float, default=60.0,
                        help="give up after this many minutes (default 60)")
    parser.add_argument("--poll", type=float, default=0.15,
                        help="seconds between usbmux polls (default 0.15)")
    parser.set_defaults(func=run)
    return parser


# ---------------------------------------------------------------- output ----

def _attach_console() -> None:
    """Give the windowed Windows build a console so progress is visible."""
    if os.name != "nt":
        return
    if sys.stdout is not None and getattr(sys.stdout, "isatty", lambda: False)():
        return
    try:
        import ctypes
        if not ctypes.windll.kernel32.AttachConsole(-1):  # parent cmd.exe, if any
            ctypes.windll.kernel32.AllocConsole()
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        sys.stderr = sys.stdout
        ctypes.windll.kernel32.SetConsoleTitleW("GoldenNugget rescue")
    except Exception:
        pass


def _open_log() -> Path:
    global _LOG_HANDLE
    desktop = Path.home() / "Desktop"
    base = desktop if desktop.is_dir() else Path.home()
    path = base / "goldennugget-rescue.log"
    try:
        _LOG_HANDLE = open(path, "a", encoding="utf-8", buffering=1)
    except OSError:
        _LOG_HANDLE = None
    return path


def say(line: str) -> None:
    stamped = f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]}  {line}"
    for stream in (sys.stdout, _LOG_HANDLE):
        if stream is None:
            continue
        try:
            stream.write(stamped + "\n")
            stream.flush()
        except Exception:
            pass


# --------------------------------------------------------------- payload ----

def build_files(include_uikit: bool):
    from src.utils.file_to_restore import FileToRestore
    empty = plistlib.dumps({}, fmt=plistlib.FMT_XML)
    files = [FileToRestore(contents=empty, restore_path="/mobile/com.apple.springboard.plist",
                           domain="ManagedPreferencesDomain")]
    if include_uikit:
        files.append(FileToRestore(contents=empty, restore_path="/mobile/com.apple.UIKit.plist",
                                   domain="ManagedPreferencesDomain"))
    return files


def build_backup(files, lockdown):
    from src.restore import backup
    from src.restore.restore import concat_regular_file
    from src.devicemanagement.constants import Version
    rows: list = []
    last_domain, last_path = "", ""
    for f in sorted(files, key=lambda f: (f.domain, f.restore_path)):
        last_domain, last_path = concat_regular_file(f, rows, last_domain, last_path)
    values = getattr(lockdown, "all_values", {}) or {}
    manifest = {k: values[k] for k in ("ProductVersion", "ProductType", "DeviceClass",
                                       "BuildVersion", "UniqueDeviceID", "SerialNumber",
                                       "DeviceName") if k in values}
    ios27 = Version(lockdown.product_version) >= Version("27.0")
    return backup.Backup(files=rows, apps=[], device_manifest=manifest, manifest_ios27=ios27)


# ------------------------------------------------------------------ race ----

def classify(exc: BaseException) -> str:
    from src.exceptions.device_errors import (
        is_device_locked_error, is_find_my_error, is_connection_error)
    if is_find_my_error(exc):
        return "FIND MY"
    if is_device_locked_error(exc):
        return "LOCKED"
    if is_connection_error(exc):
        return "DROPPED"
    return "OTHER"


async def _visible_udids() -> list[str]:
    from pymobiledevice3 import usbmux
    try:
        devices = await usbmux.list_devices()
    except Exception:
        return []
    return [d.serial for d in devices if getattr(d, "connection_type", "USB") == "USB"]


async def attempt(udid: str, files) -> tuple[bool, str]:
    from pymobiledevice3.lockdown import create_using_usbmux
    from src.restore import perform_restore
    lockdown = await asyncio.wait_for(create_using_usbmux(serial=udid), timeout=4)
    try:
        say(f"  connected: {lockdown.all_values.get('DeviceName', '?')} "
            f"{lockdown.product_type} iOS {lockdown.product_version} — sending reset")
        back = build_backup(files, lockdown)
        await perform_restore(backup=back, reboot=False, lockdown_client=lockdown,
                              progress_callback=lambda p: None, udid=udid)
        return True, "restore accepted"
    finally:
        try:
            await lockdown.close()
        except Exception:
            pass


async def race(args) -> int:
    files = build_files(args.uikit)
    targets = ", ".join(f"{f.domain}{f.restore_path}" for f in files)
    say(f"Rescue: will write an empty plist to {targets}")
    say("Waiting for the device. Leave it plugged in and looping; this retries every cycle.")
    deadline = time.monotonic() + args.minutes * 60
    tally: dict[str, int] = {}
    seen_present = False
    while time.monotonic() < deadline:
        udids = await _visible_udids()
        if args.udid:
            udids = [u for u in udids if u == args.udid]
        if not udids:
            if seen_present:
                say("  device gone (rebooting) — waiting for it to come back")
                seen_present = False
            await asyncio.sleep(args.poll)
            continue
        seen_present = True
        udid = udids[0]
        n = sum(tally.values()) + 1
        say(f"Attempt {n}: device {udid} is visible")
        try:
            ok, detail = await attempt(udid, files)
        except Exception as exc:  # noqa: BLE001 — every failure is reported
            kind = classify(exc)
            tally[kind] = tally.get(kind, 0) + 1
            say(f"  {kind}: {type(exc).__name__}: {exc}")
            if kind == "FIND MY":
                say("Find My is on. Restores are refused until it is off; this cannot be raced. Stopping.")
                return 2
            if kind == "LOCKED" and tally[kind] in (3, 10, 25):
                say("  note: iOS keeps answering 'locked'. The device has not been unlocked since "
                    "boot, and the backup service refuses until it is. If every attempt ends here, "
                    "this route cannot work.")
            # Wait for this boot cycle to end before trying again, so a
            # half-dead session is not hammered.
            await asyncio.sleep(0.5)
            continue
        say(f"SUCCESS: {detail}. The device should reboot by itself with stock SpringBoard "
            "settings. If it still loops, run rescue again with --uikit.")
        return 0
    say(f"Gave up after {args.minutes:g} minutes. Attempt results: "
        + (", ".join(f"{k} ×{v}" for k, v in sorted(tally.items())) or "device never seen"))
    return 1


def run(args) -> int:
    _attach_console()
    log_path = _open_log()
    say(f"GoldenNugget rescue — log: {log_path}")
    try:
        return asyncio.run(race(args))
    except KeyboardInterrupt:
        say("Stopped.")
        return 130
    finally:
        if os.name == "nt" and sys.stdin is None:
            # Windowed build launched by double-click: keep the console open.
            time.sleep(30)

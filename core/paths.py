"""
Path resolution for both dev mode and PyInstaller frozen builds.

- get_app_dir()    → read-only bundled assets (presets.json, libmpv, ffmpeg)
- get_data_dir()   → writable user data (config.json, user_presets.json)
- get_ffmpeg()     → full path to ffmpeg executable
- get_ffprobe()    → full path to ffprobe executable
"""

import os
import sys

_FROZEN = getattr(sys, "frozen", False)


def get_app_dir() -> str:
    if _FROZEN:
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_data_dir() -> str:
    if _FROZEN:
        data = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "SubVela")
        os.makedirs(data, exist_ok=True)
        return data
    return get_app_dir()


def get_asset_path(*parts: str) -> str:
    return os.path.join(get_app_dir(), "assets", *parts)


def get_data_path(*parts: str) -> str:
    return os.path.join(get_data_dir(), *parts)


def get_ffmpeg() -> str:
    if _FROZEN:
        return os.path.join(get_app_dir(), "ffmpeg.exe")
    return "ffmpeg"


def get_ffprobe() -> str:
    if _FROZEN:
        return os.path.join(get_app_dir(), "ffprobe.exe")
    return "ffprobe"

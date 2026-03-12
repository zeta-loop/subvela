import json
import os
from dataclasses import dataclass
from core.subtitle_model import SubtitleAnimation, SubtitleStyle
from core.paths import get_asset_path, get_data_path

BUILTIN_PRESETS_PATH = get_asset_path("presets.json")
USER_PRESETS_PATH = get_data_path("user_presets.json")


@dataclass
class PresetData:
    primary: SubtitleStyle
    secondary: SubtitleStyle | None = None
    animation: SubtitleAnimation | None = None

    def to_dict(self) -> dict:
        d: dict = {"primary": self.primary.to_dict()}
        if self.secondary is not None:
            d["secondary"] = self.secondary.to_dict()
        if self.animation is not None:
            d["animation"] = self.animation.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PresetData":
        # New nested format: {"primary": {...}, "secondary": {...}, "animation": {...}}
        if "primary" in data:
            primary = SubtitleStyle.from_dict(data["primary"])
            secondary = SubtitleStyle.from_dict(data["secondary"]) if "secondary" in data else None
            animation = SubtitleAnimation.from_dict(data["animation"]) if "animation" in data else None
            return cls(primary=primary, secondary=secondary, animation=animation)
        # Legacy flat format: treat entire dict as primary style only
        return cls(primary=SubtitleStyle.from_dict(data))


class PresetManager:
    def __init__(self):
        self._builtin: dict[str, PresetData] = {}
        self._user: dict[str, PresetData] = {}
        self._load_builtin()
        self._load_user()

    def _load_builtin(self):
        try:
            with open(BUILTIN_PRESETS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for name, preset_dict in data.items():
                self._builtin[name] = PresetData.from_dict(preset_dict)
        except Exception:
            pass

    def _load_user(self):
        try:
            with open(USER_PRESETS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for name, preset_dict in data.items():
                self._user[name] = PresetData.from_dict(preset_dict)
        except Exception:
            pass

    def get_all_names(self) -> list[str]:
        return list(self._builtin.keys()) + list(self._user.keys())

    def get_preset(self, name: str) -> PresetData | None:
        return self._builtin.get(name) or self._user.get(name)

    def is_user_preset(self, name: str) -> bool:
        return name in self._user

    def save_user_preset(self, name: str, primary: SubtitleStyle,
                         secondary: SubtitleStyle | None = None,
                         animation: SubtitleAnimation | None = None):
        self._user[name] = PresetData(primary=primary, secondary=secondary, animation=animation)
        self._persist_user()

    def delete_user_preset(self, name: str) -> bool:
        if name in self._user:
            del self._user[name]
            self._persist_user()
            return True
        return False

    def _persist_user(self):
        data = {name: preset.to_dict() for name, preset in self._user.items()}
        try:
            with open(USER_PRESETS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception:
            pass

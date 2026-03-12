from __future__ import annotations

import json
import locale
import os
import sys
import threading
import time
from pathlib import Path


APP_NAME = "SubVela"
CACHE_VERSION = 1
CACHE_FILENAME = ".font_map.json"
SUPPORTED_EXTENSIONS = {".ttf", ".otf", ".ttc", ".otc"}


_CATALOG_LOCK = threading.Lock()
_CATALOG_CACHE: dict | None = None


def normalize_font_name(name: str) -> str:
    value = (name or "").strip()
    if value.startswith("@"):
        value = value[1:]
    return " ".join(value.split())


def _cache_key(name: str) -> str:
    return normalize_font_name(name).casefold()


def _user_locale_language() -> str:
    lang = None
    try:
        lang = locale.getlocale()[0]
    except Exception:
        lang = None
    if not lang:
        lang = os.environ.get("LANG", "")
    lang = (lang or "").replace("-", "_")
    return lang.split("_", 1)[0].lower()


def _build_font_label(display_name: str, canonical_name: str) -> str:
    display = normalize_font_name(display_name)
    canonical = normalize_font_name(canonical_name)
    if not display:
        return canonical
    if not canonical or display.casefold() == canonical.casefold():
        return display
    return f"{display} ({canonical})"


def _get_cache_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        if not base:
            base = str(Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")

    cache_dir = Path(base) / APP_NAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_font_cache_path() -> Path:
    return _get_cache_dir() / CACHE_FILENAME


def _mark_hidden(path: Path):
    if sys.platform != "win32":
        return
    try:
        import ctypes

        FILE_ATTRIBUTE_HIDDEN = 0x2
        FILE_ATTRIBUTE_NORMAL = 0x80
        current = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        if current == -1:
            current = FILE_ATTRIBUTE_NORMAL
        ctypes.windll.kernel32.SetFileAttributesW(str(path), current | FILE_ATTRIBUTE_HIDDEN)
    except Exception:
        pass


def _app_bundled_fonts_dir() -> Path | None:
    """Return the app's bundled fonts/ directory (next to core/)."""
    app_root = Path(__file__).resolve().parent.parent
    fonts_dir = app_root / "fonts"
    if fonts_dir.is_dir():
        return fonts_dir
    return None


def _system_font_directories() -> list[Path]:
    home = Path.home()
    if sys.platform == "win32":
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        candidates = [
            windir / "Fonts",
            home / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts",
        ]
    elif sys.platform == "darwin":
        candidates = [
            Path("/System/Library/Fonts"),
            Path("/Library/Fonts"),
            home / "Library" / "Fonts",
        ]
    else:
        candidates = [
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            home / ".fonts",
            home / ".local" / "share" / "fonts",
        ]

    # Include app-bundled fonts directory (for fonts shipped with the exe)
    bundled = _app_bundled_fonts_dir()
    if bundled is not None:
        candidates.insert(0, bundled)

    unique = []
    seen = set()
    for path in candidates:
        resolved = str(path)
        if resolved in seen or not path.exists():
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def _iter_font_files() -> list[Path]:
    files = []
    seen = set()
    for root in _system_font_directories():
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            resolved = str(path)
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(path)
    return files


def _decode_name_record(record) -> str:
    try:
        value = record.toUnicode().strip()
    except Exception:
        return ""
    return normalize_font_name(value)


def _extract_name_map(font) -> dict[int, list[tuple[str, int]]]:
    table = font.get("name")
    result: dict[int, list[tuple[str, int]]] = {}
    if table is None:
        return result
    for record in table.names:
        value = _decode_name_record(record)
        if not value:
            continue
        result.setdefault(record.nameID, []).append((value, getattr(record, "langID", 0)))
    return result


def _pick_canonical_name(candidates: list[tuple[str, int]]) -> str:
    if not candidates:
        return ""

    def score(item: tuple[str, int]) -> tuple[int, int, str]:
        name, lang_id = item
        ascii_only = all(ord(ch) < 128 for ch in name)
        english_hint = lang_id in (0, 0x009, 0x409, 0x809)
        return (2 if ascii_only else 0) + (1 if english_hint else 0), len(name), name

    return max(candidates, key=score)[0]


def _pick_display_name(candidates: list[tuple[str, int]], canonical_name: str) -> str:
    if not candidates:
        return canonical_name

    language = _user_locale_language()
    if language in {"zh", "ja", "ko"}:
        localized = [name for name, _ in candidates if any(ord(ch) > 127 for ch in name)]
        if localized:
            return localized[0]

    localized = [name for name, _ in candidates if any(ord(ch) > 127 for ch in name)]
    if localized:
        return localized[0]

    return canonical_name or candidates[0][0]


def _variant_key(subfamily_name: str) -> str:
    value = (subfamily_name or "").casefold()
    is_bold = any(token in value for token in ("bold", "black", "heavy", "semibold", "demibold", "extrabold"))
    is_italic = any(token in value for token in ("italic", "oblique"))
    if is_bold and is_italic:
        return "bold_italic"
    if is_bold:
        return "bold"
    if is_italic:
        return "italic"
    return "regular"


def _empty_catalog() -> dict:
    return {
        "version": CACHE_VERSION,
        "generated_at": 0,
        "fonts": [],
        "label_to_family": {},
        "family_to_label": {},
        "alias_to_family": {},
        "variant_lookup": {},
    }


def _finalize_catalog(data: dict) -> dict:
    catalog = dict(data)
    fonts = catalog.get("fonts", [])
    label_to_family = {}
    family_to_label = {}
    alias_to_family = {}
    variant_lookup = {}

    for entry in fonts:
        canonical = normalize_font_name(entry.get("canonical_name", ""))
        display = normalize_font_name(entry.get("display_name", canonical))
        if not canonical:
            continue
        aliases = set(entry.get("aliases", []))
        normalized_aliases = sorted({normalize_font_name(alias) for alias in aliases if normalize_font_name(alias)})
        if display.casefold() == canonical.casefold():
            localized_aliases = [alias for alias in normalized_aliases if any(ord(ch) > 127 for ch in alias)]
            if localized_aliases:
                display = localized_aliases[0]
        label = _build_font_label(display, canonical)
        entry["canonical_name"] = canonical
        entry["display_name"] = display or canonical
        entry["label"] = label

        canonical_key = canonical.casefold()
        family_to_label[canonical_key] = label
        label_to_family[label] = canonical

        aliases = set(normalized_aliases)
        aliases.update({canonical, display, label})
        normalized_aliases = sorted({normalize_font_name(alias) for alias in aliases if normalize_font_name(alias)})
        entry["aliases"] = normalized_aliases
        for alias in normalized_aliases:
            alias_to_family[_cache_key(alias)] = canonical

        variants = entry.get("variants", {})
        for variant_name, variant_data in variants.items():
            if not isinstance(variant_data, dict):
                continue
            variant_lookup[(canonical_key, variant_name)] = {
                "path": variant_data.get("path", ""),
                "index": int(variant_data.get("index", 0)),
            }

    catalog["fonts"] = sorted(fonts, key=lambda item: item.get("label", item.get("canonical_name", "")).casefold())
    catalog["label_to_family"] = label_to_family
    catalog["family_to_label"] = family_to_label
    catalog["alias_to_family"] = alias_to_family
    catalog["variant_lookup"] = variant_lookup
    return catalog


def _read_cache_file(cache_path: Path) -> dict | None:
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if data.get("version") != CACHE_VERSION:
        return None
    return _finalize_catalog(data)


def _write_cache_file(cache_path: Path, catalog: dict):
    serializable = {
        "version": CACHE_VERSION,
        "generated_at": int(time.time()),
        "fonts": catalog.get("fonts", []),
    }
    cache_path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
    _mark_hidden(cache_path)


def _merge_font_face(families: dict, canonical_name: str, display_name: str,
                     aliases: set[str], variant_name: str, path: str, index: int):
    key = canonical_name.casefold()
    entry = families.setdefault(
        key,
        {
            "canonical_name": canonical_name,
            "display_name": display_name or canonical_name,
            "aliases": set(),
            "variants": {},
        },
    )
    entry["aliases"].update(aliases)
    if entry.get("display_name", canonical_name).casefold() == canonical_name.casefold() and display_name:
        entry["display_name"] = display_name
    entry["variants"].setdefault(variant_name, {"path": path, "index": index})


def _scan_font_file(path: Path, families: dict):
    try:
        from fontTools.ttLib import TTCollection, TTFont
    except Exception:
        raise

    extension = path.suffix.lower()
    fonts_with_index = []

    if extension in {".ttc", ".otc"}:
        collection = TTCollection(str(path), lazy=True)
        try:
            fonts_with_index = [(font, idx) for idx, font in enumerate(collection.fonts)]
        except Exception:
            fonts_with_index = []
    else:
        font = TTFont(str(path), lazy=True)
        fonts_with_index = [(font, 0)]

    for font, index in fonts_with_index:
        try:
            name_map = _extract_name_map(font)
            family_candidates = name_map.get(16) or name_map.get(1) or []
            if not family_candidates:
                continue
            canonical_name = _pick_canonical_name(family_candidates)
            if not canonical_name:
                continue
            display_name = _pick_display_name(family_candidates, canonical_name)
            subfamily_candidates = name_map.get(17) or name_map.get(2) or []
            subfamily_name = _pick_canonical_name(subfamily_candidates) if subfamily_candidates else "Regular"
            variant_name = _variant_key(subfamily_name)
            aliases = {name for name, _ in family_candidates if name}
            aliases.add(canonical_name)
            aliases.add(display_name)
            _merge_font_face(families, canonical_name, display_name, aliases, variant_name, str(path), index)
        finally:
            try:
                font.close()
            except Exception:
                pass


def _scan_system_fonts() -> dict:
    families: dict[str, dict] = {}
    files = _iter_font_files()
    for path in files:
        try:
            _scan_font_file(path, families)
        except Exception:
            continue

    fonts = []
    for entry in families.values():
        aliases = sorted({normalize_font_name(alias) for alias in entry.get("aliases", set()) if normalize_font_name(alias)})
        fonts.append(
            {
                "canonical_name": normalize_font_name(entry.get("canonical_name", "")),
                "display_name": normalize_font_name(entry.get("display_name", "")),
                "aliases": aliases,
                "variants": entry.get("variants", {}),
            }
        )

    return _finalize_catalog({
        "version": CACHE_VERSION,
        "generated_at": int(time.time()),
        "fonts": fonts,
    })


def get_font_catalog(force_refresh: bool = False) -> dict:
    global _CATALOG_CACHE

    with _CATALOG_LOCK:
        if _CATALOG_CACHE is not None and not force_refresh:
            return _CATALOG_CACHE

        cache_path = get_font_cache_path()
        if not force_refresh:
            cached = _read_cache_file(cache_path)
            if cached is not None:
                _CATALOG_CACHE = cached
                return _CATALOG_CACHE

        try:
            catalog = _scan_system_fonts()
            _write_cache_file(cache_path, catalog)
            _CATALOG_CACHE = catalog
        except Exception:
            fallback = _read_cache_file(cache_path)
            _CATALOG_CACHE = fallback if fallback is not None else _empty_catalog()

        return _CATALOG_CACHE


def refresh_font_catalog() -> dict:
    return get_font_catalog(force_refresh=True)


def get_font_dropdown_entries(force_refresh: bool = False) -> list[dict]:
    return list(get_font_catalog(force_refresh=force_refresh).get("fonts", []))


def resolve_font_family_name(name_or_label: str) -> str:
    value = normalize_font_name(name_or_label)
    if not value:
        return ""

    catalog = get_font_catalog()
    family = catalog.get("alias_to_family", {}).get(_cache_key(value))
    if family:
        return family

    if value.endswith(")") and "(" in value:
        inner = value.rsplit("(", 1)[1].rstrip(") ")
        family = catalog.get("alias_to_family", {}).get(_cache_key(inner))
        if family:
            return family

    return value


def get_font_display_label(name_or_label: str) -> str:
    family = resolve_font_family_name(name_or_label)
    if not family:
        return ""
    catalog = get_font_catalog()
    return catalog.get("family_to_label", {}).get(family.casefold(), family)


def resolve_cached_font_variant(family: str, bold: bool, italic: bool) -> dict | None:
    family_name = resolve_font_family_name(family)
    if not family_name:
        return None

    catalog = get_font_catalog()
    key = family_name.casefold()
    variants = catalog.get("variant_lookup", {})

    wanted = []
    if bold and italic:
        wanted.extend(["bold_italic", "bold", "italic", "regular"])
    elif bold:
        wanted.extend(["bold", "bold_italic", "regular"])
    elif italic:
        wanted.extend(["italic", "bold_italic", "regular"])
    else:
        wanted.extend(["regular", "bold", "italic", "bold_italic"])

    for variant_name in wanted:
        match = variants.get((key, variant_name))
        if match and os.path.exists(match.get("path", "")):
            result = dict(match)
            result["variant"] = variant_name  # "regular", "bold", "italic", "bold_italic"
            return result
    return None
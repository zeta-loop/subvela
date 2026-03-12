import json
import os
from dotenv import load_dotenv
from core.paths import get_data_path

try:
    import keyring
except ImportError:
    keyring = None

load_dotenv()

CONFIG_PATH = get_data_path("config.json")
KEYRING_SERVICE = "SubVela"

_PROVIDER_FIELDS = {
    "gemini": "gemini_api_key",
    "groq": "groq_api_key",
    "openai": "openai_api_key",
    "claude": "claude_api_key",
}

_PROVIDER_ENV_VARS = {
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "openai": "OPENAI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
}

_PROVIDER_STORE_FLAGS = {
    "gemini": "store_gemini_api_key_locally",
    "groq": "store_groq_api_key_locally",
    "openai": "store_openai_api_key_locally",
    "claude": "store_claude_api_key_locally",
}

_SESSION_KEYS = {}

_DEFAULT_CONFIG = {
    "store_gemini_api_key_locally": False,
    "store_groq_api_key_locally": False,
    "store_openai_api_key_locally": False,
    "store_claude_api_key_locally": False,
    "transcription_provider": "local",
    "translation_provider": "local_nllb",
    "whisper_model": "base",
}


def _load_raw_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_raw_config(config: dict):
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except Exception:
        pass


def is_secure_key_storage_available() -> bool:
    return keyring is not None


def _keyring_name(provider: str) -> str:
    return f"provider:{provider}"


def _legacy_keyring_name(provider: str) -> str:
    return f"transcription:{provider}"


def _get_keyring_api_key(provider: str) -> str:
    if keyring is None:
        return ""
    try:
        return (
            keyring.get_password(KEYRING_SERVICE, _keyring_name(provider))
            or keyring.get_password(KEYRING_SERVICE, _legacy_keyring_name(provider))
            or ""
        )
    except Exception:
        return ""


def _set_keyring_api_key(provider: str, api_key: str):
    if keyring is None:
        return
    try:
        keyring.set_password(KEYRING_SERVICE, _keyring_name(provider), api_key)
    except Exception:
        pass


def _delete_keyring_api_key(provider: str):
    if keyring is None:
        return
    try:
        keyring.delete_password(KEYRING_SERVICE, _keyring_name(provider))
    except Exception:
        pass
    try:
        keyring.delete_password(KEYRING_SERVICE, _legacy_keyring_name(provider))
    except Exception:
        pass


def _migrate_plaintext_api_keys(raw_config: dict) -> dict:
    if keyring is None:
        return raw_config

    changed = False
    for provider, field in _PROVIDER_FIELDS.items():
        plaintext = (raw_config.get(field) or "").strip()
        if not plaintext:
            continue
        _set_keyring_api_key(provider, plaintext)
        raw_config[_PROVIDER_STORE_FLAGS[provider]] = True
        raw_config.pop(field, None)
        changed = True

    if changed:
        _write_raw_config(raw_config)
    return raw_config


def load_config() -> dict:
    raw_config = _migrate_plaintext_api_keys(_load_raw_config())
    result = dict(_DEFAULT_CONFIG)
    result.update(raw_config)

    for provider, field in _PROVIDER_FIELDS.items():
        result[field] = get_api_key(provider, config=result)

    return result


def save_config(config: dict):
    filtered = dict(_DEFAULT_CONFIG)
    for key, value in config.items():
        if key in _PROVIDER_FIELDS.values():
            continue
        filtered[key] = value
    _write_raw_config(filtered)


def get_api_key(provider: str, config: dict | None = None) -> str:
    provider = provider.lower()
    if provider in _SESSION_KEYS and _SESSION_KEYS[provider]:
        return _SESSION_KEYS[provider]

    keyring_value = _get_keyring_api_key(provider)
    if keyring_value:
        return keyring_value

    field = _PROVIDER_FIELDS[provider]
    source = config if config is not None else _load_raw_config()
    legacy_value = (source.get(field) or "").strip()
    if legacy_value:
        return legacy_value

    return os.getenv(_PROVIDER_ENV_VARS[provider], "").strip()


def get_api_key_storage_mode(provider: str, config: dict | None = None) -> str:
    provider = provider.lower()
    if provider in _SESSION_KEYS and _SESSION_KEYS[provider]:
        return "session"
    if _get_keyring_api_key(provider):
        return "local"

    source = config if config is not None else _load_raw_config()
    if (source.get(_PROVIDER_FIELDS[provider]) or "").strip():
        return "legacy"
    if os.getenv(_PROVIDER_ENV_VARS[provider], "").strip():
        return "environment"
    return "none"


def set_api_key(provider: str, api_key: str, store_locally: bool):
    provider = provider.lower()
    raw_config = _migrate_plaintext_api_keys(_load_raw_config())
    raw_config[_PROVIDER_STORE_FLAGS[provider]] = bool(store_locally and is_secure_key_storage_available())
    raw_config.pop(_PROVIDER_FIELDS[provider], None)

    if store_locally and is_secure_key_storage_available():
        _SESSION_KEYS.pop(provider, None)
        _set_keyring_api_key(provider, api_key)
    else:
        if api_key:
            _SESSION_KEYS[provider] = api_key
        else:
            _SESSION_KEYS.pop(provider, None)
        _delete_keyring_api_key(provider)

    _write_raw_config(raw_config)

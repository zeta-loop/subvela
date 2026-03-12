import io
import os
import shutil
import threading
from pathlib import Path

from huggingface_hub import snapshot_download
from tqdm.auto import tqdm


NLLB_MODEL_REPO = "entai2965/nllb-200-distilled-600M-ctranslate2"
NLLB_TOKENIZER_REPO = "facebook/nllb-200-distilled-600M"
NLLB_CACHE_DIR = Path.home() / ".cache" / "subvela" / "translation"

NLLB_LANGUAGE_CODES = {
    "Afrikaans": "afr_Latn",
    "Arabic": "arb_Arab",
    "Armenian": "hye_Armn",
    "Azerbaijani": "azj_Latn",
    "Belarusian": "bel_Cyrl",
    "Bosnian": "bos_Latn",
    "Bulgarian": "bul_Cyrl",
    "Catalan": "cat_Latn",
    "Chinese (Simplified)": "zho_Hans",
    "Chinese (Traditional)": "zho_Hant",
    "Croatian": "hrv_Latn",
    "Czech": "ces_Latn",
    "Danish": "dan_Latn",
    "Dutch": "nld_Latn",
    "English": "eng_Latn",
    "Estonian": "est_Latn",
    "Filipino": "tgl_Latn",
    "Finnish": "fin_Latn",
    "French": "fra_Latn",
    "Galician": "glg_Latn",
    "Georgian": "kat_Geor",
    "German": "deu_Latn",
    "Greek": "ell_Grek",
    "Hebrew": "heb_Hebr",
    "Hindi": "hin_Deva",
    "Hungarian": "hun_Latn",
    "Icelandic": "isl_Latn",
    "Indonesian": "ind_Latn",
    "Italian": "ita_Latn",
    "Japanese": "jpn_Jpan",
    "Kannada": "kan_Knda",
    "Kazakh": "kaz_Cyrl",
    "Korean": "kor_Hang",
    "Latvian": "lav_Latn",
    "Lithuanian": "lit_Latn",
    "Macedonian": "mkd_Cyrl",
    "Malay": "zsm_Latn",
    "Marathi": "mar_Deva",
    "Mongolian": "khk_Cyrl",
    "Norwegian": "nob_Latn",
    "Persian": "pes_Arab",
    "Polish": "pol_Latn",
    "Portuguese": "por_Latn",
    "Romanian": "ron_Latn",
    "Russian": "rus_Cyrl",
    "Serbian": "srp_Cyrl",
    "Slovak": "slk_Latn",
    "Slovenian": "slv_Latn",
    "Spanish": "spa_Latn",
    "Swahili": "swh_Latn",
    "Swedish": "swe_Latn",
    "Tamil": "tam_Taml",
    "Telugu": "tel_Telu",
    "Thai": "tha_Thai",
    "Turkish": "tur_Latn",
    "Ukrainian": "ukr_Cyrl",
    "Urdu": "urd_Arab",
    "Vietnamese": "vie_Latn",
    "Welsh": "cym_Latn",
}

DETECTED_LANGUAGE_CODES = {
    "af": "afr_Latn",
    "ar": "arb_Arab",
    "az": "azj_Latn",
    "be": "bel_Cyrl",
    "bg": "bul_Cyrl",
    "bn": "ben_Beng",
    "bs": "bos_Latn",
    "ca": "cat_Latn",
    "cs": "ces_Latn",
    "cy": "cym_Latn",
    "da": "dan_Latn",
    "de": "deu_Latn",
    "el": "ell_Grek",
    "en": "eng_Latn",
    "es": "spa_Latn",
    "et": "est_Latn",
    "fa": "pes_Arab",
    "fi": "fin_Latn",
    "fr": "fra_Latn",
    "ga": "gle_Latn",
    "gl": "glg_Latn",
    "gu": "guj_Gujr",
    "he": "heb_Hebr",
    "hi": "hin_Deva",
    "hr": "hrv_Latn",
    "hu": "hun_Latn",
    "hy": "hye_Armn",
    "id": "ind_Latn",
    "is": "isl_Latn",
    "it": "ita_Latn",
    "ja": "jpn_Jpan",
    "ka": "kat_Geor",
    "kk": "kaz_Cyrl",
    "kn": "kan_Knda",
    "ko": "kor_Hang",
    "lt": "lit_Latn",
    "lv": "lav_Latn",
    "mk": "mkd_Cyrl",
    "mr": "mar_Deva",
    "ms": "zsm_Latn",
    "nl": "nld_Latn",
    "no": "nob_Latn",
    "pl": "pol_Latn",
    "pt": "por_Latn",
    "ro": "ron_Latn",
    "ru": "rus_Cyrl",
    "sk": "slk_Latn",
    "sl": "slv_Latn",
    "sr": "srp_Cyrl",
    "sv": "swe_Latn",
    "sw": "swh_Latn",
    "ta": "tam_Taml",
    "te": "tel_Telu",
    "th": "tha_Thai",
    "tl": "tgl_Latn",
    "tr": "tur_Latn",
    "uk": "ukr_Cyrl",
    "ur": "urd_Arab",
    "vi": "vie_Latn",
    "zh": "zho_Hans",
    "zh-cn": "zho_Hans",
    "zh-tw": "zho_Hant",
}

MODEL_ALLOW_PATTERNS = ["config.json", "model.bin", "shared_vocabulary.json", "*.txt", "*.json"]
TOKENIZER_ALLOW_PATTERNS = ["*.json", "*.model", "*.txt", "*.bin"]
MODEL_REQUIRED_FILES = ("config.json", "model.bin", "shared_vocabulary.json")
TOKENIZER_REQUIRED_FILES = ("tokenizer_config.json", "sentencepiece.bpe.model")
_MATERIALIZED_DIRNAME = "materialized"
_LOCAL_INTER_THREADS = 1
_LOCAL_INTRA_THREADS = 1
_LOCAL_BEAM_SIZE = 2


class _SilentTqdm(tqdm):
    def __init__(self, *args, **kwargs):
        kwargs.pop("name", None)
        kwargs["disable"] = False
        kwargs.setdefault("file", io.StringIO())
        super().__init__(*args, **kwargs)


class _SnapshotProgressTracker:
    def __init__(self, total_bytes, completed_bytes=0, on_progress=None):
        self.total_bytes = max(int(total_bytes or 0), 1)
        self.completed_bytes = max(0, min(int(completed_bytes or 0), self.total_bytes))
        self.on_progress = on_progress
        self._lock = threading.Lock()

    def attach(self, total_bytes, completed_bytes=0):
        total_bytes = max(int(total_bytes or 0), 1)
        completed_bytes = max(0, int(completed_bytes or 0))
        with self._lock:
            self.total_bytes = max(self.total_bytes, total_bytes)
            self.completed_bytes = max(self.completed_bytes, min(completed_bytes, self.total_bytes))
        self.emit()

    def emit(self):
        if self.on_progress is None:
            return
        progress = min(self.completed_bytes / self.total_bytes, 1.0)
        self.on_progress(progress, self.completed_bytes, self.total_bytes)

    def advance(self, delta_bytes):
        if delta_bytes <= 0:
            return
        with self._lock:
            self.completed_bytes = min(self.total_bytes, self.completed_bytes + int(delta_bytes))
        self.emit()

    def complete(self):
        with self._lock:
            self.completed_bytes = self.total_bytes
        self.emit()


class _CallbackTqdm(_SilentTqdm):
    tracker = None

    def __init__(self, *args, **kwargs):
        self._tracks_bytes = str(kwargs.get("unit") or "").upper() == "B"
        super().__init__(*args, **kwargs)

        tracker = type(self).tracker
        if tracker is None or not self._tracks_bytes:
            return

        current_total = max(int(getattr(self, "total", 0) or 0), 0)
        current_progress = max(int(getattr(self, "n", 0) or 0), 0)
        tracker.attach(current_total, current_progress)

    def update(self, n=1):
        previous = self.n
        result = super().update(n)
        delta = self.n - previous
        tracker = type(self).tracker
        if tracker is not None and self._tracks_bytes and delta > 0:
            tracker.advance(delta)
        return result


def get_translation_cache_dir() -> Path:
    NLLB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return NLLB_CACHE_DIR


def _format_download_size(total_bytes: int) -> str:
    if total_bytes <= 0:
        return "unknown size"
    size_mb = total_bytes / (1024 * 1024)
    if size_mb >= 100:
        return f"{round(size_mb):.0f} MB"
    if size_mb >= 10:
        return f"{size_mb:.1f} MB"
    return f"{size_mb:.2f} MB"


def _get_snapshot_download_status(repo_id: str, cache_dir: str, allow_patterns: list[str]) -> tuple[int, int]:
    files = snapshot_download(
        repo_id=repo_id,
        cache_dir=cache_dir,
        allow_patterns=allow_patterns,
        dry_run=True,
        tqdm_class=_SilentTqdm,
    )

    total_bytes = 0
    cached_bytes = 0
    for item in files:
        file_size = int(getattr(item, "file_size", 0) or 0)
        total_bytes += file_size
        if getattr(item, "is_cached", False):
            cached_bytes += file_size
    return total_bytes, cached_bytes


def _get_repo_cache_dir(repo_id: str, cache_dir: str | Path) -> Path:
    resolved_cache_dir = Path(cache_dir)
    return resolved_cache_dir / f"models--{repo_id.replace('/', '--')}"


def _get_materialized_root(repo_id: str, cache_dir: str | Path) -> Path:
    return _get_repo_cache_dir(repo_id, cache_dir) / _MATERIALIZED_DIRNAME


def _get_materialized_current_dir(repo_id: str, cache_dir: str | Path) -> Path:
    return _get_materialized_root(repo_id, cache_dir) / "current"


def _get_materialized_temp_dir(repo_id: str, cache_dir: str | Path) -> Path:
    return _get_materialized_root(repo_id, cache_dir) / "current.tmp"


def _validate_snapshot_dir(snapshot_path: str | Path | None, required_files: tuple[str, ...]) -> tuple[bool, str]:
    if not snapshot_path:
        return False, "missing snapshot path"

    resolved_path = Path(snapshot_path)
    if not resolved_path.is_dir():
        return False, f"snapshot directory not found: {resolved_path}"

    try:
        for required_name in required_files:
            required_path = resolved_path / required_name
            if not required_path.exists() or not required_path.is_file():
                return False, f"missing required file: {required_name}"
            if required_path.stat().st_size <= 0:
                return False, f"empty required file: {required_name}"
    except OSError as exc:
        return False, str(exc)

    return True, ""


def _snapshot_download_to_local_dir(repo_id: str, local_dir: str | Path, allow_patterns: list[str], *,
                                    force_download: bool = False, tqdm_class=_SilentTqdm) -> str:
    return snapshot_download(
        repo_id=repo_id,
        local_dir=str(local_dir),
        allow_patterns=allow_patterns,
        force_download=force_download,
        tqdm_class=tqdm_class,
    )


def _download_windows_snapshot(repo_id: str, cache_dir: str, allow_patterns: list[str],
                               required_files: tuple[str, ...], tracker: _SnapshotProgressTracker | None = None) -> str:
    materialized_dir = _get_materialized_current_dir(repo_id, cache_dir)
    is_valid, _reason = _validate_snapshot_dir(materialized_dir, required_files)
    if is_valid:
        if tracker is not None:
            tracker.complete()
        return str(materialized_dir)

    temp_dir = _get_materialized_temp_dir(repo_id, cache_dir)

    def _download_once(*, force_download: bool) -> Path:
        shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.parent.mkdir(parents=True, exist_ok=True)
        _CallbackTqdm.tracker = tracker
        try:
            return Path(
                _snapshot_download_to_local_dir(
                    repo_id,
                    temp_dir,
                    allow_patterns,
                    force_download=force_download,
                    tqdm_class=_CallbackTqdm,
                )
            )
        finally:
            _CallbackTqdm.tracker = None

    downloaded_dir = _download_once(force_download=False)
    is_valid, validation_error = _validate_snapshot_dir(downloaded_dir, required_files)
    if not is_valid:
        if tracker is not None:
            tracker.attach(tracker.total_bytes, 0)
        downloaded_dir = _download_once(force_download=True)
        is_valid, validation_error = _validate_snapshot_dir(downloaded_dir, required_files)

    if not is_valid:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RuntimeError(f"Downloaded snapshot is incomplete for '{repo_id}': {validation_error}.")

    shutil.rmtree(materialized_dir, ignore_errors=True)
    temp_dir.replace(materialized_dir)
    if tracker is not None:
        tracker.complete()
    return str(materialized_dir)


def _download_snapshot(repo_id: str, cache_dir: str, allow_patterns: list[str],
                       required_files: tuple[str, ...], tracker: _SnapshotProgressTracker | None = None) -> str:
    if os.name == "nt":
        return _download_windows_snapshot(repo_id, cache_dir, allow_patterns, required_files, tracker)

    _CallbackTqdm.tracker = tracker
    try:
        snapshot_dir = snapshot_download(
            repo_id=repo_id,
            cache_dir=cache_dir,
            allow_patterns=allow_patterns,
            tqdm_class=_CallbackTqdm,
        )
    finally:
        _CallbackTqdm.tracker = None

    is_valid, validation_error = _validate_snapshot_dir(snapshot_dir, required_files)
    if not is_valid:
        raise RuntimeError(f"Downloaded snapshot is incomplete for '{repo_id}': {validation_error}.")
    if tracker is not None:
        tracker.complete()
    return snapshot_dir


class LocalNLLBTranslator:
    def __init__(self):
        self._translator = None
        self._tokenizer = None
        self._model_dir = None
        self._tokenizer_dir = None

    def ensure_ready(self, on_progress=None, on_status=None):
        cache_dir = get_translation_cache_dir()
        cache_dir_str = str(cache_dir)

        def emit_prepare_progress(base: float, span: float, fraction: float):
            if on_progress is None:
                return
            fraction = max(0.0, min(float(fraction), 1.0))
            on_progress(base + (span * fraction))

        if on_status:
            on_status("Preparing local NLLB translation model...")

        model_total_bytes, model_cached_bytes = _get_snapshot_download_status(
            NLLB_MODEL_REPO,
            cache_dir_str,
            MODEL_ALLOW_PATTERNS,
        )
        if on_status and model_total_bytes > model_cached_bytes:
            on_status(
                f"Downloading local NLLB model ({_format_download_size(model_total_bytes)})..."
            )

        model_tracker = _SnapshotProgressTracker(
            model_total_bytes,
            completed_bytes=model_cached_bytes,
            on_progress=lambda progress, _downloaded, _total: emit_prepare_progress(0.0, 0.35, progress),
        )
        model_tracker.emit()

        try:
            self._model_dir = _download_snapshot(
                repo_id=NLLB_MODEL_REPO,
                cache_dir=cache_dir_str,
                allow_patterns=MODEL_ALLOW_PATTERNS,
                required_files=MODEL_REQUIRED_FILES,
                tracker=model_tracker,
            )
        except Exception as exc:
            raise RuntimeError(
                "Local NLLB model download failed. Check your internet connection or update the configured Hugging Face repo id. "
                f"Details: {exc}"
            ) from exc
        emit_prepare_progress(0.35, 0.0, 1.0)

        if on_status:
            on_status("Preparing local NLLB tokenizer...")

        tokenizer_total_bytes, tokenizer_cached_bytes = _get_snapshot_download_status(
            NLLB_TOKENIZER_REPO,
            cache_dir_str,
            TOKENIZER_ALLOW_PATTERNS,
        )
        if on_status and tokenizer_total_bytes > tokenizer_cached_bytes:
            on_status(
                f"Downloading local NLLB tokenizer ({_format_download_size(tokenizer_total_bytes)})..."
            )

        tokenizer_tracker = _SnapshotProgressTracker(
            tokenizer_total_bytes,
            completed_bytes=tokenizer_cached_bytes,
            on_progress=lambda progress, _downloaded, _total: emit_prepare_progress(0.35, 0.15, progress),
        )
        tokenizer_tracker.emit()

        try:
            self._tokenizer_dir = _download_snapshot(
                repo_id=NLLB_TOKENIZER_REPO,
                cache_dir=cache_dir_str,
                allow_patterns=TOKENIZER_ALLOW_PATTERNS,
                required_files=TOKENIZER_REQUIRED_FILES,
                tracker=tokenizer_tracker,
            )
        except Exception as exc:
            raise RuntimeError(
                "Local NLLB tokenizer download failed. Check your internet connection. "
                f"Details: {exc}"
            ) from exc
        emit_prepare_progress(0.50, 0.0, 1.0)

        if self._translator is None:
            if on_status:
                on_status("Loading local NLLB model...")
            import ctranslate2

            self._translator = ctranslate2.Translator(
                self._model_dir,
                device="cpu",
                compute_type="int8",
                inter_threads=_LOCAL_INTER_THREADS,
                intra_threads=_LOCAL_INTRA_THREADS,
            )
        emit_prepare_progress(0.50, 0.03, 1.0)

        if self._tokenizer is None:
            if on_status:
                on_status("Loading local NLLB tokenizer...")
            from transformers import AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(self._tokenizer_dir, use_fast=False)
        emit_prepare_progress(0.53, 0.02, 1.0)

    def translate_batch(self, batch, source_language: str, target_language: str) -> dict[int, str]:
        if self._translator is None or self._tokenizer is None:
            raise RuntimeError("Local translation model is not ready.")

        source_code = self._resolve_source_code(batch, source_language)
        target_code = NLLB_LANGUAGE_CODES.get(target_language)
        if not target_code:
            raise RuntimeError(f"Local NLLB translation does not support target language '{target_language}'.")

        self._tokenizer.src_lang = source_code
        source_tokens = []
        for entry in batch:
            token_ids = self._tokenizer.encode(entry.original_text)
            source_tokens.append(self._tokenizer.convert_ids_to_tokens(token_ids))

        results = self._translator.translate_batch(
            source_tokens,
            target_prefix=[[target_code]] * len(source_tokens),
            beam_size=_LOCAL_BEAM_SIZE,
        )

        translations: dict[int, str] = {}
        for entry, result in zip(batch, results):
            hypothesis = list(result.hypotheses[0])
            if hypothesis and hypothesis[0] == target_code:
                hypothesis = hypothesis[1:]
            hypothesis = [token for token in hypothesis if token not in {"</s>", "<pad>"}]
            token_ids = self._tokenizer.convert_tokens_to_ids(hypothesis)
            translations[entry.index] = self._tokenizer.decode(token_ids, skip_special_tokens=True).strip()

        return translations

    def _resolve_source_code(self, batch, source_language: str) -> str:
        if source_language and source_language in NLLB_LANGUAGE_CODES:
            return NLLB_LANGUAGE_CODES[source_language]

        sample_text = "\n".join(entry.original_text for entry in batch if entry.original_text.strip())
        if not sample_text:
            return NLLB_LANGUAGE_CODES["English"]

        try:
            from langdetect import DetectorFactory, detect

            DetectorFactory.seed = 0
            detected = detect(sample_text).lower()
        except Exception:
            return NLLB_LANGUAGE_CODES["English"]

        if detected.startswith("zh"):
            return DETECTED_LANGUAGE_CODES.get(detected, "zho_Hans")
        return DETECTED_LANGUAGE_CODES.get(detected, NLLB_LANGUAGE_CODES["English"])
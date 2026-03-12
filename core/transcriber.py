import io
import os
import shutil
import threading
import time
from pathlib import Path

from huggingface_hub import snapshot_download
from tqdm.auto import tqdm


_IMPORT_LOCK = threading.Lock()
_WARMUP_THREAD = None
_WHISPER_MODEL_CLASS = None
_RUNTIME_STATE = "idle"
_RUNTIME_ERROR = ""
_WHISPER_CACHE_DIR = Path.home() / ".cache" / "whisper"
_MATERIALIZED_DIRNAME = "materialized"
_MODEL_ALLOW_PATTERNS = [
    "config.json",
    "preprocessor_config.json",
    "model.bin",
    "tokenizer.json",
    "vocabulary.*",
]
_REQUIRED_MODEL_FILES = ("config.json", "model.bin", "tokenizer.json")


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


def get_local_whisper_cache_dir() -> Path:
    _WHISPER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _WHISPER_CACHE_DIR


def _get_model_repo_id(model_size: str) -> str:
    from faster_whisper import utils as whisper_utils

    model_repo = getattr(whisper_utils, "_MODELS", {}).get(model_size)
    if model_repo is None:
        raise ValueError(f"Invalid model size '{model_size}'")
    return model_repo


def _get_repo_cache_dir(repo_id: str, cache_dir: str | None = None) -> Path:
    resolved_cache_dir = Path(cache_dir or get_local_whisper_cache_dir())
    return resolved_cache_dir / f"models--{repo_id.replace('/', '--')}"


def _get_materialized_root(repo_id: str, cache_dir: str | None = None) -> Path:
    return _get_repo_cache_dir(repo_id, cache_dir=cache_dir) / _MATERIALIZED_DIRNAME


def _get_materialized_current_dir(repo_id: str, cache_dir: str | None = None) -> Path:
    return _get_materialized_root(repo_id, cache_dir=cache_dir) / "current"


def _get_materialized_temp_dir(repo_id: str, cache_dir: str | None = None) -> Path:
    return _get_materialized_root(repo_id, cache_dir=cache_dir) / "current.tmp"


def _build_link_target_path(link_path: Path, link_target: str) -> Path:
    return Path(os.path.normpath(os.path.join(str(link_path.parent), link_target)))


def _resolve_snapshot_entry_source(entry_path: Path) -> Path:
    if entry_path.is_symlink():
        return _build_link_target_path(entry_path, os.readlink(entry_path))
    return entry_path


def _materialize_model_directory(snapshot_path: str | Path, repo_id: str,
                                 cache_dir: str | None = None) -> str:
    snapshot_dir = Path(snapshot_path)
    materialized_dir = _get_materialized_root(repo_id, cache_dir=cache_dir) / snapshot_dir.name

    if _validate_model_snapshot(materialized_dir)[0]:
        return str(materialized_dir)

    materialized_dir.mkdir(parents=True, exist_ok=True)

    for entry in snapshot_dir.iterdir():
        if entry.is_dir():
            continue

        source_path = _resolve_snapshot_entry_source(entry)
        destination_path = materialized_dir / entry.name

        if destination_path.exists():
            try:
                if destination_path.stat().st_size == source_path.stat().st_size:
                    continue
            except OSError:
                pass

        shutil.copy2(source_path, destination_path)

    return str(materialized_dir)


def _finalize_model_directory(snapshot_path: str | Path, repo_id: str,
                              cache_dir: str | None = None) -> str:
    if os.name != "nt":
        return str(snapshot_path)
    return _materialize_model_directory(snapshot_path, repo_id, cache_dir=cache_dir)


def _finalize_and_validate_model_directory(model_path: str | Path | None, repo_id: str,
                                           cache_dir: str | None = None) -> tuple[str | None, str]:
    if not model_path:
        return None, "missing model path"

    try:
        finalized_path = _finalize_model_directory(model_path, repo_id, cache_dir=cache_dir)
    except OSError as exc:
        return None, str(exc)

    is_valid, reason = _validate_model_snapshot(finalized_path)
    if not is_valid:
        return None, reason
    return finalized_path, ""


def _validate_model_snapshot(model_path: str | Path | None) -> tuple[bool, str]:
    if not model_path:
        return False, "missing model path"

    snapshot_path = Path(model_path)
    if not snapshot_path.is_dir():
        return False, f"snapshot directory not found: {snapshot_path}"

    try:
        for required_name in _REQUIRED_MODEL_FILES:
            required_path = snapshot_path / required_name
            source_path = _resolve_snapshot_entry_source(required_path)
            if not os.path.lexists(str(required_path)):
                return False, f"missing required file: {required_name}"
            if not source_path.exists() or not source_path.is_file():
                return False, f"missing required file: {required_name}"
            if source_path.stat().st_size <= 0:
                return False, f"empty required file: {required_name}"
    except OSError as exc:
        return False, str(exc)

    return True, ""


def _is_valid_model_snapshot(model_path: str | Path | None) -> bool:
    is_valid, _ = _validate_model_snapshot(model_path)
    return is_valid


def _iter_snapshot_candidates(repo_id: str, cache_dir: str | None = None):
    repo_cache_dir = _get_repo_cache_dir(repo_id, cache_dir=cache_dir)
    refs_main = repo_cache_dir / "refs" / "main"
    if refs_main.exists():
        try:
            revision = refs_main.read_text(encoding="utf-8").strip()
        except OSError:
            revision = ""
        if revision:
            yield repo_cache_dir / "snapshots" / revision

    snapshots_dir = repo_cache_dir / "snapshots"
    if snapshots_dir.is_dir():
        try:
            snapshot_dirs = sorted(
                (path for path in snapshots_dir.iterdir() if path.is_dir()),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            snapshot_dirs = []

        for snapshot_dir in snapshot_dirs:
            yield snapshot_dir


def _resolve_valid_model_snapshot(model_path: str | Path | None, repo_id: str,
                                  cache_dir: str | None = None, retries: int = 3,
                                  retry_delay: float = 0.35) -> tuple[str | None, str]:
    last_reason = "missing model path"
    seen_paths = set()

    for attempt in range(max(1, retries)):
        candidates = []
        if model_path:
            candidates.append(Path(model_path))
        candidates.extend(_iter_snapshot_candidates(repo_id, cache_dir=cache_dir))

        for candidate in candidates:
            candidate_key = str(candidate)
            if candidate_key in seen_paths and attempt == 0:
                continue
            seen_paths.add(candidate_key)

            finalized_path, reason = _finalize_and_validate_model_directory(
                candidate,
                repo_id,
                cache_dir=cache_dir,
            )
            if finalized_path is not None:
                return finalized_path, ""
            last_reason = reason

        if attempt < retries - 1:
            time.sleep(retry_delay)

    return None, last_reason


def _purge_model_cache(repo_id: str, cache_dir: str | None = None):
    shutil.rmtree(_get_repo_cache_dir(repo_id, cache_dir=cache_dir), ignore_errors=True)


def _snapshot_download(repo_id: str, cache_dir: str, *, local_files_only: bool = False,
                       force_download: bool = False, tqdm_class=_SilentTqdm) -> str:
    return snapshot_download(
        repo_id,
        cache_dir=cache_dir,
        allow_patterns=_MODEL_ALLOW_PATTERNS,
        local_files_only=local_files_only,
        force_download=force_download,
        tqdm_class=tqdm_class,
    )


def _snapshot_download_to_local_dir(repo_id: str, local_dir: str | Path, *,
                                    force_download: bool = False,
                                    tqdm_class=_SilentTqdm) -> str:
    return snapshot_download(
        repo_id,
        local_dir=str(local_dir),
        allow_patterns=_MODEL_ALLOW_PATTERNS,
        force_download=force_download,
        tqdm_class=tqdm_class,
    )


def get_model_download_status(model_size: str, cache_dir: str | None = None) -> dict:
    resolved_cache_dir = str(cache_dir or get_local_whisper_cache_dir())
    repo_id = _get_model_repo_id(model_size)
    files = snapshot_download(
        repo_id,
        cache_dir=resolved_cache_dir,
        allow_patterns=_MODEL_ALLOW_PATTERNS,
        dry_run=True,
        tqdm_class=_SilentTqdm,
    )

    total_bytes = 0
    cached_bytes = 0
    for item in files:
        file_size = int(getattr(item, "file_size", 0) or 0)
        total_bytes += file_size
        if getattr(item, "is_cached", False) and not getattr(item, "will_download", False):
            cached_bytes += file_size

    return {
        "model_size": model_size,
        "repo_id": repo_id,
        "cache_dir": resolved_cache_dir,
        "total_bytes": total_bytes,
        "cached_bytes": cached_bytes,
        "is_cached": total_bytes > 0 and cached_bytes >= total_bytes,
    }


def is_model_cached(model_size: str, cache_dir: str | None = None) -> bool:
    resolved_cache_dir = str(cache_dir or get_local_whisper_cache_dir())
    repo_id = _get_model_repo_id(model_size)
    if os.name == "nt":
        return _is_valid_model_snapshot(_get_materialized_current_dir(repo_id, cache_dir=resolved_cache_dir))

    try:
        model_path = _snapshot_download(
            repo_id,
            resolved_cache_dir,
            local_files_only=True,
            tqdm_class=_SilentTqdm,
        )
    except Exception:
        return False
    resolved_model_path, _ = _resolve_valid_model_snapshot(
        model_path,
        repo_id,
        cache_dir=resolved_cache_dir,
        retries=1,
    )
    return resolved_model_path is not None


def download_model_files(model_size: str, cache_dir: str | None = None, on_progress=None) -> str:
    resolved_cache_dir = str(cache_dir or get_local_whisper_cache_dir())
    repo_id = _get_model_repo_id(model_size)

    if os.name == "nt":
        materialized_dir = _get_materialized_current_dir(repo_id, cache_dir=resolved_cache_dir)
        if _is_valid_model_snapshot(materialized_dir):
            if on_progress is not None:
                on_progress(1.0, 1, 1)
            return str(materialized_dir)

        status = get_model_download_status(model_size, cache_dir=resolved_cache_dir)
        tracker = _SnapshotProgressTracker(
            total_bytes=status["total_bytes"],
            completed_bytes=status["cached_bytes"],
            on_progress=on_progress,
        )
        tracker.emit()

        temp_dir = _get_materialized_temp_dir(repo_id, cache_dir=resolved_cache_dir)

        def _download_once(*, force_download: bool) -> str:
            shutil.rmtree(temp_dir, ignore_errors=True)
            temp_dir.parent.mkdir(parents=True, exist_ok=True)
            _CallbackTqdm.tracker = tracker
            try:
                return _snapshot_download_to_local_dir(
                    status["repo_id"],
                    temp_dir,
                    force_download=force_download,
                    tqdm_class=_CallbackTqdm,
                )
            finally:
                _CallbackTqdm.tracker = None

        downloaded_dir = Path(_download_once(force_download=False))
        is_valid, validation_error = _validate_model_snapshot(downloaded_dir)
        if not is_valid:
            tracker.attach(status["total_bytes"], 0)
            downloaded_dir = Path(_download_once(force_download=True))
            is_valid, validation_error = _validate_model_snapshot(downloaded_dir)

        if not is_valid:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise RuntimeError(
                f"Downloaded Whisper model cache is incomplete for '{model_size}': {validation_error}."
            )

        shutil.rmtree(materialized_dir, ignore_errors=True)
        temp_dir.replace(materialized_dir)
        tracker.complete()
        return str(materialized_dir)

    if is_model_cached(model_size, cache_dir=resolved_cache_dir):
        model_path = _snapshot_download(
            repo_id,
            resolved_cache_dir,
            local_files_only=True,
            tqdm_class=_SilentTqdm,
        )
        resolved_model_path, _ = _resolve_valid_model_snapshot(
            model_path,
            repo_id,
            cache_dir=resolved_cache_dir,
            retries=1,
        )
        if resolved_model_path is not None:
            if on_progress is not None:
                on_progress(1.0, 1, 1)
            return resolved_model_path

        _purge_model_cache(repo_id, cache_dir=resolved_cache_dir)
    elif _get_repo_cache_dir(repo_id, cache_dir=resolved_cache_dir).exists():
        _purge_model_cache(repo_id, cache_dir=resolved_cache_dir)

    status = get_model_download_status(model_size, cache_dir=resolved_cache_dir)

    tracker = _SnapshotProgressTracker(
        total_bytes=status["total_bytes"],
        completed_bytes=status["cached_bytes"],
        on_progress=on_progress,
    )
    tracker.emit()

    def _download_once(*, force_download: bool) -> str:
        _CallbackTqdm.tracker = tracker
        try:
            return _snapshot_download(
                status["repo_id"],
                resolved_cache_dir,
                force_download=force_download,
                tqdm_class=_CallbackTqdm,
            )
        finally:
            _CallbackTqdm.tracker = None

    model_path = _download_once(force_download=False)
    resolved_model_path, validation_error = _resolve_valid_model_snapshot(
        model_path,
        repo_id,
        cache_dir=resolved_cache_dir,
        retries=4,
    )
    if resolved_model_path is None:
        _purge_model_cache(repo_id, cache_dir=resolved_cache_dir)
        tracker.attach(status["total_bytes"], 0)
        model_path = _download_once(force_download=True)
        resolved_model_path, validation_error = _resolve_valid_model_snapshot(
            model_path,
            repo_id,
            cache_dir=resolved_cache_dir,
            retries=4,
        )

    if resolved_model_path is None:
        raise RuntimeError(
            f"Downloaded Whisper model cache is incomplete for '{model_size}': {validation_error}."
        )

    tracker.complete()
    return resolved_model_path


def get_transcriber_runtime_status() -> dict:
    return {
        "state": _RUNTIME_STATE,
        "error": _RUNTIME_ERROR,
        "ready": _WHISPER_MODEL_CLASS is not None,
    }


def _ensure_whisper_model_class():
    global _WHISPER_MODEL_CLASS, _RUNTIME_STATE, _RUNTIME_ERROR

    if _WHISPER_MODEL_CLASS is not None:
        return _WHISPER_MODEL_CLASS

    with _IMPORT_LOCK:
        if _WHISPER_MODEL_CLASS is not None:
            return _WHISPER_MODEL_CLASS

        _RUNTIME_STATE = "loading"
        _RUNTIME_ERROR = ""
        try:
            from faster_whisper import WhisperModel as ImportedWhisperModel

            _WHISPER_MODEL_CLASS = ImportedWhisperModel
            _RUNTIME_STATE = "ready"
        except Exception as exc:
            _RUNTIME_STATE = "error"
            _RUNTIME_ERROR = str(exc)
            raise

    return _WHISPER_MODEL_CLASS


def warmup_transcriber_runtime() -> dict:
    try:
        _ensure_whisper_model_class()
    except Exception:
        pass
    return get_transcriber_runtime_status()


def warmup_transcriber_runtime_async(on_complete=None):
    global _WARMUP_THREAD

    if _WHISPER_MODEL_CLASS is not None:
        if on_complete is not None:
            try:
                on_complete(get_transcriber_runtime_status())
            except Exception:
                pass
        return None

    if _WARMUP_THREAD is not None and _WARMUP_THREAD.is_alive():
        return _WARMUP_THREAD

    def _runner():
        status = warmup_transcriber_runtime()
        if on_complete is not None:
            try:
                on_complete(status)
            except Exception:
                pass

    _WARMUP_THREAD = threading.Thread(target=_runner, daemon=True)
    _WARMUP_THREAD.start()
    return _WARMUP_THREAD

class Transcriber:
    def __init__(self):
        self.model = None
        self.model_size = "base"
        self.loaded_model_size = None
        self._cancel = False

    def load_model(self, model_size="base"):
        """Load WhisperModel. Sizes: tiny, base, small, medium, large-v2"""
        self.model_size = model_size
        print(f"--- Loading Whisper Model: {model_size} ---")
        whisper_model_class = _ensure_whisper_model_class()
        cache_dir = str(get_local_whisper_cache_dir())
        repo_id = _get_model_repo_id(model_size)

        for attempt in range(2):
            try:
                model_path = download_model_files(model_size, cache_dir=cache_dir)
                self.model = whisper_model_class(model_path, device="cpu", compute_type="int8")
                self.loaded_model_size = model_size
                print(f"--- Model Loaded Successfully ---")
                return
            except Exception as e:
                if attempt == 0 and "model.bin" in str(e).lower():
                    _purge_model_cache(repo_id, cache_dir=cache_dir)
                    continue
                print(f"--- Error Loading Model: {e} ---")
                raise e

    def is_model_cached(self, model_size=None):
        target_model_size = model_size or self.model_size
        return is_model_cached(target_model_size, cache_dir=str(get_local_whisper_cache_dir()))

    def get_model_download_status(self, model_size=None):
        target_model_size = model_size or self.model_size
        return get_model_download_status(target_model_size, cache_dir=str(get_local_whisper_cache_dir()))

    def download_model(self, model_size=None, on_progress=None, on_complete=None, on_error=None):
        target_model_size = model_size or self.model_size

        def _worker():
            try:
                model_path = download_model_files(
                    target_model_size,
                    cache_dir=str(get_local_whisper_cache_dir()),
                    on_progress=on_progress,
                )
                if on_complete:
                    on_complete(model_path)
            except Exception as exc:
                if on_error:
                    on_error(str(exc))

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        return thread

    def transcribe(
        self,
        audio_path,
        language=None,
        voice_adjustment="normal",
        word_timestamps=False,
        on_progress=None,
        on_complete=None,
        on_error=None,
    ):
        """Run transcription in background thread.
        on_progress(float) - 0.0 to 1.0
        on_complete(list[dict]) - list of {index, start, end, text, words?}
        on_error(str) - error message
        """
        self._cancel = False
        thread = threading.Thread(
            target=self._transcribe_worker,
            args=(audio_path, language, voice_adjustment, word_timestamps,
                  on_progress, on_complete, on_error),
            daemon=True,
        )
        thread.start()
        return thread

    def _transcribe_worker(self, audio_path, language, voice_adjustment, word_timestamps,
                           on_progress, on_complete, on_error):
        try:
            if self.model is None or self.loaded_model_size != self.model_size:
                self.load_model(self.model_size)

            transcribe_kwargs = {
                "language": language,
                "beam_size": 5,
            }

            if word_timestamps:
                transcribe_kwargs["word_timestamps"] = True

            adjustment = (voice_adjustment or "normal").lower()
            if adjustment == "low":
                transcribe_kwargs["vad_filter"] = True
                transcribe_kwargs["vad_parameters"] = {
                    "min_silence_duration_ms": 900,
                    "speech_pad_ms": 400,
                }
            elif adjustment == "high":
                transcribe_kwargs["vad_filter"] = True
                transcribe_kwargs["vad_parameters"] = {
                    "min_silence_duration_ms": 250,
                    "speech_pad_ms": 200,
                }

            segments, info = self.model.transcribe(audio_path, **transcribe_kwargs)
            duration = info.duration
            results = []
            idx = 0

            for segment in segments:
                if self._cancel:
                    return
                idx += 1
                entry = {
                    "index": idx,
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text.strip(),
                }

                if word_timestamps and hasattr(segment, 'words') and segment.words:
                    entry["words"] = [
                        {"word": w.word, "start": w.start, "end": w.end}
                        for w in segment.words
                    ]

                results.append(entry)
                if on_progress and duration > 0:
                    on_progress(min(segment.end / duration, 1.0))

            if on_progress:
                on_progress(1.0)
            if on_complete:
                on_complete(results)
        except Exception as e:
            if on_error:
                on_error(str(e))

    def cancel(self):
        self._cancel = True

AVAILABLE_MODELS = ["tiny", "base", "small", "medium", "large-v2"]

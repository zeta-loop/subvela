import threading
import tempfile
import os
from core.video_utils import extract_audio


class CloudTranscriber:
    def __init__(self):
        self._cancel = False

    def transcribe(
        self,
        video_path,
        provider="groq",
        api_key="",
        language=None,
        word_timestamps=False,
        on_progress=None,
        on_complete=None,
        on_error=None,
    ):
        self._cancel = False
        thread = threading.Thread(
            target=self._transcribe_worker,
            args=(video_path, provider, api_key, language, word_timestamps,
                  on_progress, on_complete, on_error),
            daemon=True,
        )
        thread.start()
        return thread

    def _transcribe_worker(self, video_path, provider, api_key, language,
                           word_timestamps, on_progress, on_complete, on_error):
        try:
            if not api_key:
                raise ValueError(f"No API key provided for {provider}")

            # Extract audio to temp file
            if on_progress:
                on_progress(0.05)

            tmp_dir = tempfile.gettempdir()
            audio_path = os.path.join(tmp_dir, "cloud_transcribe_audio.wav")
            extract_audio(video_path, audio_path, format="wav")

            if self._cancel:
                return
            if on_progress:
                on_progress(0.1)

            if provider == "groq":
                results = self._transcribe_groq(audio_path, api_key, language, word_timestamps, on_progress)
            elif provider == "openai":
                results = self._transcribe_openai(audio_path, api_key, language, word_timestamps, on_progress)
            else:
                raise ValueError(f"Unknown provider: {provider}")

            if self._cancel:
                return

            # Clean up temp file
            try:
                os.remove(audio_path)
            except Exception:
                pass

            if on_progress:
                on_progress(1.0)
            if on_complete:
                on_complete(results)

        except Exception as e:
            if on_error:
                on_error(str(e))

    def _transcribe_groq(self, audio_path, api_key, language, word_timestamps, on_progress):
        from groq import Groq

        client = Groq(api_key=api_key)

        if on_progress:
            on_progress(0.2)

        kwargs = {
            "model": "whisper-large-v3",
            "response_format": "verbose_json",
        }
        if language:
            kwargs["language"] = language
        if word_timestamps:
            kwargs["timestamp_granularities"] = ["word", "segment"]

        with open(audio_path, "rb") as f:
            kwargs["file"] = (os.path.basename(audio_path), f)
            transcription = client.audio.transcriptions.create(**kwargs)

        if on_progress:
            on_progress(0.8)

        return self._parse_response(transcription, word_timestamps)

    def _transcribe_openai(self, audio_path, api_key, language, word_timestamps, on_progress):
        from openai import OpenAI

        client = OpenAI(api_key=api_key)

        if on_progress:
            on_progress(0.2)

        kwargs = {
            "model": "whisper-1",
            "response_format": "verbose_json",
        }
        if language:
            kwargs["language"] = language
        if word_timestamps:
            kwargs["timestamp_granularities"] = ["word", "segment"]

        with open(audio_path, "rb") as f:
            kwargs["file"] = f
            transcription = client.audio.transcriptions.create(**kwargs)

        if on_progress:
            on_progress(0.8)

        return self._parse_response(transcription, word_timestamps)

    def _parse_response(self, transcription, word_timestamps):
        results = []
        segments = getattr(transcription, 'segments', None) or []

        for idx, seg in enumerate(segments, 1):
            entry = {
                "index": idx,
                "start": seg.get("start", 0) if isinstance(seg, dict) else getattr(seg, "start", 0),
                "end": seg.get("end", 0) if isinstance(seg, dict) else getattr(seg, "end", 0),
                "text": (seg.get("text", "") if isinstance(seg, dict) else getattr(seg, "text", "")).strip(),
            }

            if word_timestamps:
                words_data = []
                seg_words = seg.get("words", []) if isinstance(seg, dict) else getattr(seg, "words", [])
                for w in (seg_words or []):
                    if isinstance(w, dict):
                        words_data.append({
                            "word": w.get("word", ""),
                            "start": w.get("start", 0),
                            "end": w.get("end", 0),
                        })
                    else:
                        words_data.append({
                            "word": getattr(w, "word", ""),
                            "start": getattr(w, "start", 0),
                            "end": getattr(w, "end", 0),
                        })
                entry["words"] = words_data

            # Also check top-level words for OpenAI with timestamp_granularities=["word"]
            if word_timestamps and not entry.get("words"):
                top_words = getattr(transcription, 'words', None) or []
                seg_start = entry["start"]
                seg_end = entry["end"]
                words_data = []
                for w in top_words:
                    w_start = w.get("start", 0) if isinstance(w, dict) else getattr(w, "start", 0)
                    w_end = w.get("end", 0) if isinstance(w, dict) else getattr(w, "end", 0)
                    if w_start >= seg_start and w_end <= seg_end + 0.1:
                        words_data.append({
                            "word": w.get("word", "") if isinstance(w, dict) else getattr(w, "word", ""),
                            "start": w_start,
                            "end": w_end,
                        })
                entry["words"] = words_data

            results.append(entry)

        return results

    def cancel(self):
        self._cancel = True

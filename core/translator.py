import threading

from dotenv import load_dotenv

from core.config import get_api_key

load_dotenv()

BATCH_SIZE = 20
LOCAL_NLLB_BATCH_SIZE = 8

LANGUAGES = [
    "Afrikaans", "Arabic", "Armenian", "Azerbaijani", "Belarusian", "Bosnian",
    "Bulgarian", "Catalan", "Chinese (Simplified)", "Chinese (Traditional)",
    "Croatian", "Czech", "Danish", "Dutch", "English", "Estonian", "Filipino",
    "Finnish", "French", "Galician", "Georgian", "German", "Greek", "Hebrew",
    "Hindi", "Hungarian", "Icelandic", "Indonesian", "Italian", "Japanese",
    "Kannada", "Kazakh", "Korean", "Latvian", "Lithuanian", "Macedonian",
    "Malay", "Marathi", "Mongolian", "Norwegian", "Persian", "Polish",
    "Portuguese", "Romanian", "Russian", "Serbian", "Slovak", "Slovenian",
    "Spanish", "Swahili", "Swedish", "Tamil", "Telugu", "Thai", "Turkish",
    "Ukrainian", "Urdu", "Vietnamese", "Welsh"
]

class Translator:
    def __init__(self, provider: str = "local_nllb", source_language: str = "Auto Detect"):
        self.provider = provider
        self.source_language = source_language
        self._cancel = False
        self._local_provider = None

    def translate(self, entries, target_language, on_progress=None, on_complete=None, on_error=None, on_status=None):
        """Translate subtitle entries in batches using background thread.
        entries: list of SubtitleEntry objects
        target_language: target language name
        on_progress(float) - 0.0 to 1.0
        on_complete(dict) - {index: translated_text}
        on_error(str) - error message
        """
        self._cancel = False
        thread = threading.Thread(target=self._translate_worker,
                                  args=(entries, target_language, on_progress, on_complete, on_error, on_status),
                                  daemon=True)
        thread.start()
        return thread

    def _translate_worker(self, entries, target_language, on_progress, on_complete, on_error, on_status=None):
        try:
            translations = {}
            total = len(entries)
            batch_size = LOCAL_NLLB_BATCH_SIZE if self.provider == "local_nllb" else BATCH_SIZE

            if self.provider == "local_nllb":
                if on_status:
                    on_status("Preparing local NLLB translation...")
                self._ensure_local_provider(on_progress=on_progress, on_status=on_status)

            for batch_start in range(0, total, batch_size):
                if self._cancel:
                    return

                batch = entries[batch_start:batch_start + batch_size]
                if on_status:
                    on_status(
                        f"Translating batch {batch_start // batch_size + 1}/{(total + batch_size - 1) // batch_size} via {self._provider_label()}..."
                    )

                if self.provider == "local_nllb":
                    translations.update(self._local_provider.translate_batch(batch, self.source_language, target_language))
                else:
                    translations.update(self._translate_with_cloud_provider(batch, target_language))

                if on_progress:
                    done = min(batch_start + batch_size, total)
                    if self.provider == "local_nllb":
                        on_progress(0.55 + ((done / total) * 0.45))
                    else:
                        on_progress(done / total)

            if on_complete:
                on_complete(translations)
        except Exception as e:
            if on_error:
                message = str(e)
                lowered = message.lower()
                if "mkl_malloc" in lowered or "failed to allocate memory" in lowered or "std::bad_alloc" in lowered:
                    message = (
                        "Local NLLB translation ran out of memory. Close other heavy apps and try again, "
                        "or switch to a cloud translation provider in Settings."
                    )
                on_error(message)

    def _ensure_local_provider(self, on_progress=None, on_status=None):
        if self._local_provider is None:
            from core.translation_nllb import LocalNLLBTranslator

            self._local_provider = LocalNLLBTranslator()
        self._local_provider.ensure_ready(on_progress=on_progress, on_status=on_status)

    def _translate_with_cloud_provider(self, batch, target_language: str) -> dict[int, str]:
        from core.translation_llm import LLMTranslatorProvider

        api_key = get_api_key(self.provider)
        translator = LLMTranslatorProvider(self.provider, api_key)
        return translator.translate_batch(target_language, batch)

    def _provider_label(self) -> str:
        return {
            "local_nllb": "Local NLLB",
            "gemini": "Gemini",
            "openai": "OpenAI",
            "claude": "Claude",
        }.get(self.provider, self.provider)

    def cancel(self):
        self._cancel = True

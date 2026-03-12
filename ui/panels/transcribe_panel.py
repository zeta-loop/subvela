import customtkinter as ctk
from app.theme import COLORS, FONTS, SPACING, RADIUS, get_font_family
from core.transcriber import Transcriber
from core.cloud_transcriber import CloudTranscriber
from core.subtitle_model import SubtitleEntry, WordEntry
from core.config import get_api_key


class TranscribePanel(ctk.CTkFrame):
    def __init__(self, parent, state, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.state = state
        self.transcriber = Transcriber()
        self.cloud_transcriber = CloudTranscriber()
        self._is_downloading_model = False
        self._is_downloading_translation_model = False
        self._loading_dots = 0
        self._loading_after_id = None
        self._translation_status_prefix = "Translating..."

        self.grid_columnconfigure(0, weight=1)

        ff = get_font_family()

        # Title
        ctk.CTkLabel(
            self, text="Transcribe & Translate",
            font=ctk.CTkFont(family=ff, size=FONTS["display"][1], weight="bold"),
            text_color=COLORS["text_heading"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=SPACING["lg"], pady=(SPACING["lg"], SPACING["md"]))

        # --- Transcription Section ---
        trans_section = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"], corner_radius=RADIUS["card"],
                                      border_width=2, border_color=COLORS["accent_muted"])
        trans_section.grid(row=1, column=0, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["md"]))
        trans_section.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            trans_section, text="Speech to Text",
            font=ctk.CTkFont(family=ff, size=FONTS["subheading"][1]),
            text_color=COLORS["text_primary"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=SPACING["lg"], pady=(SPACING["md"], SPACING["sm"]))

        self.transcribe_note_label = ctk.CTkLabel(
            trans_section,
            text="Local transcription uses the base model by default for speed. For higher accuracy, switch to a stronger model in Settings or use your own cloud API.",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            text_color=COLORS["text_muted"],
            anchor="w",
            justify="left",
            wraplength=760,
        )
        self.transcribe_note_label.grid(row=1, column=0, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["sm"]))
        trans_section.bind(
            "<Configure>",
            lambda event, label=self.transcribe_note_label: label.configure(wraplength=max(260, event.width - (SPACING["lg"] * 2))),
            add="+",
        )

        # --- Language Setting (right below STT title) ---
        source_frame = ctk.CTkFrame(trans_section, fg_color="transparent")
        source_frame.grid(row=2, column=0, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["md"]))
        source_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            source_frame, text="Spoken:",
            font=ctk.CTkFont(family=ff, size=FONTS["body"][1]),
            text_color=COLORS["text_secondary"],
        ).grid(row=0, column=0, padx=(0, SPACING["md"]))

        self.source_lang_var = ctk.StringVar(value="Auto Detect")
        self.source_lang_dropdown = ctk.CTkComboBox(
            source_frame,
            values=["Auto Detect", "English", "Malay", "Chinese", "Japanese", "French", "German", "Spanish"],
            variable=self.source_lang_var,
            font=ctk.CTkFont(family=ff, size=FONTS["body"][1]),
            dropdown_font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            fg_color=COLORS["entry_bg"],
            border_color=COLORS["entry_border"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            dropdown_fg_color=COLORS["bg_secondary"],
            corner_radius=RADIUS["md"],
            height=32,
            state="readonly",
        )
        self.source_lang_dropdown.grid(row=0, column=1, sticky="ew")

        # Transcribe button + progress
        action_frame = ctk.CTkFrame(trans_section, fg_color="transparent")
        action_frame.grid(row=3, column=0, sticky="ew", padx=SPACING["lg"], pady=SPACING["md"])
        action_frame.grid_columnconfigure(0, weight=0)
        action_frame.grid_columnconfigure(1, weight=1)
        action_frame.grid_columnconfigure(2, weight=0)

        self.transcribe_btn = ctk.CTkButton(
            action_frame,
            text="Transcribe",
            font=ctk.CTkFont(family=ff, size=FONTS["body_bold"][1]),
            fg_color=COLORS["button_primary"],
            hover_color=COLORS["button_primary_hover"],
            text_color=COLORS["button_text"],
            corner_radius=RADIUS["md"],
            height=38,
            width=130,
            command=self._start_transcription,
            cursor="hand2",
        )
        self.transcribe_btn.grid(row=0, column=0, padx=(0, SPACING["md"]))

        self.trans_download_frame = ctk.CTkFrame(action_frame, fg_color="transparent")
        self.trans_download_frame.grid_columnconfigure(0, weight=1)

        self.trans_download_label = ctk.CTkLabel(
            self.trans_download_frame,
            text="",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            text_color=COLORS["text_primary"],
            anchor="w",
        )
        self.trans_download_label.grid(row=0, column=0, sticky="ew", pady=(0, SPACING["xs"]))

        self.trans_download_progress_row = ctk.CTkFrame(self.trans_download_frame, fg_color="transparent")
        self.trans_download_progress_row.grid(row=1, column=0, sticky="ew")
        self.trans_download_progress_row.grid_columnconfigure(0, weight=1)

        self.trans_progress = ctk.CTkProgressBar(
            self.trans_download_progress_row,
            progress_color=COLORS["progress_fill"],
            fg_color=COLORS["progress_bg"],
            height=12,
            corner_radius=6,
        )
        self.trans_progress.grid(row=0, column=0, sticky="ew")
        self.trans_progress.set(0)

        self.trans_pct_label = ctk.CTkLabel(
            self.trans_download_progress_row, text="0%",
            font=ctk.CTkFont(family=ff, size=FONTS["caption"][1]),
            text_color=COLORS["text_muted"],
            width=36,
        )
        self.trans_pct_label.grid(row=0, column=1, padx=(SPACING["xs"], 0))

        self.trans_status = ctk.CTkLabel(
            trans_section, text="",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            text_color=COLORS["text_muted"],
            anchor="w",
        )
        self.trans_status.grid(row=4, column=0, sticky="w", padx=SPACING["lg"], pady=(0, SPACING["sm"]))

        # --- Translation Section ---
        translate_section = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"], corner_radius=RADIUS["card"],
                                          border_width=2, border_color=COLORS["accent_muted"])
        translate_section.grid(row=3, column=0, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["md"]))
        translate_section.grid_columnconfigure(0, weight=1)

        # Translation title
        bi_frame = ctk.CTkFrame(translate_section, fg_color="transparent")
        bi_frame.grid(row=0, column=0, sticky="ew", padx=SPACING["lg"], pady=(SPACING["md"], SPACING["sm"]))

        ctk.CTkLabel(
            bi_frame, text="Translation",
            font=ctk.CTkFont(family=ff, size=FONTS["subheading"][1]),
            text_color=COLORS["text_primary"],
        ).grid(row=0, column=0, sticky="w")

        self.translate_note_label = ctk.CTkLabel(
            translate_section,
            text="Local (Free) translation uses an NLLB model downloaded on first use. You can switch to Gemini, OpenAI, or Claude in Settings.",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            text_color=COLORS["text_muted"],
            anchor="w",
            justify="left",
            wraplength=760,
        )
        self.translate_note_label.grid(row=1, column=0, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["sm"]))
        translate_section.bind(
            "<Configure>",
            lambda event, label=self.translate_note_label: label.configure(wraplength=max(260, event.width - (SPACING["lg"] * 2))),
            add="+",
        )

        # Language selector
        lang_frame = ctk.CTkFrame(translate_section, fg_color="transparent")
        lang_frame.grid(row=2, column=0, sticky="ew", padx=SPACING["lg"])
        lang_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            lang_frame, text="Target:",
            font=ctk.CTkFont(family=ff, size=FONTS["body"][1]),
            text_color=COLORS["text_secondary"],
        ).grid(row=0, column=0, padx=(0, SPACING["md"]))

        from core.translator import LANGUAGES
        self.lang_var = ctk.StringVar(value="Chinese (Simplified)")
        self.lang_dropdown = ctk.CTkComboBox(
            lang_frame,
            values=LANGUAGES,
            variable=self.lang_var,
            font=ctk.CTkFont(family=ff, size=FONTS["body"][1]),
            dropdown_font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            fg_color=COLORS["entry_bg"],
            border_color=COLORS["entry_border"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            dropdown_fg_color=COLORS["bg_secondary"],
            corner_radius=RADIUS["md"],
            height=32,
            state="readonly",
        )
        self.lang_dropdown.grid(row=0, column=1, sticky="ew")

        # Translate button + progress
        t_action = ctk.CTkFrame(translate_section, fg_color="transparent")
        t_action.grid(row=3, column=0, sticky="ew", padx=SPACING["lg"], pady=SPACING["md"])
        t_action.grid_columnconfigure(1, weight=1)

        self.translate_btn = ctk.CTkButton(
            t_action,
            text="Translate",
            font=ctk.CTkFont(family=ff, size=FONTS["body_bold"][1]),
            fg_color=COLORS["button_primary"],
            hover_color=COLORS["button_primary_hover"],
            text_color=COLORS["button_text"],
            corner_radius=RADIUS["md"],
            height=38,
            width=130,
            command=self._start_translation,
            cursor="hand2",
            state="normal" if state.subtitles else "disabled",
        )
        self.translate_btn.grid(row=0, column=0, padx=(0, SPACING["md"]))

        self.tl_progress = ctk.CTkProgressBar(
            t_action,
            progress_color=COLORS["progress_fill"],
            fg_color=COLORS["progress_bg"],
            height=12,
            corner_radius=6,
        )
        self.tl_progress.grid(row=0, column=1, sticky="ew")
        self.tl_progress.set(0)

        self.tl_pct_label = ctk.CTkLabel(
            t_action, text="0%",
            font=ctk.CTkFont(family=ff, size=FONTS["caption"][1]),
            text_color=COLORS["text_muted"],
            width=36,
        )
        self.tl_pct_label.grid(row=0, column=2, padx=(SPACING["xs"], 0))

        self.tl_download_label = ctk.CTkLabel(
            translate_section,
            text="",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            text_color=COLORS["text_primary"],
            anchor="w",
        )
        self.tl_download_label.grid(row=4, column=0, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["xs"]))

        self.tl_status = ctk.CTkLabel(
            translate_section, text="",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            text_color=COLORS["text_muted"],
            anchor="w",
        )
        self.tl_status.grid(row=5, column=0, sticky="w", padx=SPACING["lg"], pady=(0, SPACING["md"]))

        # Listen to state changes
        self.state.add_listener(self._on_state_change)
        self._set_transcribe_action_mode("button")
        self._update_ui_states()

    def _on_state_change(self, field):
        if field in ("subtitles", "video"):
            self._update_ui_states()

    def _update_ui_states(self):
        has_subs = len(self.state.subtitles) > 0
        if has_subs:
            self.translate_btn.configure(state="normal")
        else:
            self.translate_btn.configure(state="disabled")

    def _start_transcription(self):
        if not self.state.video_path:
            self.trans_status.configure(text="No video loaded.", text_color=COLORS["error"])
            return
        if self.state.is_transcribing:
            return

        # Determine language code
        lang_map = {
            "Auto Detect": None,
            "English": "en",
            "Malay": "ms",
            "Chinese": "zh",
            "Japanese": "ja",
            "French": "fr",
            "German": "de",
            "Spanish": "es",
        }
        selected_lang = lang_map.get(self.source_lang_var.get())
        use_word_timestamps = True
        provider = self.state.transcription_provider
        self.state.set_source_language(self.source_lang_var.get())

        self.state.is_transcribing = True
        self.trans_progress.set(0)
        self.trans_pct_label.configure(text="0%")

        if provider == "local":
            model_size = self.state.whisper_model
            self.transcriber.model_size = model_size
            if self.transcriber.is_model_cached(model_size):
                self._start_local_transcription(selected_lang, use_word_timestamps)
            else:
                self._start_model_download(model_size, selected_lang, use_word_timestamps)
        else:
            self._is_downloading_model = False
            self._set_transcribe_action_mode("button")
            self.transcribe_btn.configure(state="disabled", text="Transcribing")
            self.trans_status.configure(text="Loading model...", text_color=COLORS["text_muted"])
            self._start_loading_animation(self.transcribe_btn, "Transcribing")

            # Cloud transcription — key is managed in Settings
            api_key = get_api_key(provider)

            if not api_key:
                self._on_transcription_error(f"No API key set for {provider}. Enter and apply your key first.")
                return

            def on_progress(p):
                self.after(0, lambda: self._update_trans_progress(p))

            def on_complete(results):
                self.after(0, lambda: self._on_transcription_done(results))

            def on_error(msg):
                self.after(0, lambda: self._on_transcription_error(msg))

            self.trans_status.configure(text="Extracting audio & uploading...", text_color=COLORS["text_muted"])
            self.cloud_transcriber.transcribe(
                self.state.video_path,
                provider=provider,
                api_key=api_key,
                language=selected_lang,
                word_timestamps=use_word_timestamps,
                on_progress=on_progress,
                on_complete=on_complete,
                on_error=on_error,
            )

    def _start_model_download(self, model_size, selected_lang, use_word_timestamps):
        self._is_downloading_model = True
        self.transcribe_btn.configure(state="disabled", text="Transcribe")
        self.trans_download_label.configure(text=f"Downloading Whisper {model_size} model...")
        self.trans_status.configure(text="Preparing model download...", text_color=COLORS["text_muted"])
        self._set_transcribe_action_mode("download")

        def on_progress(progress, downloaded_bytes, total_bytes):
            self.after(
                0,
                lambda: self._update_model_download_progress(
                    model_size,
                    progress,
                    downloaded_bytes,
                    total_bytes,
                ),
            )

        def on_complete(_model_path):
            self.after(0, lambda: self._start_local_transcription(selected_lang, use_word_timestamps))

        def on_error(msg):
            self.after(0, lambda: self._on_transcription_error(msg))

        self.transcriber.download_model(
            model_size=model_size,
            on_progress=on_progress,
            on_complete=on_complete,
            on_error=on_error,
        )

    def _start_local_transcription(self, selected_lang, use_word_timestamps):
        self._is_downloading_model = False
        self._set_transcribe_action_mode("button")
        self.transcribe_btn.configure(state="disabled", text="Transcribing")
        self.trans_progress.set(0)
        self.trans_pct_label.configure(text="0%")
        self.trans_status.configure(text="Loading model...", text_color=COLORS["text_muted"])
        self._start_loading_animation(self.transcribe_btn, "Transcribing")

        def on_progress(p):
            self.after(0, lambda: self._update_trans_progress(p))

        def on_complete(results):
            self.after(0, lambda: self._on_transcription_done(results))

        def on_error(msg):
            self.after(0, lambda: self._on_transcription_error(msg))

        self.transcriber.transcribe(
            self.state.video_path,
            language=selected_lang,
            word_timestamps=use_word_timestamps,
            on_progress=on_progress,
            on_complete=on_complete,
            on_error=on_error,
        )

    def _update_model_download_progress(self, model_size, progress, downloaded_bytes, total_bytes):
        pct = int(progress * 100)
        size_label = self._format_download_size(total_bytes)
        self.trans_download_label.configure(text=f"Downloading Whisper {model_size} model ({size_label})...")
        self.trans_progress.set(progress)
        self.trans_pct_label.configure(text=f"{pct}%")
        self.trans_status.configure(text=f"Downloading model... {pct}%", text_color=COLORS["text_muted"])

    @staticmethod
    def _format_download_size(total_bytes):
        if total_bytes <= 0:
            return "unknown size"
        size_mb = total_bytes / (1024 * 1024)
        if size_mb >= 100:
            return f"{round(size_mb):.0f} MB"
        if size_mb >= 10:
            return f"{size_mb:.1f} MB"
        return f"{size_mb:.2f} MB"

    def _set_transcribe_action_mode(self, mode):
        if mode == "download":
            self.transcribe_btn.grid_remove()
            self.trans_download_frame.grid(row=0, column=0, columnspan=3, sticky="ew")
            self.trans_download_label.grid()
            self.trans_download_progress_row.grid(row=1, column=0, sticky="ew")
            return

        self.transcribe_btn.grid(row=0, column=0, padx=(0, SPACING["md"]))
        self.trans_download_frame.grid(row=0, column=1, columnspan=2, sticky="ew")
        self.trans_download_label.grid_remove()
        self.trans_download_progress_row.grid(row=0, column=0, sticky="ew")

    def _update_trans_progress(self, p):
        self.trans_progress.set(p)
        pct = int(p * 100)
        self.trans_pct_label.configure(text=f"{pct}%")
        self.trans_status.configure(text=f"Transcribing... {pct}%")

    def _on_transcription_done(self, results):
        entries = []
        for r in results:
            original_text = (r.get("text") or "").strip()
            if not original_text and r.get("words"):
                original_text = " ".join((w.get("word") or "").strip() for w in r["words"]).strip()

            entry = SubtitleEntry(
                index=r["index"],
                start=r["start"],
                end=r["end"],
                original_text=original_text,
            )
            # Populate word entries if available (Feature 3)
            if "words" in r and r["words"]:
                entry.words = [
                    WordEntry(word=w["word"], start=w["start"], end=w["end"])
                    for w in r["words"]
                ]
            entries.append(entry)

        self.state.set_subtitles(entries)

        if not entries:
            self.trans_status.configure(text="No speech detected in this video.", text_color=COLORS["error"])
            self._finish_transcription_flow()
            return

        self.trans_status.configure(text=f"Done! {len(entries)} segments found.", text_color=COLORS["success"])

        # Smart translation default: Chinese source → English target, otherwise → Chinese
        source = self.source_lang_var.get()
        if source in ("Chinese", "Chinese (Simplified)", "Chinese (Traditional)"):
            self.lang_var.set("English")
        else:
            self.lang_var.set("Chinese (Simplified)")

        # Auto-switch primary font to SimSun if transcribed text is CJK and font is default Arial
        sample = " ".join(e.original_text for e in entries[:5])
        if self._text_contains_cjk(sample) and self.state.primary_style.font_family == "Arial":
            self.state.update_primary_style(font_family="SimSun")

        self._finish_transcription_flow()

    def _finish_transcription_flow(self):
        self.state.is_transcribing = False
        self._is_downloading_model = False
        self._stop_loading_animation()
        self._set_transcribe_action_mode("button")
        self.transcribe_btn.configure(state="normal", text="Transcribe")
        self.trans_progress.set(1.0)
        self.trans_pct_label.configure(text="100%")

    def _on_transcription_error(self, msg):
        self.state.is_transcribing = False
        self._is_downloading_model = False
        self._stop_loading_animation()
        self._set_transcribe_action_mode("button")
        self.transcribe_btn.configure(state="normal", text="Transcribe")
        if "SSL" in msg or "connection" in msg.lower():
            self.trans_status.configure(text=f"Connection Error: {msg[:60]}...", text_color=COLORS["error"])
        else:
            self.trans_status.configure(text=f"Error: {msg}", text_color=COLORS["error"])

    def _start_translation(self):
        if not self.state.subtitles:
            self.tl_status.configure(text="No subtitles to translate.", text_color=COLORS["error"])
            return
        if self.state.is_translating:
            return

        self.state.is_translating = True
        self.state.target_language = self.lang_var.get()
        self.translate_btn.configure(state="disabled", text="Translating")
        self.tl_progress.set(0)
        self.tl_pct_label.configure(text="0%")
        self.tl_download_label.configure(text="")
        self._translation_status_prefix = "Preparing translation..."
        self.tl_status.configure(text=self._translation_status_prefix, text_color=COLORS["text_muted"])
        self._is_downloading_translation_model = self.state.translation_provider == "local_nllb"
        if not self._is_downloading_translation_model:
            self._start_loading_animation(self.translate_btn, "Translating")

        from core.translator import Translator
        translator = Translator(
            provider=self.state.translation_provider,
            source_language=self.state.source_language,
        )

        def on_progress(p):
            self.after(0, lambda: self._update_tl_progress(p))

        def on_status(msg):
            self.after(0, lambda: self._update_translation_status(msg))

        def on_complete(translations):
            self.after(0, lambda: self._on_translation_done(translations))

        def on_error(msg):
            self.after(0, lambda: self._on_translation_error(msg))

        translator.translate(
            self.state.subtitles,
            self.state.target_language,
            on_progress=on_progress,
            on_complete=on_complete,
            on_error=on_error,
            on_status=on_status,
        )

    def _update_tl_progress(self, p):
        self.tl_progress.set(p)
        pct = int(p * 100)
        self.tl_pct_label.configure(text=f"{pct}%")
        self.tl_status.configure(text=f"{self._translation_status_prefix} {pct}%", text_color=COLORS["text_muted"])

    def _update_translation_status(self, msg):
        self._translation_status_prefix = msg
        if msg.startswith("Downloading local NLLB"):
            self.tl_download_label.configure(text=msg)
        else:
            self.tl_download_label.configure(text="")

        if msg.startswith("Translating batch") and self._is_downloading_translation_model:
            self._is_downloading_translation_model = False
            self._start_loading_animation(self.translate_btn, "Translating")

        self.tl_status.configure(text=msg, text_color=COLORS["text_muted"])

    def _on_translation_done(self, translations):
        for sub in self.state.subtitles:
            if sub.index in translations:
                sub.translated_text = translations[sub.index]
        self.state.sync_bilingual_with_translations()
        self.state.notify("subtitles")
        self.state.is_translating = False
        self._is_downloading_translation_model = False
        self._stop_loading_animation()
        self.translate_btn.configure(state="normal", text="Translate")
        self.tl_progress.set(1.0)
        self.tl_pct_label.configure(text="100%")
        self.tl_download_label.configure(text="")
        self.tl_status.configure(
            text=f"Done! {len(translations)} lines translated.",
            text_color=COLORS["success"],
        )

        # Auto-switch secondary font to SimSun if translated text is CJK and font is default Arial
        sample = " ".join(translations[k] for k in list(translations)[:5])
        if self._text_contains_cjk(sample) and self.state.secondary_style.font_family == "Arial":
            self.state.update_secondary_style(font_family="SimSun")

    def _on_translation_error(self, msg):
        self.state.is_translating = False
        self._is_downloading_translation_model = False
        self._stop_loading_animation()
        self.translate_btn.configure(state="normal", text="Translate")
        self.tl_download_label.configure(text="")
        self.tl_status.configure(text=f"Error: {msg}", text_color=COLORS["error"])

    @staticmethod
    def _text_contains_cjk(text: str) -> bool:
        return any(
            ("\u4e00" <= ch <= "\u9fff")
            or ("\u3400" <= ch <= "\u4dbf")
            or ("\u3040" <= ch <= "\u30ff")
            or ("\uac00" <= ch <= "\ud7af")
            for ch in text
        )

    def _start_loading_animation(self, btn, base_text):
        self._loading_dots = 0
        self._loading_btn = btn
        self._loading_base = base_text
        self._tick_loading()

    def _tick_loading(self):
        if not (
            (self.state.is_transcribing and not self._is_downloading_model)
            or (self.state.is_translating and not self._is_downloading_translation_model)
        ):
            return
        dots = "." * (self._loading_dots % 4)
        self._loading_btn.configure(text=f"{self._loading_base}{dots}")
        self._loading_dots += 1
        self._loading_after_id = self.after(400, self._tick_loading)

    def _stop_loading_animation(self):
        if self._loading_after_id is not None:
            try:
                self.after_cancel(self._loading_after_id)
            except Exception:
                pass
            self._loading_after_id = None

import customtkinter as ctk
from app.theme import COLORS, FONTS, SPACING, RADIUS, get_font_family
from core.config import get_api_key_storage_mode, is_secure_key_storage_available, load_config, save_config, set_api_key
from core.transcriber import AVAILABLE_MODELS


class SettingsPanel(ctk.CTkFrame):
    def __init__(self, parent, state, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.state = state
        self._secure_storage_available = is_secure_key_storage_available()
        self.grid_columnconfigure(0, weight=1)
        ff = get_font_family()

        ctk.CTkLabel(
            self, text="Settings",
            font=ctk.CTkFont(family=ff, size=FONTS["display"][1], weight="bold"),
            text_color=COLORS["text_heading"], anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=SPACING["lg"], pady=(SPACING["lg"], SPACING["md"]))

        card = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"], corner_radius=RADIUS["card"])
        card.grid(row=1, column=0, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["md"]))
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            card, text="Transcription",
            font=ctk.CTkFont(family=ff, size=FONTS["subheading"][1], weight="bold"),
            text_color=COLORS["text_heading"], anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=SPACING["lg"], pady=(SPACING["md"], SPACING["sm"]))

        self.transcription_note_label = ctk.CTkLabel(
            card,
            text="Base is the default local model for speed. Move up to a larger local model or use your own cloud API when you need better accuracy.",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            text_color=COLORS["text_muted"],
            anchor="w",
            justify="left",
            wraplength=760,
        )
        self.transcription_note_label.grid(row=1, column=0, columnspan=2, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["sm"]))
        card.bind(
            "<Configure>",
            lambda event, label=self.transcription_note_label: label.configure(wraplength=max(260, event.width - (SPACING["lg"] * 2))),
            add="+",
        )

        ctk.CTkLabel(
            card, text="Provider:",
            font=ctk.CTkFont(family=ff, size=FONTS["body"][1]),
            text_color=COLORS["text_secondary"],
        ).grid(row=2, column=0, padx=(SPACING["lg"], SPACING["md"]), pady=(0, SPACING["sm"]))

        self._provider_map = {"Local (Free)": "local", "Groq (Cloud)": "groq", "OpenAI (Cloud)": "openai"}
        self._provider_rev = {v: k for k, v in self._provider_map.items()}
        self.provider_var = ctk.StringVar(value=self._provider_rev.get(state.transcription_provider, "Local (Free)"))
        ctk.CTkSegmentedButton(
            card,
            values=list(self._provider_map.keys()),
            variable=self.provider_var,
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent_hover"],
            command=self._on_provider_change,
        ).grid(row=2, column=1, sticky="ew", padx=(0, SPACING["lg"]), pady=(0, SPACING["sm"]))

        self.model_row = ctk.CTkFrame(card, fg_color="transparent")
        self.model_row.grid(row=3, column=0, columnspan=2, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["sm"]))
        self.model_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self.model_row, text="Model:",
            font=ctk.CTkFont(family=ff, size=FONTS["body"][1]),
            text_color=COLORS["text_secondary"],
        ).grid(row=0, column=0, padx=(0, SPACING["md"]))

        self.model_var = ctk.StringVar(value=state.whisper_model)
        ctk.CTkSegmentedButton(
            self.model_row,
            values=AVAILABLE_MODELS,
            variable=self.model_var,
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent_hover"],
            command=lambda value: state.set_whisper_model(value),
        ).grid(row=0, column=1, sticky="ew")

        self.api_row = ctk.CTkFrame(card, fg_color="transparent")
        self.api_row.grid(row=4, column=0, columnspan=2, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["sm"]))
        self.api_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self.api_row, text="API Key:",
            font=ctk.CTkFont(family=ff, size=FONTS["body"][1]),
            text_color=COLORS["text_secondary"],
        ).grid(row=0, column=0, padx=(0, SPACING["md"]))

        self.api_entry = ctk.CTkEntry(
            self.api_row,
            font=ctk.CTkFont(family=ff, size=FONTS["body"][1]),
            fg_color=COLORS["entry_bg"], border_color=COLORS["entry_border"],
            show="*", height=32,
            placeholder_text="Paste your API key here…",
        )
        self.api_entry.grid(row=0, column=1, sticky="ew", padx=SPACING["xs"])

        self.apply_api_btn = ctk.CTkButton(
            self.api_row, text="Apply",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            fg_color=COLORS["button_secondary"], hover_color=COLORS["accent"],
            text_color=COLORS["text_primary"],
            height=32, width=64, cursor="hand2",
            command=self._apply_api_key,
        )
        self.apply_api_btn.grid(row=0, column=2, padx=(SPACING["xs"], 0))

        self.store_key_var = ctk.BooleanVar(value=False)
        self.store_key_check = ctk.CTkCheckBox(
            self.api_row,
            text="Store locally on this device",
            variable=self.store_key_var,
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            text_color=COLORS["text_secondary"],
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            checkmark_color=COLORS["button_text"],
        )
        self.store_key_check.grid(row=1, column=1, columnspan=2, sticky="w", padx=SPACING["xs"], pady=(SPACING["xs"], 0))

        self.api_status_label = ctk.CTkLabel(
            self.api_row,
            text="",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            text_color=COLORS["text_muted"],
            anchor="w",
            justify="left",
        )
        self.api_status_label.grid(row=2, column=1, columnspan=2, sticky="ew", padx=SPACING["xs"], pady=(SPACING["xs"], 0))

        self.cloud_help_label = ctk.CTkLabel(
            card,
            text="",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            text_color=COLORS["text_muted"],
            anchor="w",
            justify="left",
            wraplength=760,
        )
        self.cloud_help_label.grid(row=5, column=0, columnspan=2, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["md"]))
        card.bind(
            "<Configure>",
            lambda event, label=self.cloud_help_label: label.configure(wraplength=max(260, event.width - (SPACING["lg"] * 2))),
            add="+",
        )

        ctk.CTkLabel(
            card, text="Translation",
            font=ctk.CTkFont(family=ff, size=FONTS["subheading"][1], weight="bold"),
            text_color=COLORS["text_heading"], anchor="w",
        ).grid(row=6, column=0, columnspan=2, sticky="w", padx=SPACING["lg"], pady=(SPACING["md"], SPACING["sm"]))

        self.translation_note_label = ctk.CTkLabel(
            card,
            text="Local (Free) translation uses a cached NLLB model downloaded on first use. Cloud translation uses your own API key for Gemini, OpenAI, or Claude.",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            text_color=COLORS["text_muted"],
            anchor="w",
            justify="left",
            wraplength=760,
        )
        self.translation_note_label.grid(row=7, column=0, columnspan=2, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["sm"]))
        card.bind(
            "<Configure>",
            lambda event, label=self.translation_note_label: label.configure(wraplength=max(260, event.width - (SPACING["lg"] * 2))),
            add="+",
        )

        ctk.CTkLabel(
            card, text="Provider:",
            font=ctk.CTkFont(family=ff, size=FONTS["body"][1]),
            text_color=COLORS["text_secondary"],
        ).grid(row=8, column=0, padx=(SPACING["lg"], SPACING["md"]), pady=(0, SPACING["sm"]))

        self._translation_provider_map = {
            "Local (Free)": "local_nllb",
            "Gemini": "gemini",
            "OpenAI": "openai",
            "Claude": "claude",
        }
        self._translation_provider_rev = {v: k for k, v in self._translation_provider_map.items()}
        self.translation_provider_var = ctk.StringVar(
            value=self._translation_provider_rev.get(state.translation_provider, "Local (Free)")
        )
        ctk.CTkSegmentedButton(
            card,
            values=list(self._translation_provider_map.keys()),
            variable=self.translation_provider_var,
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent_hover"],
            command=self._on_translation_provider_change,
        ).grid(row=8, column=1, sticky="ew", padx=(0, SPACING["lg"]), pady=(0, SPACING["sm"]))

        self.translation_api_row = ctk.CTkFrame(card, fg_color="transparent")
        self.translation_api_row.grid(row=9, column=0, columnspan=2, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["sm"]))
        self.translation_api_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self.translation_api_row, text="API Key:",
            font=ctk.CTkFont(family=ff, size=FONTS["body"][1]),
            text_color=COLORS["text_secondary"],
        ).grid(row=0, column=0, padx=(0, SPACING["md"]))

        self.translation_api_entry = ctk.CTkEntry(
            self.translation_api_row,
            font=ctk.CTkFont(family=ff, size=FONTS["body"][1]),
            fg_color=COLORS["entry_bg"], border_color=COLORS["entry_border"],
            show="*", height=32,
            placeholder_text="Paste your translation API key here…",
        )
        self.translation_api_entry.grid(row=0, column=1, sticky="ew", padx=SPACING["xs"])

        self.translation_apply_api_btn = ctk.CTkButton(
            self.translation_api_row, text="Apply",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            fg_color=COLORS["button_secondary"], hover_color=COLORS["accent"],
            text_color=COLORS["text_primary"],
            height=32, width=64, cursor="hand2",
            command=self._apply_translation_api_key,
        )
        self.translation_apply_api_btn.grid(row=0, column=2, padx=(SPACING["xs"], 0))

        self.translation_store_key_var = ctk.BooleanVar(value=False)
        self.translation_store_key_check = ctk.CTkCheckBox(
            self.translation_api_row,
            text="Store locally on this device",
            variable=self.translation_store_key_var,
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            text_color=COLORS["text_secondary"],
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            checkmark_color=COLORS["button_text"],
        )
        self.translation_store_key_check.grid(row=1, column=1, columnspan=2, sticky="w", padx=SPACING["xs"], pady=(SPACING["xs"], 0))

        self.translation_api_status_label = ctk.CTkLabel(
            self.translation_api_row,
            text="",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            text_color=COLORS["text_muted"],
            anchor="w",
            justify="left",
        )
        self.translation_api_status_label.grid(row=2, column=1, columnspan=2, sticky="ew", padx=SPACING["xs"], pady=(SPACING["xs"], 0))

        self.translation_help_label = ctk.CTkLabel(
            card,
            text="",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            text_color=COLORS["text_muted"],
            anchor="w",
            justify="left",
            wraplength=760,
        )
        self.translation_help_label.grid(row=10, column=0, columnspan=2, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["md"]))
        card.bind(
            "<Configure>",
            lambda event, label=self.translation_help_label: label.configure(wraplength=max(260, event.width - (SPACING["lg"] * 2))),
            add="+",
        )

        self._refresh_api_row(state.transcription_provider)
        self._refresh_translation_api_row(state.translation_provider)

    def _on_provider_change(self, value):
        provider = self._provider_map.get(value, "local")
        self.state.set_transcription_provider(provider)
        config = load_config()
        config["transcription_provider"] = provider
        save_config(config)
        self._refresh_api_row(provider)

    def _on_translation_provider_change(self, value):
        provider = self._translation_provider_map.get(value, "local_nllb")
        self.state.set_translation_provider(provider)
        config = load_config()
        config["translation_provider"] = provider
        save_config(config)
        self._refresh_translation_api_row(provider)

    def _refresh_api_row(self, provider: str):
        if provider == "local":
            self.model_row.grid()
            self.api_row.grid_remove()
            self.cloud_help_label.grid_remove()
            return

        self.model_row.grid_remove()
        self.api_row.grid()
        self.cloud_help_label.grid()

        config = load_config()
        key_field = "groq_api_key" if provider == "groq" else "openai_api_key"
        saved_key = config.get(key_field, "")
        storage_mode = get_api_key_storage_mode(provider, config)

        self.api_entry.delete(0, "end")
        if saved_key:
            self.api_entry.insert(0, saved_key)

        self.store_key_var.set(storage_mode == "local")
        if self._secure_storage_available:
            self.store_key_check.configure(state="normal", text="Store locally on this device")
        else:
            self.store_key_check.configure(state="disabled", text="Store locally on this device (secure storage unavailable)")

        self.api_status_label.configure(text=self._storage_status_text(storage_mode), text_color=COLORS["text_muted"])
        self.cloud_help_label.configure(text=self._cloud_help_text(provider, storage_mode))

    def _apply_api_key(self):
        provider = self.state.transcription_provider
        key = self.api_entry.get().strip()
        if not key:
            self.api_status_label.configure(text="Enter an API key first.", text_color=COLORS["error"])
            return

        store_locally = bool(self.store_key_var.get() and self._secure_storage_available)
        set_api_key(provider, key, store_locally)

        storage_mode = "local" if store_locally else "session"
        status_text = "Applied. Key stored in your OS credential store." if store_locally else "Applied. Key will stay in memory for this session only."
        self.api_status_label.configure(text=status_text, text_color=COLORS["success"])
        self.cloud_help_label.configure(text=self._cloud_help_text(provider, storage_mode))

    def _refresh_translation_api_row(self, provider: str):
        if provider == "local_nllb":
            self.translation_api_row.grid_remove()
            self.translation_help_label.configure(
                text="Local translation downloads the NLLB model on first use and reuses it from the local cache after that."
            )
            return

        self.translation_api_row.grid()
        config = load_config()
        key_field = f"{provider}_api_key"
        saved_key = config.get(key_field, "")
        storage_mode = get_api_key_storage_mode(provider, config)

        self.translation_api_entry.delete(0, "end")
        if saved_key:
            self.translation_api_entry.insert(0, saved_key)

        self.translation_store_key_var.set(storage_mode == "local")
        if self._secure_storage_available:
            self.translation_store_key_check.configure(state="normal", text="Store locally on this device")
        else:
            self.translation_store_key_check.configure(state="disabled", text="Store locally on this device (secure storage unavailable)")

        self.translation_api_status_label.configure(
            text=self._storage_status_text(storage_mode),
            text_color=COLORS["text_muted"],
        )
        self.translation_help_label.configure(text=self._translation_help_text(provider, storage_mode))

    def _apply_translation_api_key(self):
        provider = self.state.translation_provider
        key = self.translation_api_entry.get().strip()
        if not key:
            self.translation_api_status_label.configure(text="Enter an API key first.", text_color=COLORS["error"])
            return

        store_locally = bool(self.translation_store_key_var.get() and self._secure_storage_available)
        set_api_key(provider, key, store_locally)

        storage_mode = "local" if store_locally else "session"
        status_text = "Applied. Key stored in your OS credential store." if store_locally else "Applied. Key will stay in memory for this session only."
        self.translation_api_status_label.configure(text=status_text, text_color=COLORS["success"])
        self.translation_help_label.configure(text=self._translation_help_text(provider, storage_mode))

    def _storage_status_text(self, storage_mode: str) -> str:
        if storage_mode == "local":
            return "A key is already stored securely on this device."
        if storage_mode == "session":
            return "A key is loaded for this app session only."
        if storage_mode == "environment":
            return "A key is available from your environment variables."
        if storage_mode == "legacy":
            return "A legacy plain-text key was found and will be migrated to secure storage when available."
        return ""

    def _cloud_help_text(self, provider: str, storage_mode: str) -> str:
        if storage_mode == "local":
            safety = "Safety: with local storage enabled, the key is saved in your OS credential store instead of plain text app files. It stays masked in the UI and is not written into subtitle exports, burned videos, or preset files."
        elif storage_mode == "session":
            safety = "Safety: with local storage off, the key stays only in app memory for this session. It stays masked in the UI and is only sent to the selected provider when a cloud transcription request starts."
        elif storage_mode == "environment":
            safety = "Safety: this key comes from your environment variables. The app does not rewrite it into subtitle exports, burned videos, or preset files."
        else:
            safety = "Safety: with local storage on, the app uses your OS credential store. With it off, the key is kept only for the current session. In both cases the key stays masked in the UI and is not written into subtitle outputs."

        if provider == "groq":
            setup = "Quick setup: 1. Create or log into Groq Console. 2. Generate an API key. 3. Paste it here. 4. Click Apply. This app uses Groq whisper-large-v3 for multilingual timestamps."
            pricing = "Pricing: Groq currently lists whisper-large-v3 at $0.111/hour and whisper-large-v3-turbo at $0.04/hour on its speech-to-text pricing page."
        else:
            setup = "Quick setup: 1. Create or log into OpenAI Platform. 2. Add billing and create an API key. 3. Paste it here. 4. Click Apply. This app uses whisper-1 because it supports word timestamps."
            pricing = "Pricing: OpenAI currently lists whisper-1 transcription at $0.006/minute, which is about $0.36/hour."

        return f"{safety}\n\n{setup}\n\n{pricing}"

    def _translation_help_text(self, provider: str, storage_mode: str) -> str:
        if storage_mode == "local":
            safety = "Safety: with local storage enabled, the key is saved in your OS credential store instead of plain text app files."
        elif storage_mode == "session":
            safety = "Safety: with local storage off, the key stays only in app memory for this session."
        elif storage_mode == "environment":
            safety = "Safety: this key comes from your environment variables."
        else:
            safety = "Safety: the key stays masked in the UI and is only used when cloud translation starts."

        setup = {
            "gemini": "Gemini uses a built-in default model tuned for fast subtitle translation.",
            "openai": "OpenAI uses a built-in default model tuned for fast subtitle translation.",
            "claude": "Claude uses a built-in default model tuned for fast subtitle translation.",
        }.get(provider, "")

        return f"{safety}\n\n{setup}".strip()


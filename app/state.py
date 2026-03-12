from dataclasses import dataclass, field
from typing import Callable
from core.subtitle_model import SubtitleAnimation, SubtitleEntry, SubtitleStyle


@dataclass
class AppState:
    # Video
    video_path: str = ""
    video_info: dict = field(default_factory=dict)

    # Subtitles
    subtitles: list[SubtitleEntry] = field(default_factory=list)
    selected_subtitle_index: int = -1

    # Styles
    primary_style: SubtitleStyle = field(default_factory=SubtitleStyle)
    secondary_style: SubtitleStyle = field(
        default_factory=lambda: SubtitleStyle(
            primary_color="#FFD700",
            position="bottom",
            position_y_percent=86,  # lower split when both lines share the 85% bottom baseline
            font_size=36,
        )
    )

    # Translation
    bilingual: bool = False
    target_language: str = "Japanese"
    source_language: str = "Auto Detect"
    translation_provider: str = "local_nllb"

    # Navigation
    current_step: int = 0  # 0-4 (4 = settings)

    # Processing flags
    is_transcribing: bool = False
    transcribe_progress: float = 0.0
    is_translating: bool = False
    translate_progress: float = 0.0
    is_burning: bool = False
    burn_progress: float = 0.0

    # Preview
    preview_time: float = 0.0

    # Feature 2: Cloud Transcription
    transcription_provider: str = "local"  # "local", "groq", "openai"
    whisper_model: str = "base"

    # Feature 3: Karaoke
    karaoke_mode: str = "off"  # "off", "sweep", "highlight", "bounce"
    animation_style: str = "none"  # "none", "fade", "pop", "slide_up", "typewriter"
    translation_animation_style: str = "none"  # "none", "fade", "pop", "slide_up"
    karaoke_highlight_color: str = "#FFFF00"
    transition_duration: float = 0.30      # fade/pop/slide in-duration seconds (0.05-1.0)
    highlight_dimmed_opacity: float = 0.5    # unspoken-word opacity in Highlight mode (0.1-0.9)
    bounce_trail_count: int = 3             # Bounce trailing words shown (0-5)
    bounce_min_chars: int = 3               # Min chars per bounce group; short words merged forward (0-8)
    sweep_entry_style: str = "instant"   # "instant", "fade", "pop"
    sweep_history_dim: float = 1.0       # history words opacity: 0=hidden, 1=full
    highlight_active_marker: str = "color"   # "color" | "box" | "color_box"
    highlight_history_on: bool = False        # mirror active marker for spoken words

    # Position swap: when True, primary uses top-anchor and secondary uses bottom-anchor
    position_swapped: bool = False

    # Observer
    _listeners: list[Callable] = field(default_factory=list, repr=False)

    def add_listener(self, callback: Callable):
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable):
        self._listeners = [l for l in self._listeners if l is not callback]

    def notify(self, field_name: str):
        for listener in self._listeners:
            try:
                listener(field_name)
            except Exception:
                pass

    def set_video(self, path: str, info: dict):
        self.video_path = path
        self.video_info = info
        self.subtitles = []
        self.selected_subtitle_index = -1
        self.preview_time = 0.0
        self.notify("video")

    def set_subtitles(self, subs: list[SubtitleEntry]):
        self.subtitles = subs
        self.selected_subtitle_index = 0 if subs else -1
        self.sync_bilingual_with_translations()
        self.notify("subtitles")

    def set_selected_subtitle(self, index: int):
        if 0 <= index < len(self.subtitles):
            self.selected_subtitle_index = index
            self.preview_time = self.subtitles[index].start
            self.notify("selected_subtitle")

    def set_step(self, step: int):
        self.current_step = step
        self.notify("step")

    def set_preview_time(self, t: float):
        self.preview_time = t
        self.notify("preview_time")

    def get_subtitle_at_time(self, t: float) -> SubtitleEntry | None:
        for sub in self.subtitles:
            if sub.start <= t <= sub.end:
                return sub
        return None

    def update_primary_style(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self.primary_style, k):
                setattr(self.primary_style, k, v)
        self.notify("style")

    def update_secondary_style(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self.secondary_style, k):
                setattr(self.secondary_style, k, v)
        self.notify("style")

    def set_bilingual(self, enabled: bool):
        self.bilingual = enabled
        self.notify("bilingual")

    def sync_bilingual_with_translations(self):
        has_translation = any((getattr(s, "translated_text", "") or "").strip() for s in self.subtitles)
        if self.bilingual != has_translation:
            self.bilingual = has_translation
            self.notify("bilingual")


    # Feature 2: Cloud Transcription
    def set_transcription_provider(self, provider: str):
        self.transcription_provider = provider
        self.notify("transcription_provider")

    def set_translation_provider(self, provider: str):
        self.translation_provider = provider
        self.notify("translation_provider")

    def set_source_language(self, language: str):
        self.source_language = language
        self.notify("source_language")

    # Feature 3: Karaoke
    def set_karaoke_mode(self, mode: str):
        self.karaoke_mode = mode
        self.notify("karaoke_mode")

    def set_animation_style(self, style: str):
        self.animation_style = style
        self.notify("animation_style")

    def set_translation_animation_style(self, style: str):
        self.translation_animation_style = style
        self.notify("translation_animation_style")

    def set_whisper_model(self, model: str):
        self.whisper_model = model
        self.notify("whisper_model")

    def set_karaoke_highlight_color(self, color: str):
        self.karaoke_highlight_color = color
        self.notify("karaoke_highlight_color")

    def set_transition_duration(self, v):
        self.transition_duration = max(0.05, min(1.0, float(v)))
        self.notify("transition_duration")

    def set_highlight_dimmed_opacity(self, v):
        self.highlight_dimmed_opacity = max(0.1, min(0.9, float(v)))
        self.notify("highlight_dimmed_opacity")

    def set_bounce_trail_count(self, v):
        self.bounce_trail_count = max(0, min(5, int(v)))
        self.notify("bounce_trail_count")

    def set_bounce_min_chars(self, v: int):
        self.bounce_min_chars = max(0, min(8, int(v)))
        self.notify("bounce_min_chars")

    def set_sweep_entry_style(self, v: str):
        if v in ("instant", "fade", "pop"):
            self.sweep_entry_style = v
            self.notify("sweep_entry_style")

    def set_sweep_history_dim(self, v: float):
        self.sweep_history_dim = max(0.0, min(1.0, float(v)))
        self.notify("sweep_history_dim")

    def set_highlight_active_marker(self, v: str):
        if v in ("color", "box", "color_box"):
            self.highlight_active_marker = v
            self.notify("highlight_active_marker")

    def set_highlight_history_on(self, v: bool):
        self.highlight_history_on = bool(v)
        self.notify("highlight_history_on")

    def apply_animation_preset(self, anim: "SubtitleAnimation"):
        """Bulk-apply all animation fields from a SubtitleAnimation, notifying once per field."""
        field_map = {
            "karaoke_mode": "set_karaoke_mode",
            "animation_style": "set_animation_style",
            "translation_animation_style": "set_translation_animation_style",
            "transition_duration": "set_transition_duration",
            "karaoke_highlight_color": "set_karaoke_highlight_color",
            "highlight_dimmed_opacity": "set_highlight_dimmed_opacity",
            "bounce_trail_count": "set_bounce_trail_count",
            "bounce_min_chars": "set_bounce_min_chars",
            "sweep_entry_style": "set_sweep_entry_style",
            "sweep_history_dim": "set_sweep_history_dim",
            "highlight_active_marker": "set_highlight_active_marker",
            "highlight_history_on": "set_highlight_history_on",
        }
        for field_name, setter_name in field_map.items():
            value = getattr(anim, field_name, None)
            if value is not None:
                getattr(self, setter_name)(value)

    def toggle_position_swap(self):
        """Swap primary/secondary position values (preset + Y%) and flip anchor logic."""
        pri_pct = self.primary_style.position_y_percent
        sec_pct = self.secondary_style.position_y_percent
        pri_pos = self.primary_style.position
        sec_pos = self.secondary_style.position
        self.primary_style.position_y_percent = sec_pct
        self.secondary_style.position_y_percent = pri_pct
        self.primary_style.position = sec_pos
        self.secondary_style.position = pri_pos
        self.position_swapped = not self.position_swapped
        self.notify("position_swap")

    def get_word_at_time(self, t: float):
        """Returns (SubtitleEntry, word_index) or (None, -1)."""
        sub = self.get_subtitle_at_time(t)
        if sub and sub.words:
            for i, w in enumerate(sub.words):
                if w.start <= t <= w.end:
                    return sub, i
            # If between words, find closest
            for i, w in enumerate(sub.words):
                if t < w.start:
                    return sub, max(0, i - 1)
            return sub, len(sub.words) - 1
        return None, -1

    def get_primary_style_for_subtitle(self, sub: SubtitleEntry | None) -> SubtitleStyle:
        if sub is None:
            return self.primary_style
        override = getattr(sub, 'primary_style_override', None)
        if override is not None:
            return override
        legacy_override = getattr(sub, 'style_override', None)
        if legacy_override is not None:
            return legacy_override
        return self.primary_style

    def get_secondary_style_for_subtitle(self, sub: SubtitleEntry | None) -> SubtitleStyle:
        if sub is None:
            return self.secondary_style
        override = getattr(sub, 'secondary_style_override', None)
        if override is not None:
            return override
        return self.secondary_style

    def subtitle_has_style_override(self, sub: SubtitleEntry | None) -> bool:
        if sub is None:
            return False
        return any(
            getattr(sub, attr, None) is not None
            for attr in ("style_override", "primary_style_override", "secondary_style_override")
        )

    def get_style_for_subtitle(self, sub: SubtitleEntry) -> SubtitleStyle:
        """Backward-compatible alias for primary subtitle style resolution."""
        return self.get_primary_style_for_subtitle(sub)

    def get_animation_settings_for_subtitle(self, sub: SubtitleEntry | None = None) -> SubtitleAnimation:
        settings = SubtitleAnimation(
            karaoke_mode=self.karaoke_mode,
            animation_style=self.animation_style,
            translation_animation_style=self.translation_animation_style,
            transition_duration=self.transition_duration,
            karaoke_highlight_color=self.karaoke_highlight_color,
            highlight_dimmed_opacity=self.highlight_dimmed_opacity,
            bounce_trail_count=self.bounce_trail_count,
            bounce_min_chars=self.bounce_min_chars,
            sweep_entry_style=self.sweep_entry_style,
            sweep_history_dim=self.sweep_history_dim,
            highlight_active_marker=self.highlight_active_marker,
            highlight_history_on=self.highlight_history_on,
        )
        override = getattr(sub, 'animation_override', None) if sub is not None else None
        if override is not None:
            for key, value in override.to_dict().items():
                setattr(settings, key, value)
        return settings

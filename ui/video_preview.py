import customtkinter as ctk
import tkinter as tk
import cv2
import time
import os
import re
import functools
import threading
import queue
from collections import OrderedDict
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageTk, ImageChops
from app.theme import COLORS, FONTS, SPACING, RADIUS, IconRenderer, get_font_family
from core.font_catalog import resolve_cached_font_variant, resolve_font_family_name
from core.subtitle_renderer import SubtitleOverlayRenderer, build_render_params
from core.subtitle_model import SubtitleStyle


# ---------------------------------------------------------------------------
# Font resolution — Windows registry + bold/italic variant lookup
# ---------------------------------------------------------------------------

_FONT_REGISTRY: dict | None = None  # lazy-loaded: {lowercase_display_name: abs_path}

# Map common localized/display aliases to canonical Windows family names.
_FONT_ALIAS_MAP = {
    "\u5b8b\u4f53": "SimSun",
    "\u65b0\u5b8b\u4f53": "NSimSun",
    "\u6977\u4f53": "KaiTi",
    "\u4eff\u5b8b": "FangSong",
    "\u9ed1\u4f53": "SimHei",
    "\u5fae\u8f6f\u96c5\u9ed1": "Microsoft YaHei",
    "\u5fae\u8f6f\u96c5\u9ed1 ui": "Microsoft YaHei UI",
    "\u5fae\u8f6f\u6b63\u9ed1\u4f53": "Microsoft JhengHei",
    "\u534e\u6587\u5b8b\u4f53": "STSong",
    "\u534e\u6587\u4eff\u5b8b": "STFangsong",
    "\u534e\u6587\u6977\u4f53": "STKaiti",
    "\u534e\u6587\u4e2d\u5b8b": "STZhongsong",
    "\u534e\u6587\u884c\u6977": "STXingkai",
}


def _normalize_family_name(family: str) -> str:
    name = (family or "").strip()
    if name.startswith("@"):
        name = name[1:]
    return re.sub(r"\s+", " ", name)


def _canonicalize_family_name(family: str) -> str:
    normalized = _normalize_family_name(family)
    if not normalized:
        return ""
    resolved = resolve_font_family_name(normalized)
    if resolved:
        return resolved
    return _FONT_ALIAS_MAP.get(normalized.casefold(), normalized)


def _contains_cjk(text: str) -> bool:
    if not text:
        return False
    return any(
        ("\u4e00" <= ch <= "\u9fff")
        or ("\u3400" <= ch <= "\u4dbf")
        or ("\u3040" <= ch <= "\u30ff")
        or ("\uac00" <= ch <= "\ud7af")
        for ch in text
    )


def _is_likely_cjk_family(family: str) -> bool:
    name = _canonicalize_family_name(family).lower()
    cjk_tokens = (
        "yahei", "simhei", "simsun", "nsimsun", "kaiti", "fangsong",
        "msyh", "jhenghei", "noto sans cjk", "noto sans sc", "noto serif sc",
        "source han", "gothic", "meiryo", "malgun", "pingfang", "heiti",
        "song", "kai",
    )
    return any(tok in name for tok in cjk_tokens)



def _font_family_candidates_for_text(preferred_family: str, text: str) -> list[str]:
    preferred_raw = _normalize_family_name(preferred_family) or "Arial"
    preferred = _canonicalize_family_name(preferred_raw) or preferred_raw
    preferred_variants = [preferred]
    if preferred_raw.casefold() != preferred.casefold():
        preferred_variants.append(preferred_raw)

    if _contains_cjk(text):
        cjk_families = [
            "SimSun",
            "Microsoft YaHei UI",
            "Microsoft YaHei",
            "SimHei",
            "Yu Gothic UI",
            "Meiryo UI",
        ]
        # If user explicitly picked a CJK font, try it first; otherwise CJK fallbacks first.
        if _is_likely_cjk_family(preferred):
            ordered = preferred_variants + cjk_families + ["Segoe UI", "Arial"]
        else:
            ordered = cjk_families + preferred_variants + ["Segoe UI", "Arial"]
    elif any(ord(ch) > 0x024F for ch in text or ""):
        ordered = [
            *preferred_variants,
            "Segoe UI",
            "Nirmala UI",
            "Leelawadee UI",
            "Arial Unicode MS",
            "Arial",
        ]
    else:
        ordered = preferred_variants + ["Segoe UI", "Arial", "Tahoma"]

    deduped = []
    seen = set()
    for name in ordered:
        key = name.casefold()
        if key not in seen:
            deduped.append(name)
            seen.add(key)
    return deduped


def _register_font_mapping(registry: dict, raw_name: str, path: str):
    clean = re.sub(r"\s*\(.*?\)\s*$", "", raw_name).strip()
    if not clean:
        return
    for part in clean.split("&"):
        name = _normalize_family_name(part)
        if not name:
            continue
        key = name.casefold()
        registry[key] = path
        canonical = _canonicalize_family_name(name)
        if canonical and canonical.casefold() != key:
            registry.setdefault(canonical.casefold(), path)


def _load_font_registry() -> dict:
    global _FONT_REGISTRY
    if _FONT_REGISTRY is not None:
        return _FONT_REGISTRY
    _FONT_REGISTRY = {}
    try:
        import winreg
        fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        key_specs = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Fonts"),
        ]

        for hive, key_path in key_specs:
            try:
                key = winreg.OpenKey(hive, key_path)
            except OSError:
                continue

            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                    i += 1
                    if not isinstance(value, str):
                        continue
                    path = value if os.path.isabs(value) else os.path.join(fonts_dir, value)
                    _register_font_mapping(_FONT_REGISTRY, name, path)
                except OSError:
                    break

            winreg.CloseKey(key)

        # Backfill aliases so localized names resolve when canonical family exists.
        for alias, canonical in _FONT_ALIAS_MAP.items():
            canonical_path = _FONT_REGISTRY.get(canonical.casefold())
            if canonical_path:
                _FONT_REGISTRY.setdefault(alias.casefold(), canonical_path)
    except Exception:
        pass
    return _FONT_REGISTRY




@functools.lru_cache(maxsize=128)
def _resolve_font_path(family: str, bold: bool, italic: bool) -> str | None:
    """Return an absolute font file path for the given family + style, or None."""
    registry = _load_font_registry()
    family_norm = _normalize_family_name(family)
    if not family_norm:
        return None
    family_canonical = _canonicalize_family_name(family_norm)

    style_parts = []
    if bold:
        style_parts.append("Bold")
    if italic:
        style_parts.append("Italic")
    style_suffix = " ".join(style_parts).casefold()

    family_bases = [family_canonical, family_norm]
    deduped_bases = []
    seen_bases = set()
    for base in family_bases:
        k = base.casefold()
        if base and k not in seen_bases:
            deduped_bases.append(base)
            seen_bases.add(k)

    # Try exact family, then progressively drop trailing words to handle
    # Tk variants like "Arial CE", "Bahnschrift Light Condensed", etc.
    for raw_base in deduped_bases:
        words = raw_base.split()
        for length in range(len(words), 0, -1):
            base = " ".join(words[:length]).casefold()
            # Try styled first (e.g. "arial bold"), then plain (e.g. "arial")
            if style_suffix:
                path = registry.get(base + " " + style_suffix)
                if path and os.path.exists(path):
                    return path
            path = registry.get(base)
            if path and os.path.exists(path):
                return path

    return None


# ---------------------------------------------------------------------------
# Deferred mpv / VLC detection — avoid heavy backend imports at module import
# ---------------------------------------------------------------------------

mpv = None
vlc = None
_HAS_MPV = None
_HAS_VLC = None
_VLC_ENV_READY = False
_BACKEND_IMPORT_LOCK = threading.Lock()


def _load_mpv_module() -> bool:
    global mpv, _HAS_MPV

    if _HAS_MPV is not None:
        return _HAS_MPV

    with _BACKEND_IMPORT_LOCK:
        if _HAS_MPV is not None:
            return _HAS_MPV
        try:
            import mpv as imported_mpv

            mpv = imported_mpv
            _HAS_MPV = True
        except Exception:
            mpv = None
            _HAS_MPV = False

    return _HAS_MPV


def _prepare_vlc_environment():
    global _VLC_ENV_READY

    if _VLC_ENV_READY or os.name != "nt":
        _VLC_ENV_READY = True
        return

    _vlc_base_candidates = [
        r"C:\Program Files\VideoLAN\VLC",
        r"C:\Program Files (x86)\VideoLAN\VLC",
    ]
    for _base in _vlc_base_candidates:
        if os.path.isdir(_base):
            try:
                os.add_dll_directory(_base)
            except Exception:
                pass
            plugins_dir = os.path.join(_base, "plugins")
            if os.path.isdir(plugins_dir):
                os.environ.setdefault("VLC_PLUGIN_PATH", plugins_dir)
            break
    _VLC_ENV_READY = True


def _load_vlc_module() -> bool:
    global vlc, _HAS_VLC

    if _HAS_VLC is not None:
        return _HAS_VLC

    with _BACKEND_IMPORT_LOCK:
        if _HAS_VLC is not None:
            return _HAS_VLC
        _prepare_vlc_environment()
        try:
            import vlc as imported_vlc

            vlc = imported_vlc
            _HAS_VLC = True
        except Exception:
            vlc = None
            _HAS_VLC = False

    return _HAS_VLC


class VideoPreview(ctk.CTkFrame):
    """
    Video preview widget.

    When python-mpv is available AND mpv can be initialised, uses mpv for
    hardware-accelerated playback.  The video is rendered directly into an
    embedded tk.Frame (via HWND on Windows) and a transparent subtitle
    canvas is layered on top.

    Falls back to the original OpenCV + PIL + VLC approach when mpv is
    unavailable or fails to initialise.
    """

    def __init__(self, parent, state, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_secondary"], corner_radius=0, **kwargs)
        self.state = state
        self._subtitle_renderer = SubtitleOverlayRenderer(video_info=self.state.video_info)

        # Common playback state
        self._is_playing = False
        self._suppress_scrub_callback = False
        self._is_muted = False
        self._volume = 80

        # Decide which backend to use
        self._use_mpv = _load_mpv_module()
        self._has_vlc = False
        self._mpv_player = None
        self._mpv_overlay = None

        # --------------- fallback (OpenCV/VLC) state ---------------
        self._photo = None            # prevent GC for fallback canvas
        self._capture = None
        self._capture_path = ""
        self._frame_cache = OrderedDict()
        self._scaled_frame_cache = OrderedDict()
        self._cache_limit = 160
        self._scaled_cache_limit = 120
        self._render_after_id = None
        self._play_after_id = None
        self._last_tick = 0.0
        self._canvas_image_id = None
        self._vlc_instance = None
        self._vlc_player = None
        self._audio_ready = False

        # Threaded rendering (fallback only) — started regardless so the
        # queue always exists; it will just idle if mpv is used.
        self._render_queue: queue.Queue = queue.Queue(maxsize=2)
        self._render_thread = threading.Thread(target=self._render_worker, daemon=True)
        self._render_thread.start()

        # --------------- mpv state ---------------
        self._mpv_scrubber_after_id = None
        self._mpv_subtitle_after_id = None
        self._subtitle_photo = None           # PhotoImage for overlay (prevent GC)
        self._subtitle_canvas_image_id = None
        self._prev_sub_index = -2             # sentinel for change detection
        self._prev_word_index = -2
        self._safe_area_visible_until = 0.0
        self._safe_area_hint_seconds = 1.0   # fade-out duration
        self._safe_area_hold_seconds = 0.6   # stay fully visible after last interaction
        self._safe_area_hide_after_id = None

        # --------------- layout ---------------
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Main video area container (row 0)
        self._video_container = ctk.CTkFrame(
            self, fg_color="#000000", corner_radius=0
        )
        self._video_container.grid(
            row=0, column=0, sticky="nsew",
            padx=SPACING["sm"], pady=(SPACING["sm"], 0)
        )
        self._video_container.grid_columnconfigure(0, weight=1)
        self._video_container.grid_rowconfigure(0, weight=1)

        if self._use_mpv:
            # mpv path: native tk.Frame as mpv rendering target + overlay canvas
            self._mpv_frame = tk.Frame(
                self._video_container, bg="#000000"
            )
            self._mpv_frame.grid(row=0, column=0, sticky="nsew")

            # Subtitle overlay canvas is a child of _mpv_frame (not _video_container)
            # so it is guaranteed to be pixel-identical in size to the mpv render
            # target. Background is a "magic" colorkey colour (#010101 ≈ black)
            # made transparent via WS_EX_LAYERED in _init_mpv, so the mpv video
            # shows through wherever there is no subtitle text.
            self.subtitle_canvas = tk.Canvas(
                self._mpv_frame,
                bg="#010101",
                highlightthickness=0,
            )
            self.subtitle_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)

            # Bind resize to _mpv_frame so subtitle dimensions stay in sync
            # with the actual mpv render area.
            self._mpv_frame.bind("<Configure>", self._on_resize)

        else:
            # Fallback path: single canvas for video + subtitle composite
            self.canvas = ctk.CTkCanvas(
                self._video_container,
                bg="#000000",
                highlightthickness=0,
                cursor="crosshair",
            )
            self.canvas.grid(row=0, column=0, sticky="nsew")
            self.canvas.bind("<Configure>", self._on_resize)

        # --------------- scrubber / controls (row 1) ---------------
        scrubber_frame = ctk.CTkFrame(
            self, fg_color=COLORS["bg_tertiary"], height=44,
            corner_radius=RADIUS["md"]
        )
        scrubber_frame.grid(
            row=1, column=0, sticky="ew",
            padx=SPACING["md"], pady=SPACING["sm"]
        )
        scrubber_frame.grid_columnconfigure(2, weight=1)

        self._play_icon = IconRenderer.get_colored("play", 16, "#FFFFFF")
        self._pause_icon = IconRenderer.get_colored("pause", 16, "#FFFFFF")

        self.play_btn = ctk.CTkButton(
            scrubber_frame,
            text="",
            image=self._play_icon,
            width=34, height=30,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["button_text"],
            corner_radius=RADIUS["pill"],
            command=self._toggle_playback,
            cursor="hand2",
        )
        self.play_btn.grid(row=0, column=0, padx=(SPACING["sm"], SPACING["sm"]))

        self.time_label = ctk.CTkLabel(
            scrubber_frame, text="00:00",
            font=ctk.CTkFont(family=FONTS["mono_small"][0], size=FONTS["mono_small"][1]),
            text_color=COLORS["text_secondary"], width=60,
        )
        self.time_label.grid(row=0, column=1, padx=(0, SPACING["sm"]))

        self.scrubber = ctk.CTkSlider(
            scrubber_frame,
            from_=0, to=1,
            number_of_steps=1000,
            progress_color=COLORS["accent"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            fg_color=COLORS["progress_bg"],
            command=self._on_scrub,
            height=14,
        )
        self.scrubber.grid(row=0, column=2, sticky="ew")
        self.scrubber.set(0)

        self.duration_label = ctk.CTkLabel(
            scrubber_frame, text="00:00",
            font=ctk.CTkFont(family=FONTS["mono_small"][0], size=FONTS["mono_small"][1]),
            text_color=COLORS["text_secondary"], width=60,
        )
        self.duration_label.grid(row=0, column=3, padx=(SPACING["sm"], 0))

        self._volume_icon = IconRenderer.get("volume", 16)
        self._mute_icon = IconRenderer.get("volume_mute", 16)

        self.mute_btn = ctk.CTkButton(
            scrubber_frame,
            text="",
            image=self._volume_icon,
            width=34, height=30,
            fg_color=COLORS["button_secondary"],
            hover_color=COLORS["button_secondary_hover"],
            corner_radius=RADIUS["md"],
            command=self._toggle_mute,
            cursor="hand2",
        )
        self.mute_btn.grid(row=0, column=4, padx=(SPACING["sm"], SPACING["sm"]))

        self.volume_slider = ctk.CTkSlider(
            scrubber_frame,
            from_=0, to=100,
            number_of_steps=20,
            progress_color=COLORS["accent"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            fg_color=COLORS["progress_bg"],
            command=self._on_volume_change,
            height=14,
            width=90,
        )
        self.volume_slider.grid(row=0, column=5, padx=(0, SPACING["sm"]))
        self.volume_slider.set(self._volume)

        # Volume controls disabled only when neither mpv nor VLC is present.
        if not self._use_mpv:
            self._has_vlc = _load_vlc_module()

        if not self._use_mpv and not self._has_vlc:
            self.mute_btn.configure(state="disabled")
            self.volume_slider.configure(state="disabled")

        # State listener
        self.state.add_listener(self._on_state_change)
        self.bind("<Destroy>", self._on_destroy)

        # Defer mpv initialisation until the window is actually mapped so
        # winfo_id() returns a valid HWND.
        if self._use_mpv:
            self.after(100, self._init_mpv)
        else:
            self._show_placeholder()

    # =========================================================================
    # mpv initialisation
    # =========================================================================

    def _init_mpv(self):
        """Called once after the widget is mapped; tries to create the mpv player."""
        try:
            hwnd = self._mpv_frame.winfo_id()
            player = mpv.MPV(
                wid=str(hwnd),
                vo="gpu",
                hwdec="auto",
                keep_open=True,
                pause=True,
                osc=False,
                input_default_bindings=False,
                input_vo_keyboard=False,
                sid=False,
            )
            player.volume = self._volume
            player.mute = self._is_muted
            self._mpv_player = player
            # Use mpv's native image overlay for subtitle rendering.
            # This gives true per-pixel alpha compositing on the GPU,
            # so effects like glow with soft edges render correctly
            # without the colorkey hack (which can't do semi-transparency).
            self._mpv_overlay = player.create_image_overlay()
            # Hide the tkinter canvas — mpv overlay replaces it.
            self.subtitle_canvas.place_forget()
            # Start the subtitle + scrubber update loops
            self._mpv_subtitle_tick()
            self._mpv_scrubber_tick()
        except Exception:
            # mpv init failed — fall back to OpenCV pipeline
            self._use_mpv = False
            self._mpv_player = None
            # Replace the mpv frame + overlay canvas with a plain canvas
            try:
                self._mpv_frame.destroy()
            except Exception:
                pass
            try:
                self.subtitle_canvas.destroy()
            except Exception:
                pass
            self.canvas = ctk.CTkCanvas(
                self._video_container,
                bg="#000000",
                highlightthickness=0,
                cursor="crosshair",
            )
            self.canvas.grid(row=0, column=0, sticky="nsew")
            self.canvas.bind("<Configure>", self._on_resize)
            self._show_placeholder()

    # =========================================================================
    # State listener
    # =========================================================================

    def _on_state_change(self, field):
        if field not in (
            "video", "preview_time", "subtitles", "selected_subtitle",
            "style", "bilingual", "karaoke_mode", "animation_style",
            "translation_animation_style",
            "karaoke_highlight_color", "transition_duration", "highlight_dimmed_opacity",
            "highlight_active_marker", "highlight_history_on", "bounce_trail_count", "bounce_min_chars",
            "sweep_entry_style", "sweep_history_dim", "subtitles_edited", "text_width_percent",
            "text_width_release", "position_swap",
        ):
            return

        if field == "text_width_percent":
            self._show_safe_area_hint()
        elif field == "text_width_release":
            self._begin_safe_area_fadeout()

        if field == "video":
            self._reset_video_session()
            if self._use_mpv:
                self._mpv_load_video(self.state.video_path)
            else:
                self._setup_audio_player(self.state.video_path)

        if field in ("style", "karaoke_mode", "animation_style", "translation_animation_style", "bilingual", "subtitles_edited", "position_swap"):
            if not self._use_mpv:
                self._scaled_frame_cache.clear()
            # Force subtitle overlay redraw on next tick
            self._prev_sub_index = -2
            self._prev_word_index = -2

        if self._use_mpv:
            if field in ("preview_time", "selected_subtitle") and not self._is_playing:
                # Sync mpv position for scrubber changes AND subtitle-list clicks.
                # set_selected_subtitle() sets preview_time silently (no "preview_time"
                # notification), so we must also handle "selected_subtitle" here.
                t = self.state.preview_time
                self._mpv_seek(t)
            self._mpv_force_subtitle_redraw()
        else:
            self._request_render()

    def _on_resize(self, event=None):
        if self._use_mpv:
            # Force a subtitle redraw at the new frame dimensions.
            self._prev_sub_index = -2
        else:
            self._request_render()

    # =========================================================================
    # Scrubber
    # =========================================================================

    def _on_scrub(self, value):
        if self._suppress_scrub_callback:
            return
        duration = self._get_duration()
        if duration > 0:
            t = value * duration
            if self._use_mpv:
                self._mpv_seek(t)
                self.state.set_preview_time(t)
            else:
                self.state.set_preview_time(t)
                self._seek_audio(t)

    # =========================================================================
    # mpv-specific helpers
    # =========================================================================

    def _mpv_load_video(self, path: str):
        """Load a new file into mpv."""
        if self._mpv_player is None or not path:
            return
        try:
            self._mpv_player.loadfile(path)
            # After file loads pause at start
            self.after(300, self._mpv_post_load)
        except Exception:
            pass

    def _mpv_post_load(self):
        """Called ~300 ms after loadfile to ensure we are paused at the beginning."""
        if self._mpv_player is None:
            return
        try:
            self._mpv_player.pause = True
            self._mpv_player.seek(0, reference="absolute", precision="exact")
        except Exception:
            pass
        self.state.set_preview_time(0)

    def _mpv_seek(self, seconds: float):
        """Seek mpv to an absolute position."""
        if self._mpv_player is None:
            return
        try:
            self._mpv_player.seek(seconds, reference="absolute", precision="exact")
        except Exception:
            pass

    def _mpv_scrubber_tick(self):
        """100 ms poll: update scrubber and time labels from mpv time_pos."""
        if not self._use_mpv or self._mpv_player is None:
            return
        try:
            t = self._mpv_player.time_pos
            d = self._mpv_player.duration
            if t is None:
                t = 0.0
            if d is None:
                d = self.state.video_info.get("duration", 0)

            # Sync state.preview_time while playing so subtitle list highlights correctly.
            # Write directly to avoid recursive notify loops.
            if self._is_playing and abs(t - self.state.preview_time) > 0.1:
                self.state.preview_time = t

            self.time_label.configure(text=self._fmt(t))
            self.duration_label.configure(text=self._fmt(d))
            if d and d > 0:
                self._suppress_scrub_callback = True
                try:
                    self.scrubber.set(t / d)
                finally:
                    self._suppress_scrub_callback = False

            # Detect natural end-of-file
            if self._is_playing and d and d > 0 and t >= d - 0.3:
                self._is_playing = False
                try:
                    self._mpv_player.pause = True
                except Exception:
                    pass
                self.play_btn.configure(image=self._play_icon)

        except Exception:
            pass

        self._mpv_scrubber_after_id = self.after(100, self._mpv_scrubber_tick)

    def _mpv_subtitle_tick(self):
        """50 ms poll: redraw subtitle overlay when subtitle/word changes or animation is active."""
        if not self._use_mpv:
            return
        try:
            if self._mpv_player is not None:
                t = self._mpv_player.time_pos
            else:
                t = None
            if t is None:
                t = self.state.preview_time

            sub = self.state.get_subtitle_at_time(t)
            sub_index = id(sub) if sub is not None else -1

            karaoke = self.state.karaoke_mode
            word_index = -1
            if sub is not None and karaoke != "off" and getattr(sub, "words", None):
                words = self._get_karaoke_words(sub)
                for i, w in enumerate(words):
                    if w["start"] <= t < w["end"]:
                        word_index = i
                        break

            # During animation, redraw every tick — animation state changes continuously.
            anim_settings = self.state.get_animation_settings_for_subtitle(sub)
            anim_needs_redraw = (
                self._is_playing
                and sub is not None
                and anim_settings.karaoke_mode == "off"
                and anim_settings.animation_style != "none"
            )
            safe_area_visible = time.time() <= self._safe_area_visible_until
            if (
                anim_needs_redraw
                or safe_area_visible
                or sub_index != self._prev_sub_index
                or word_index != self._prev_word_index
            ):
                self._prev_sub_index = sub_index
                self._prev_word_index = word_index
                self._mpv_render_subtitle_overlay(t, sub)
        except Exception as exc:
            import traceback
            traceback.print_exc()

        self._mpv_subtitle_after_id = self.after(50, self._mpv_subtitle_tick)

    def _mpv_force_subtitle_redraw(self):
        """Mark cached indices stale so the next subtitle tick re-renders."""
        self._prev_sub_index = -2
        self._prev_word_index = -2

    def _show_safe_area_hint(self):
        """Show the guide at full opacity. Cancel any pending fade-out —
        the fade is only scheduled by _begin_safe_area_fadeout (on mouse release)."""
        # Push visible_until far into the future so alpha stays at 1.0
        self._safe_area_visible_until = time.time() + 600

        if self._safe_area_hide_after_id is not None:
            try:
                self.after_cancel(self._safe_area_hide_after_id)
            except Exception:
                pass
            self._safe_area_hide_after_id = None

    def _begin_safe_area_fadeout(self):
        """Called on mouse release — start hold + fade timer."""
        total = self._safe_area_hold_seconds + self._safe_area_hint_seconds
        self._safe_area_visible_until = time.time() + total

        if self._safe_area_hide_after_id is not None:
            try:
                self.after_cancel(self._safe_area_hide_after_id)
            except Exception:
                pass
            self._safe_area_hide_after_id = None

        self._safe_area_hide_after_id = self.after(
            int(total * 1000),
            self._hide_safe_area_hint,
        )

    def _hide_safe_area_hint(self):
        self._safe_area_hide_after_id = None
        self._safe_area_visible_until = 0.0

        if self._use_mpv:
            try:
                current_t = self._mpv_player.time_pos if self._mpv_player is not None else None
            except Exception:
                current_t = None
            if current_t is None:
                current_t = self.state.preview_time
            sub = self.state.get_subtitle_at_time(current_t)
            self._mpv_force_subtitle_redraw()
            self._mpv_render_subtitle_overlay(current_t, sub)
        else:
            self._request_render()

    def _current_safe_area_alpha(self) -> float:
        remaining = self._safe_area_visible_until - time.time()
        if remaining <= 0:
            return 0.0
        # Hold at full opacity during the hold period, then fade out
        fade_dur = self._safe_area_hint_seconds
        if remaining > fade_dur:
            return 1.0  # still in the hold period
        return max(0.0, min(1.0, remaining / fade_dur))

    def _mpv_render_subtitle_overlay(self, current_time: float, sub):
        """Render a subtitle PIL image and push it to mpv's native overlay."""
        cw = self._mpv_frame.winfo_width()
        ch = self._mpv_frame.winfo_height()
        if cw < 10 or ch < 10:
            return

        params = self._snapshot_render_params_for_overlay(cw, ch, current_time, sub)

        # Render subtitle text onto a fully transparent RGBA image
        overlay = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        overlay = self._render_subtitle_onto_overlay(overlay, sub, params)

        if overlay is not None and hasattr(self, '_mpv_overlay') and self._mpv_overlay is not None:
            self._mpv_overlay.update(overlay)
        elif hasattr(self, '_mpv_overlay') and self._mpv_overlay is not None:
            # Clear: push a 1×1 transparent image
            self._mpv_overlay.update(Image.new("RGBA", (1, 1), (0, 0, 0, 0)))

    def _snapshot_render_params_for_overlay(self, cw: int, ch: int, current_time: float, sub) -> dict:
        """Build the params dict for subtitle rendering onto the transparent overlay."""
        return build_render_params(
            self.state,
            current_time,
            sub,
            cw,
            ch,
            is_playing=self._is_playing,
            safe_area_alpha=self._current_safe_area_alpha(),
        )

    def _render_subtitle_onto_overlay(self, overlay: Image.Image, sub, params: dict) -> Image.Image:
        """
        Dispatch to the correct karaoke/subtitle drawing method.
        The input overlay is an RGBA image; returns the modified overlay.
        """
        return self._subtitle_renderer.render_on_image(overlay, sub, params)

    # =========================================================================
    # Playback controls (unified interface)
    # =========================================================================

    def _toggle_playback(self):
        if not self.state.video_path:
            return
        if self._is_playing:
            self._pause_playback(update_button=True)
        else:
            self._start_playback()

    def _start_playback(self):
        duration = self._get_duration()
        if duration <= 0:
            return

        if self._use_mpv:
            if self._mpv_player is None:
                return
            try:
                t = self.state.preview_time
                if t >= duration:
                    t = 0.0
                    self.state.set_preview_time(0)
                self._mpv_seek(t)
                self._mpv_player.pause = False
                self._is_playing = True
                self.play_btn.configure(image=self._pause_icon)
            except Exception:
                pass
        else:
            if not self._audio_ready and self.state.video_path:
                self._setup_audio_player(self.state.video_path)

            if self.state.preview_time >= duration:
                self.state.set_preview_time(0)

            self._is_playing = True
            self.play_btn.configure(image=self._pause_icon)
            self._last_tick = time.perf_counter()
            self._play_audio(self.state.preview_time)
            self._tick_playback()

    def _pause_playback(self, update_button: bool):
        self._is_playing = False
        if self._use_mpv:
            if self._mpv_player is not None:
                try:
                    self._mpv_player.pause = True
                except Exception:
                    pass
        else:
            self._pause_audio()
            if self._play_after_id is not None:
                try:
                    self.after_cancel(self._play_after_id)
                except Exception:
                    pass
                self._play_after_id = None
        if update_button:
            self.play_btn.configure(image=self._play_icon)

    def _get_duration(self) -> float:
        """Return video duration in seconds from mpv (preferred) or state."""
        if self._use_mpv and self._mpv_player is not None:
            try:
                d = self._mpv_player.duration
                if d is not None and d > 0:
                    return d
            except Exception:
                pass
        return self.state.video_info.get("duration", 0)

    # =========================================================================
    # Volume / mute (unified)
    # =========================================================================

    def _toggle_mute(self):
        self._is_muted = not self._is_muted
        self.mute_btn.configure(image=self._mute_icon if self._is_muted else self._volume_icon)
        if self._use_mpv and self._mpv_player is not None:
            try:
                self._mpv_player.mute = self._is_muted
            except Exception:
                pass
        elif self._audio_ready and self._vlc_player is not None:
            try:
                self._vlc_player.audio_set_mute(self._is_muted)
            except Exception:
                self._audio_ready = False

    def _on_volume_change(self, value):
        self._volume = int(value)
        if self._volume == 0 and not self._is_muted:
            self._is_muted = True
            self.mute_btn.configure(image=self._mute_icon)
        elif self._volume > 0 and self._is_muted:
            self._is_muted = False
            self.mute_btn.configure(image=self._volume_icon)

        if self._use_mpv and self._mpv_player is not None:
            try:
                self._mpv_player.volume = self._volume
                self._mpv_player.mute = self._is_muted
            except Exception:
                pass
        elif self._audio_ready and self._vlc_player is not None:
            try:
                self._vlc_player.audio_set_volume(self._volume)
                self._vlc_player.audio_set_mute(self._is_muted)
            except Exception:
                self._audio_ready = False

    # =========================================================================
    # Destroy / session reset
    # =========================================================================

    def _on_destroy(self, event=None):
        if event is not None and event.widget is not self:
            return

        if self._safe_area_hide_after_id is not None:
            try:
                self.after_cancel(self._safe_area_hide_after_id)
            except Exception:
                pass
            self._safe_area_hide_after_id = None

        self._pause_playback(update_button=False)

        # Cancel all pending after() callbacks
        for attr in (
            "_render_after_id", "_mpv_scrubber_after_id",
            "_mpv_subtitle_after_id", "_play_after_id",
        ):
            after_id = getattr(self, attr, None)
            if after_id is not None:
                try:
                    self.after_cancel(after_id)
                except Exception:
                    pass
                setattr(self, attr, None)

        if self._use_mpv and self._mpv_player is not None:
            try:
                self._mpv_player.terminate()
            except Exception:
                pass
            self._mpv_player = None
        else:
            # Signal worker thread to stop
            try:
                self._render_queue.put_nowait(None)
            except Exception:
                pass
            self._release_capture()
            self._release_audio_player()

    def _reset_video_session(self):
        self._pause_playback(update_button=True)
        if not self._use_mpv:
            self._release_capture()
            self._frame_cache.clear()
            self._scaled_frame_cache.clear()
            self._release_audio_player()
        # Reset subtitle overlay change-detection cache
        self._prev_sub_index = -2
        self._prev_word_index = -2

    # =========================================================================
    # Fallback: OpenCV + PIL rendering pipeline
    # =========================================================================

    def _request_render(self):
        """Queue a render request; drop the oldest if full."""
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            return

        params = self._snapshot_render_params(cw, ch)
        # Non-blocking put: always keep the latest params
        try:
            self._render_queue.get_nowait()
        except queue.Empty:
            pass
        try:
            self._render_queue.put_nowait(params)
        except queue.Full:
            pass

    def _snapshot_render_params(self, cw: int, ch: int) -> dict:
        """Snapshot all state needed for rendering (called on main thread)."""
        sub = self.state.get_subtitle_at_time(self.state.preview_time)
        return build_render_params(
            self.state,
            self.state.preview_time,
            sub,
            cw,
            ch,
            is_playing=self._is_playing,
            safe_area_alpha=self._current_safe_area_alpha(),
        )

    def _render_worker(self):
        """Daemon thread: consume render params, produce PIL images."""
        while True:
            try:
                params = self._render_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if params is None:
                break

            try:
                img = self._render_frame(params)
                if img is not None:
                    self.after(0, lambda i=img: self._display_frame(i))
            except Exception:
                pass

    def _display_frame(self, img: Image.Image):
        """Main thread: display a rendered PIL image on the canvas."""
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            return
        self._photo = ImageTk.PhotoImage(img)
        if self._canvas_image_id is None:
            self._canvas_image_id = self.canvas.create_image(
                cw // 2, ch // 2, image=self._photo, anchor="center"
            )
        else:
            self.canvas.itemconfigure(self._canvas_image_id, image=self._photo)
            self.canvas.coords(self._canvas_image_id, cw // 2, ch // 2)
        self._update_time_labels()

    def _render_frame(self, params: dict) -> Image.Image | None:
        """Worker thread: full render pipeline (video frame + subtitle composite)."""
        if not params["video_path"]:
            return None

        img = self._get_scaled_frame(
            params["preview_time"], params["canvas_w"], params["canvas_h"],
            params["video_path"], params["video_info"]
        )
        if img is None:
            return None

        return self._subtitle_renderer.render_on_image(img, params["subtitle"], params)

    def _extract_frame(self, time_seconds: float, video_path: str, video_info: dict) -> Image.Image | None:
        if not self._ensure_capture(video_path):
            return None

        fps = video_info.get("fps", 0) or 0
        if fps <= 0:
            fps = 30.0

        frame_index = max(0, int(time_seconds * fps))
        cached = self._frame_cache.get(frame_index)
        if cached is not None:
            self._frame_cache.move_to_end(frame_index)
            return cached

        self._capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = self._capture.read()
        if not ok:
            return None

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(frame_rgb)
        self._frame_cache[frame_index] = image
        if len(self._frame_cache) > self._cache_limit:
            self._frame_cache.popitem(last=False)
        return image

    def _get_scaled_frame(self, time_seconds: float, canvas_w: int, canvas_h: int,
                          video_path: str, video_info: dict) -> Image.Image | None:
        fps = video_info.get("fps", 0) or 30.0
        frame_index = max(0, int(time_seconds * fps))
        key = (frame_index, canvas_w, canvas_h)

        cached = self._scaled_frame_cache.get(key)
        if cached is not None:
            self._scaled_frame_cache.move_to_end(key)
            return cached

        frame = self._extract_frame(time_seconds, video_path, video_info)
        if frame is None:
            return None

        scaled = self._fit_image(frame, canvas_w, canvas_h)
        self._scaled_frame_cache[key] = scaled
        if len(self._scaled_frame_cache) > self._scaled_cache_limit:
            self._scaled_frame_cache.popitem(last=False)
        return scaled

    def _ensure_capture(self, path: str) -> bool:
        if self._capture is not None and self._capture_path == path and self._capture.isOpened():
            return True
        self._release_capture()
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return False
        self._capture = cap
        self._capture_path = path
        self._frame_cache.clear()
        self._scaled_frame_cache.clear()
        return True

    def _release_capture(self):
        if self._capture is not None:
            try:
                self._capture.release()
            except Exception:
                pass
            self._capture = None
        self._capture_path = ""

    # -------------------------------------------------------------------------
    # Fallback playback tick
    # -------------------------------------------------------------------------

    def _tick_playback(self):
        if not self._is_playing:
            return

        duration = self.state.video_info.get("duration", 0)
        audio_time = self._get_audio_time() if self._audio_ready else None

        if audio_time is not None:
            next_time = audio_time
        else:
            now = time.perf_counter()
            elapsed = max(0.0, now - self._last_tick)
            self._last_tick = now
            next_time = self.state.preview_time + elapsed

        if next_time >= duration:
            self.state.set_preview_time(duration)
            self._pause_playback(update_button=True)
            return

        if abs(next_time - self.state.preview_time) > 0.001:
            self.state.set_preview_time(next_time)

        self._play_after_id = self.after(16, self._tick_playback)

    def _fit_image(self, img: Image.Image, max_w: int, max_h: int) -> Image.Image:
        ratio = min(max_w / img.width, max_h / img.height)
        new_w = int(img.width * ratio)
        new_h = int(img.height * ratio)
        result = Image.new("RGB", (max_w, max_h), (0, 0, 0))
        resized = img.resize((new_w, new_h), Image.BILINEAR)
        offset_x = (max_w - new_w) // 2
        offset_y = (max_h - new_h) // 2
        result.paste(resized, (offset_x, offset_y))
        return result

    # =========================================================================
    # Fallback VLC audio backend
    # =========================================================================

    def _setup_audio_player(self, path: str):
        if not self._has_vlc:
            self._has_vlc = _load_vlc_module()

        if not self._has_vlc or not path:
            self._audio_ready = False
            return
        try:
            self._release_audio_player()
            self._vlc_instance = vlc.Instance("--quiet")
            self._vlc_player = self._vlc_instance.media_player_new()

            media = None
            try:
                media = self._vlc_instance.media_new_path(path)
            except Exception:
                pass

            if media is None:
                try:
                    media = self._vlc_instance.media_new(path)
                except Exception:
                    pass

            if media is None:
                raise RuntimeError("Failed to create VLC media")

            media.add_option(":no-video")
            self._vlc_player.set_media(media)
            self._vlc_player.audio_set_volume(int(self._volume))
            self._vlc_player.audio_set_mute(self._is_muted)
            self._audio_ready = True
        except Exception:
            self._audio_ready = False
            self._vlc_instance = None
            self._vlc_player = None

    def _release_audio_player(self):
        if self._vlc_player is not None:
            try:
                self._vlc_player.stop()
            except Exception:
                pass
        self._vlc_player = None
        self._vlc_instance = None
        self._audio_ready = False

    def _play_audio(self, time_seconds: float):
        if not self._audio_ready or self._vlc_player is None:
            return
        try:
            self._vlc_player.play()
            self._vlc_player.audio_set_volume(int(self._volume))
            self._vlc_player.audio_set_mute(self._is_muted)
            self.after(80, lambda: self._seek_audio(time_seconds))
        except Exception:
            self._audio_ready = False

    def _pause_audio(self):
        if not self._audio_ready or self._vlc_player is None:
            return
        try:
            self._vlc_player.pause()
        except Exception:
            self._audio_ready = False

    def _seek_audio(self, time_seconds: float):
        if not self._audio_ready or self._vlc_player is None:
            return
        try:
            self._vlc_player.set_time(max(0, int(time_seconds * 1000)))
        except Exception:
            self._audio_ready = False

    def _get_audio_time(self) -> float | None:
        if not self._audio_ready or self._vlc_player is None:
            return None
        try:
            current_ms = self._vlc_player.get_time()
            if current_ms is None or current_ms < 0:
                return None
            return current_ms / 1000.0
        except Exception:
            self._audio_ready = False
            return None

    # =========================================================================
    # Subtitle font / text helpers (shared by both backends)
    # =========================================================================

    @staticmethod
    def _tag_font(font, want_bold: bool, want_italic: bool,
                  got_variant: str = "regular"):
        """Set _fake_bold / _fake_italic flags on a loaded PIL font."""
        got_bold = "bold" in got_variant
        got_italic = "italic" in got_variant
        font._fake_bold = want_bold and not got_bold
        font._fake_italic = want_italic and not got_italic
        return font

    def _get_font(self, style: SubtitleStyle, img_h: int, size_override: int = None,
                  scale: float = 1.0, sample_text: str = ""):
        base = size_override or max(12, int(style.font_size * img_h / 1080))
        font_size = max(4, int(base * scale))
        want_bold = style.bold
        want_italic = style.italic
        family_candidates = _font_family_candidates_for_text(style.font_family, sample_text)
        for family in family_candidates:
            cached_variant = resolve_cached_font_variant(family, want_bold, want_italic)
            if cached_variant:
                try:
                    font = ImageFont.truetype(
                        cached_variant["path"],
                        font_size,
                        index=int(cached_variant.get("index", 0)),
                    )
                    return self._tag_font(font, want_bold, want_italic,
                                          cached_variant.get("variant", "regular"))
                except OSError:
                    pass

            path = _resolve_font_path(family, want_bold, want_italic)
            if path:
                try:
                    font = ImageFont.truetype(path, font_size)
                    # _resolve_font_path tries styled first; if it returned a match
                    # for the styled request, assume the variant is correct.
                    return self._tag_font(font, want_bold, want_italic,
                                          ("bold_" if want_bold else "")
                                          + ("italic" if want_italic else "")
                                          or "regular")
                except OSError:
                    pass

            if want_bold or want_italic:
                cached_plain = resolve_cached_font_variant(family, False, False)
                if cached_plain:
                    try:
                        font = ImageFont.truetype(
                            cached_plain["path"],
                            font_size,
                            index=int(cached_plain.get("index", 0)),
                        )
                        return self._tag_font(font, want_bold, want_italic, "regular")
                    except OSError:
                        pass

                plain_path = _resolve_font_path(family, False, False)
                if plain_path:
                    try:
                        font = ImageFont.truetype(plain_path, font_size)
                        return self._tag_font(font, want_bold, want_italic, "regular")
                    except OSError:
                        pass

        fallbacks = ["msyh.ttc", "simhei.ttf", "arial.ttf", "msgothic.ttc"]
        for f_name in fallbacks:
            try:
                font = ImageFont.truetype(f_name, font_size)
                return self._tag_font(font, want_bold, want_italic, "regular")
            except OSError:
                continue

        font = ImageFont.load_default()
        font._fake_bold = False
        font._fake_italic = False
        return font

    def _compute_anim_effect(self, sub, params: dict, anim_style_override=None) -> dict:
        anim = anim_style_override or params["animation_style"]
        if anim == "none":
            return {}
        if not params["is_playing"]:
            stable = {
                "fade":       {"type": "fade",       "alpha": 1.0},
                "pop":        {"type": "pop",         "scale": 1.0},
                "slide_up":   {"type": "slide_up",    "y_offset": 0},
                "typewriter": {"type": "typewriter",  "char_frac": 1.0},
            }
            return stable.get(anim, {})
        t = params["preview_time"]
        dur = max(0.001, params["transition_duration"])
        t_in = t - sub.start
        t_out = sub.end - t
        if anim == "fade":
            return {"type": "fade", "alpha": min(min(1.0, t_in / dur), min(1.0, t_out / (dur * 0.67)))}
        elif anim == "pop":
            progress = min(1.0, t_in / dur) if t_in < dur else 1.0
            # Ease-out quad; start from 0.5x so text is always legible.
            ease = 1.0 - (1.0 - progress) ** 2
            return {"type": "pop", "scale": 0.5 + 0.5 * ease}
        elif anim == "slide_up":
            return {"type": "slide_up", "y_offset": int(60 * max(0.0, 1.0 - t_in / dur)) if t_in < dur else 0}
        elif anim == "typewriter":
            total = max(0.001, sub.end - sub.start)
            return {"type": "typewriter", "char_frac": min(1.0, t_in / (total * 0.85))}
        return {}

    # =========================================================================
    # Subtitle rendering — PIL drawing methods
    #
    # These methods accept either an RGB Image (fallback pipeline) or an RGBA
    # Image (mpv overlay pipeline) and preserve the input mode on output.
    # All RGBA compositing uses Image.alpha_composite so transparency from
    # the transparent overlay background is maintained correctly.
    # =========================================================================

    def _draw_bilingual_translation(self, img: Image.Image, sub, params: dict,
                                     primary_bottom_y: int | None = None) -> Image.Image:
        """Render ONLY the translated text (for karaoke modes) below the primary text.

        If primary_bottom_y is given the translation is placed at that Y coordinate
        (i.e. directly below the primary block).  Otherwise it falls back to the
        secondary style's own position — but that typically overlaps the primary, so
        callers should always supply primary_bottom_y when possible.
        """
        if not (params.get("bilingual") and getattr(sub, "translated_text", "")):
            return img
        style = params["secondary_style"]
        w, h = img.size
        trans_anim = params.get("translation_animation_style", "none")

        effect = {}
        if trans_anim != "none":
            effect = self._compute_anim_effect(sub, params, anim_style_override=trans_anim)

        scale = effect.get("scale", 1.0)
        anim_y_offset = effect.get("y_offset", 0)

        # Measure translation block height for absolute-Y placement
        gap = 10
        if primary_bottom_y is not None:
            abs_y = primary_bottom_y + gap + anim_y_offset
        else:
            abs_y = None

        def _render_translation(target: Image.Image) -> Image.Image:
            """Draw translation text onto *target* at the computed position."""
            if abs_y is not None:
                return self._draw_stacked_texts_at_y(
                    target, [(sub.translated_text, style)], w, h,
                    y_start=abs_y, scale=scale,
                )
            return self._draw_stacked_texts(
                target, [(sub.translated_text, style)], w, h,
                scale=scale, y_offset=anim_y_offset,
            )

        if effect.get("type") == "fade":
            alpha = effect.get("alpha", 1.0)
            trans_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
            trans_layer = _render_translation(trans_layer)
            r, g, b, a = trans_layer.split()
            a = a.point(lambda p: int(p * alpha))
            trans_layer = Image.merge("RGBA", (r, g, b, a))
            if img.mode == "RGBA":
                return Image.alpha_composite(img, trans_layer)
            return Image.alpha_composite(img.convert("RGBA"), trans_layer).convert(img.mode)

        return _render_translation(img)

    def _draw_subtitle(self, img: Image.Image, sub, params: dict, effect: dict = None) -> Image.Image:
        anim_type = (effect or {}).get("type", "none")

        if anim_type == "typewriter":
            from types import SimpleNamespace
            frac = effect.get("char_frac", 1.0)
            n = max(1, int(len(sub.original_text) * frac))
            sub = SimpleNamespace(
                original_text=sub.original_text[:n],
                translated_text=getattr(sub, "translated_text", ""),
                style_override=getattr(sub, "style_override", None),
            )
            effect = None

        scale = effect.get("scale", 1.0) if effect else 1.0
        y_offset = effect.get("y_offset", 0) if effect else 0

        if anim_type == "fade":
            alpha = effect.get("alpha", 1.0)
            orig_mode = img.mode
            rendered = self._draw_subtitle_content(img.copy(), sub, params, scale=scale, y_offset=y_offset)
            if orig_mode == "RGBA":
                # Transparent overlay (mpv): scale alpha-only so RGB stays at full
                # intensity — Image.blend would darken text via the near-black canvas bg.
                r, g, b, a = rendered.convert("RGBA").split()
                a = a.point(lambda p: int(p * alpha))
                return Image.merge("RGBA", (r, g, b, a))
            else:
                # Opaque video frame (fallback): blend frame with subtitle layer.
                base = img.copy()
                blended = Image.blend(base.convert("RGBA"), rendered.convert("RGBA"), alpha)
                return blended.convert(orig_mode)

        return self._draw_subtitle_content(img, sub, params, scale=scale, y_offset=y_offset)

    def _draw_subtitle_content(self, img: Image.Image, sub, params: dict,
                                scale: float = 1.0, y_offset: int = 0) -> Image.Image:
        img = img.copy()
        w, h = img.size

        primary_style = params["style"]

        texts = [(sub.original_text, primary_style)]
        if params["bilingual"] and getattr(sub, "translated_text", ""):
            texts.append((sub.translated_text, params["secondary_style"]))

        # When swapped, reverse rendering order so secondary becomes the anchor item (i=0).
        swapped = params.get("position_swapped", False)
        if swapped and len(texts) > 1:
            texts = [texts[1], texts[0]]

        # Render all items in one call (no position grouping) so that:
        # 1. Secondary is always i=1 with consistent top-anchor regardless of preset combo
        # 2. Overlap prevention always applies between primary and secondary
        img = self._draw_stacked_texts(img, texts, w, h, scale=scale, y_offset=y_offset)

        return img

    @staticmethod
    def _style_vertical_percent(style: SubtitleStyle) -> int:
        if hasattr(style, "position_y_percent"):
            try:
                return max(0, min(100, int(getattr(style, "position_y_percent"))))
            except Exception:
                pass
        base = {"top": 15, "center": 50, "bottom": 85}.get(getattr(style, "position", "bottom"), 85)
        legacy_offset = int(getattr(style, "position_offset", 0))
        return max(0, min(100, base + legacy_offset))

    def _video_content_rect(self, img_w: int, img_h: int) -> tuple[int, int, int, int]:
        """Return (x, y, w, h) of the actual video content area within the overlay/canvas.

        When the video aspect ratio differs from the canvas, mpv (and _fit_image)
        letterbox the video — this computes where the video actually sits so that
        subtitle positioning maps 0-100% to the video area, not the black bars.
        """
        vi = getattr(self, 'state', None) and getattr(self.state, 'video_info', None)
        vid_w = (vi or {}).get("width", 0)
        vid_h = (vi or {}).get("height", 0)
        if vid_w <= 0 or vid_h <= 0 or img_w <= 0 or img_h <= 0:
            return 0, 0, img_w, img_h
        ratio = min(img_w / vid_w, img_h / vid_h)
        content_w = int(vid_w * ratio)
        content_h = int(vid_h * ratio)
        offset_x = (img_w - content_w) // 2
        offset_y = (img_h - content_h) // 2
        return offset_x, offset_y, content_w, content_h

    def _compute_y_base(self, position: str, style: SubtitleStyle, total_stack_h: int,
                         img_h: int, y_offset: int = 0, img_w: int = 0,
                         anchor: str | None = None) -> int:
        """Compute y start using anchor-based positioning within the video content area.

        anchor = "bottom": slider % = bottom edge, text grows upward.
        anchor = "top":    slider % = top edge, text grows downward.
        Default is "bottom" — position name describes screen location, not anchor.
        """
        pos_pct = self._style_vertical_percent(style)
        _, vid_y, _, vid_h = self._video_content_rect(img_w or img_h, img_h)
        if vid_h <= 0:
            vid_y, vid_h = 0, img_h

        if anchor is None:
            anchor = "bottom"

        anchor_px = vid_y + int(vid_h * pos_pct / 100)

        if anchor == "top":
            y = anchor_px
        else:
            y = anchor_px - total_stack_h

        return y + y_offset

    def _draw_stacked_texts(self, img: Image.Image, items,
                            img_w: int, img_h: int, scale: float = 1.0, y_offset: int = 0) -> Image.Image:
        if not items:
            return img

        # Ensure RGBA so alpha_composite works; we convert back at the end.
        orig_mode = img.mode
        if orig_mode != "RGBA":
            img = img.convert("RGBA")

        draw = ImageDraw.Draw(img)
        gap = 10
        blocks = []
        total_stack_h = 0

        for text, style in items:
            font, lines, block_w, block_h = self._prepare_text_block(
                draw, text, style, img_w, img_h, scale=scale
            )
            blocks.append({"style": style, "font": font, "lines": lines, "w": block_w, "h": block_h})
            total_stack_h += block_h + gap
        total_stack_h -= gap

        # Each item uses its own style.position and position_y_percent.
        # i=0 always uses bottom-anchor (slider % = bottom edge, text grows up).
        # i>0 always uses top-anchor (slider % = top edge, text grows down).
        # Position name ("top"/"center"/"bottom") describes screen location, not anchor.
        # Swap is handled by reordering items in the caller.
        render_items = []
        prev_bottom_y = None
        for i, block in enumerate(blocks):
            item_anchor = "bottom" if i == 0 else "top"
            block_y = self._compute_y_base(
                block["style"].position, block["style"], block["h"], img_h, y_offset, img_w,
                anchor=item_anchor,
            )
            # Prevent overlap: push subsequent items below the previous block's bottom edge.
            if i > 0 and prev_bottom_y is not None:
                block_y = max(block_y, prev_bottom_y + 4)
            prev_bottom_y = block_y + block["h"]
            line_y = block_y
            for line_text, line_w, line_h in block["lines"]:
                x = (img_w - line_w) // 2
                render_items.append((block["style"], block["font"], line_text, x, line_y, line_w, line_h))
                line_y += line_h + 2

        # Batch backgrounds in one composite pass
        if any(item[0].background_enabled for item in render_items):
            overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            ov_draw = ImageDraw.Draw(overlay)
            pad = 6
            for style, _, _, x, y, w, h in render_items:
                if style.background_enabled:
                    bg = self._hex_to_rgb(style.background_color)
                    op = int(style.background_opacity * 255)
                    ov_draw.rounded_rectangle(
                        [x - pad, y - 2, x + w + pad, y + h + 2], radius=4, fill=(*bg, op)
                    )
            img = Image.alpha_composite(img, overlay)
            draw = ImageDraw.Draw(img)

        img = self._render_text_items(img, render_items)

        if orig_mode != "RGBA":
            img = img.convert(orig_mode)

        return img

    def _draw_stacked_texts_at_y(self, img: Image.Image, items, img_w: int, img_h: int,
                                  y_start: int, scale: float = 1.0) -> Image.Image:
        """Like _draw_stacked_texts but places the block at an absolute y_start."""
        if not items:
            return img
        orig_mode = img.mode
        if orig_mode != "RGBA":
            img = img.convert("RGBA")

        draw = ImageDraw.Draw(img)
        gap = 10
        blocks = []
        for text, style in items:
            font, lines, block_w, block_h = self._prepare_text_block(
                draw, text, style, img_w, img_h, scale=scale
            )
            blocks.append({"style": style, "font": font, "lines": lines, "w": block_w, "h": block_h})

        current_y = max(0, min(y_start, img_h - 10))

        render_items = []
        for block in blocks:
            line_y = current_y
            for line_text, line_w, line_h in block["lines"]:
                x = (img_w - line_w) // 2
                render_items.append((block["style"], block["font"], line_text, x, line_y, line_w, line_h))
                line_y += line_h + 2
            current_y += block["h"] + gap

        if any(item[0].background_enabled for item in render_items):
            overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            ov_draw = ImageDraw.Draw(overlay)
            pad = 6
            for style, _, _, x, y, w, h in render_items:
                if style.background_enabled:
                    bg = self._hex_to_rgb(style.background_color)
                    op = int(style.background_opacity * 255)
                    ov_draw.rounded_rectangle(
                        [x - pad, y - 2, x + w + pad, y + h + 2], radius=4, fill=(*bg, op)
                    )
            img = Image.alpha_composite(img, overlay)
            draw = ImageDraw.Draw(img)

        img = self._render_text_items(img, render_items)

        if orig_mode != "RGBA":
            img = img.convert(orig_mode)
        return img

    def _render_text_items(self, img, render_items):
        """Render glow/shadow/outline/text for a list of render_items with fake bold/italic."""
        _DIR8 = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
        for style, font, text, x, y, w, h in render_items:
            img = self._apply_glow(img, style, font, text, x, y)
            img = self._apply_shadow(img, style, font, text, x, y)
            if getattr(font, '_fake_italic', False):
                img = self._render_text_block_italic(img, style, font, text, x, y)
            else:
                draw = ImageDraw.Draw(img)
                t = style.outline_thickness
                if t > 0:
                    oc = self._hex_to_rgb(style.outline_color)
                    for dx, dy in _DIR8:
                        self._fb_text(draw, (x + dx * t, y + dy * t), text, font, oc)
                self._fb_text(draw, (x, y), text, font, self._hex_to_rgb(style.primary_color))
        return img

    # ------------------------------------------------------------------
    # Fake bold / italic helpers
    # ------------------------------------------------------------------

    _ITALIC_SHEAR = 0.20  # ~11.3°, matches libass ITALIC_SLANT

    @staticmethod
    def _fb_text(draw, xy, text, font, fill, **kw):
        """draw.text() with fake-bold support (draws twice at +1px offset)."""
        draw.text(xy, text, font=font, fill=fill, **kw)
        if getattr(font, '_fake_bold', False):
            draw.text((xy[0] + 1, xy[1]), text, font=font, fill=fill, **kw)

    def _shear_italic(self, layer: Image.Image, y_center: int) -> Image.Image:
        """Apply italic shear to an RGBA layer, centred vertically at y_center."""
        w, h = layer.size
        return layer.transform(
            (w, h), Image.AFFINE,
            (1, self._ITALIC_SHEAR, -self._ITALIC_SHEAR * y_center, 0, 1, 0),
            resample=Image.BILINEAR,
        )

    def _render_text_block_italic(self, img, style, font, text, x, y):
        """Render outline + fill text with fake italic onto img. Returns img."""
        bbox = font.getbbox(text)
        th = bbox[3] - bbox[1]
        y_center = y + th // 2
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        t = style.outline_thickness
        _DIR8 = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
        if t > 0:
            oc = self._hex_to_rgb(style.outline_color)
            for dx, dy in _DIR8:
                self._fb_text(ld, (x + dx * t, y + dy * t), text, font, oc)
        self._fb_text(ld, (x, y), text, font, self._hex_to_rgb(style.primary_color))
        layer = self._shear_italic(layer, y_center)
        return Image.alpha_composite(img.convert("RGBA"), layer)

    # ------------------------------------------------------------------
    # Glow and Shadow helpers
    # ------------------------------------------------------------------

    def _glow_shadow_y_center(self, font, text, y):
        """Compute vertical centre of text for italic shear."""
        bbox = font.getbbox(text)
        return y + (bbox[3] - bbox[1]) // 2

    def _apply_glow(self, img: Image.Image, style: SubtitleStyle,
                    font, text: str, x: int, y: int) -> Image.Image:
        if not getattr(style, "glow_enabled", False):
            return img
        radius = max(4, getattr(style, "glow_radius", 8))
        glow_color = self._hex_to_rgb(getattr(style, "glow_color", "#FFFFFF"))

        # Build a greyscale text mask, blur it, then subtract the *filled* shape.
        # Using a filled mask (small blur + threshold) closes letter counters
        # (inside of O, B, D, …) so glow only appears OUTSIDE the text boundary.
        text_mask = Image.new("L", img.size, 0)
        mask_draw = ImageDraw.Draw(text_mask)
        mask_draw.text((x, y), text, font=font, fill=255)
        if getattr(font, '_fake_bold', False):
            mask_draw.text((x + 1, y), text, font=font, fill=255)
        fill_blur = max(3, radius // 2)
        filled_mask = text_mask.filter(ImageFilter.GaussianBlur(fill_blur))
        filled_mask = filled_mask.point(lambda p: 255 if p > 20 else 0)

        blurred_a = text_mask.filter(ImageFilter.GaussianBlur(radius))
        outer_a = ImageChops.subtract(blurred_a, filled_mask)
        # Amplify glow intensity for visibility.
        outer_a = outer_a.point(lambda p: min(255, p * 2))

        glow_layer = Image.merge("RGBA", (
            Image.new("L", img.size, glow_color[0]),
            Image.new("L", img.size, glow_color[1]),
            Image.new("L", img.size, glow_color[2]),
            outer_a,
        ))
        if getattr(font, '_fake_italic', False):
            glow_layer = self._shear_italic(glow_layer, self._glow_shadow_y_center(font, text, y))

        orig_mode = img.mode
        base = img.convert("RGBA")
        result = Image.alpha_composite(base, glow_layer)
        return result if orig_mode == "RGBA" else result.convert(orig_mode)

    def _apply_shadow(self, img: Image.Image, style: SubtitleStyle,
                      font, text: str, x: int, y: int) -> Image.Image:
        if not getattr(style, "shadow_enabled", False):
            return img
        sx = getattr(style, "shadow_offset_x", 2)
        sy = getattr(style, "shadow_offset_y", 2)
        blur = getattr(style, "shadow_blur", 0)
        sc = self._hex_to_rgb(getattr(style, "shadow_color", "#000000"))

        shadow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow_layer)
        self._fb_text(sd, (x + sx, y + sy), text, font, (*sc, 220))
        if blur > 0:
            shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(blur))
        if getattr(font, '_fake_italic', False):
            shadow_layer = self._shear_italic(shadow_layer, self._glow_shadow_y_center(font, text, y))

        orig_mode = img.mode
        base = img.convert("RGBA")
        result = Image.alpha_composite(base, shadow_layer)
        return result if orig_mode == "RGBA" else result.convert(orig_mode)

    # ------------------------------------------------------------------
    # Karaoke modes
    # ------------------------------------------------------------------

    def _draw_karaoke_highlight(self, img: Image.Image, sub, params: dict) -> Image.Image:
        """Highlight karaoke: all words shown, spoken words highlighted."""
        orig_mode = img.mode
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        img = img.copy()
        draw = ImageDraw.Draw(img)
        w, h = img.size
        current_time = params["preview_time"]

        style = params["style"]
        font = self._get_font(style, h, sample_text=(sub.original_text or ""))

        words = self._get_karaoke_words(sub)
        if not words:
            result = self._draw_subtitle(img, sub, params)
            return result if orig_mode == "RGBA" else result.convert(orig_mode)

        word_metrics = []
        space_w = draw.textbbox((0, 0), " ", font=font)[2] - draw.textbbox((0, 0), " ", font=font)[0]

        for i, we in enumerate(words):
            text = we["word"].strip()
            if not text:
                continue
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            word_metrics.append({
                "text": text, "w": tw, "h": th,
                "start": we["start"], "end": we["end"], "index": i,
            })

        if not word_metrics:
            result = self._draw_subtitle(img, sub, params)
            return result if orig_mode == "RGBA" else result.convert(orig_mode)

        max_width = max(1, int(w * max(0, min(100, int(getattr(style, "text_width_percent", 90)))) / 100))
        line_gap = 4
        lines = []  # [(line_words, line_width, line_height)]
        cur_line = []
        cur_w = 0
        cur_h = 0
        for metric in word_metrics:
            add_w = metric["w"] if not cur_line else (space_w + metric["w"])
            if cur_line and (cur_w + add_w) > max_width:
                lines.append((cur_line, cur_w, cur_h))
                cur_line = [metric]
                cur_w = metric["w"]
                cur_h = metric["h"]
            else:
                cur_line.append(metric)
                cur_w += add_w
                cur_h = max(cur_h, metric["h"])
        if cur_line:
            lines.append((cur_line, cur_w, cur_h))

        total_stack_h = sum(line_h for _, _, line_h in lines) + (len(lines) - 1) * line_gap
        y_start = self._compute_y_base(style.position, style, total_stack_h, h, 0, w)

        highlight_color = self._hex_to_rgb(params["karaoke_highlight_color"])
        active_marker = params["highlight_active_marker"]   # "color" | "box" | "color_box"
        history_on    = params["highlight_history_on"]       # bool
        use_color = "color" in active_marker
        use_box   = "box"   in active_marker
        dimmed_a = int(params["highlight_dimmed_opacity"] * 255)
        pr, pg, pb = self._hex_to_rgb(style.primary_color)
        dimmed_color = (int(pr * dimmed_a / 255), int(pg * dimmed_a / 255), int(pb * dimmed_a / 255))
        outline_color = self._hex_to_rgb(style.outline_color)
        thickness = style.outline_thickness
        base_color = self._hex_to_rgb(style.primary_color)

        # ── per-word background box (style panel toggle, independent of marker) ──
        if style.background_enabled:
            overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            ov_draw = ImageDraw.Draw(overlay)
            pad = 4
            bg_color = self._hex_to_rgb(style.background_color)
            opacity = int(style.background_opacity * 255)
            y_line = y_start
            for line_words, line_w, line_h in lines:
                tmp_x = (w - line_w) // 2
                for m in line_words:
                    ov_draw.rounded_rectangle(
                        [tmp_x - pad, y_line - 2, tmp_x + m["w"] + pad, y_line + m["h"] + 2],
                        radius=4, fill=(*bg_color, opacity),
                    )
                    tmp_x += m["w"] + space_w
                y_line += line_h + line_gap
            img = Image.alpha_composite(img, overlay)
            draw = ImageDraw.Draw(img)

        # ── highlight box marker (active_marker controls shape; history mirrors it) ──
        if use_box:
            hl_overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            hl_draw = ImageDraw.Draw(hl_overlay)
            pad = 5
            y_line = y_start
            for line_words, line_w, line_h in lines:
                tmp_x = (w - line_w) // 2
                for m in line_words:
                    is_active = current_time >= m["start"] and current_time < m["end"]
                    is_spoken = current_time >= m["end"]
                    if is_active:
                        hl_draw.rounded_rectangle(
                            [tmp_x - pad, y_line - 3, tmp_x + m["w"] + pad, y_line + m["h"] + 3],
                            radius=5, fill=(*highlight_color, 180),
                        )
                    elif is_spoken and history_on:
                        hl_draw.rounded_rectangle(
                            [tmp_x - pad, y_line - 3, tmp_x + m["w"] + pad, y_line + m["h"] + 3],
                            radius=5, fill=(*highlight_color, 90),
                        )
                    tmp_x += m["w"] + space_w
                y_line += line_h + line_gap
            img = Image.alpha_composite(img, hl_overlay)
            draw = ImageDraw.Draw(img)

        _DIR8 = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
        fake_italic = getattr(font, '_fake_italic', False)
        if fake_italic:
            text_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(text_layer)

        y_line = y_start
        for line_words, line_w, line_h in lines:
            cur_x = (w - line_w) // 2
            for m in line_words:
                active = current_time >= m["start"] and current_time < m["end"]
                spoken = current_time >= m["end"]

                if active:
                    color = highlight_color if use_color else base_color
                elif spoken and history_on:
                    color = highlight_color if use_color else base_color
                elif spoken:
                    color = base_color
                else:
                    color = dimmed_color

                if thickness > 0:
                    if active:
                        t2 = thickness + 1
                        for dx, dy in _DIR8:
                            self._fb_text(draw, (cur_x + dx * t2, y_line + dy * t2), m["text"], font, outline_color)
                    else:
                        for dx, dy in _DIR8:
                            self._fb_text(draw, (cur_x + dx * thickness, y_line + dy * thickness), m["text"], font, outline_color)

                self._fb_text(draw, (cur_x, y_line), m["text"], font, color)
                cur_x += m["w"] + space_w
            y_line += line_h + line_gap

        if fake_italic:
            y_center = y_start + total_stack_h // 2
            text_layer = self._shear_italic(text_layer, y_center)
            img = Image.alpha_composite(img, text_layer)

        primary_bottom_y = y_start + total_stack_h
        img = self._draw_bilingual_translation(img, sub, params, primary_bottom_y=primary_bottom_y)
        return img if orig_mode == "RGBA" else img.convert(orig_mode)

    def _draw_karaoke_bounce(self, img: Image.Image, sub, params: dict) -> Image.Image:
        """Bounce mode: show only current word, large and centered."""
        orig_mode = img.mode
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        img = img.copy()
        draw = ImageDraw.Draw(img)
        w, h = img.size
        current_time = params["preview_time"]

        style = params["style"]
        words = self._get_karaoke_words(sub)
        if not words:
            result = self._draw_subtitle(img, sub, params)
            return result if orig_mode == "RGBA" else result.convert(orig_mode)

        # Merge short words forward so each display group has at least this many chars.
        _MIN_CHARS = params.get("bounce_min_chars", 3)
        merged: list[dict] = []
        i = 0
        while i < len(words):
            group = words[i]
            while len(group["word"].strip()) < _MIN_CHARS and i + 1 < len(words):
                i += 1
                group = {
                    "word": group["word"] + " " + words[i]["word"],
                    "start": group["start"],
                    "end": words[i]["end"],
                }
            merged.append(group)
            i += 1
        words = merged

        current_word = None
        current_idx = -1
        for i, we in enumerate(words):
            if we["start"] <= current_time <= we["end"]:
                current_word = we
                current_idx = i
                break

        if current_word is None:
            for i, we in enumerate(words):
                if current_time < we["start"]:
                    current_word = we
                    current_idx = i
                    break
            if current_word is None:
                # Past all word timestamps — hold the last word until subtitle ends.
                sub_end = float(getattr(sub, "end", 0.0))
                if words and current_time <= sub_end:
                    current_word = words[-1]
                    current_idx = len(words) - 1
                else:
                    return img if orig_mode == "RGBA" else img.convert(orig_mode)

        word_text = current_word["word"].strip()
        if not word_text:
            return img if orig_mode == "RGBA" else img.convert(orig_mode)

        large_size = int(style.font_size * h / 1080)
        large_font = self._get_font(style, h, size_override=large_size, sample_text=word_text)

        max_width = max(1, int(w * max(0, min(100, int(getattr(style, "text_width_percent", 90)))) / 100))
        popup_lines = []
        current_line = ""
        for token in word_text.split():
            test_line = token if not current_line else f"{current_line} {token}"
            bbox = draw.textbbox((0, 0), test_line, font=large_font)
            if (bbox[2] - bbox[0]) <= max_width or not current_line:
                current_line = test_line
            else:
                lb = draw.textbbox((0, 0), current_line, font=large_font)
                popup_lines.append((current_line, lb[2] - lb[0], lb[3] - lb[1]))
                current_line = token
        if current_line:
            lb = draw.textbbox((0, 0), current_line, font=large_font)
            popup_lines.append((current_line, lb[2] - lb[0], lb[3] - lb[1]))
        if not popup_lines:
            return img if orig_mode == "RGBA" else img.convert(orig_mode)

        block_h = sum(line_h for _, _, line_h in popup_lines) + (len(popup_lines) - 1) * 2
        y = self._compute_y_base(style.position, style, block_h, h, 0, w)

        _DIR8 = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
        outline_color = self._hex_to_rgb(style.outline_color)
        thickness = style.outline_thickness
        text_color = self._hex_to_rgb(style.primary_color)
        fake_italic = getattr(large_font, '_fake_italic', False)
        if fake_italic:
            popup_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
            popup_draw = ImageDraw.Draw(popup_layer)
        else:
            popup_draw = draw
        y_line = y
        for line_text, line_w, line_h in popup_lines:
            x = (w - line_w) // 2
            if thickness > 0:
                for dx, dy in _DIR8:
                    self._fb_text(popup_draw, (x + dx * thickness, y_line + dy * thickness),
                                  line_text, large_font, outline_color)
            self._fb_text(popup_draw, (x, y_line), line_text, large_font, text_color)
            y_line += line_h + 2
        if fake_italic:
            popup_layer = self._shear_italic(popup_layer, y + block_h // 2)
            img = Image.alpha_composite(img, popup_layer)
            draw = ImageDraw.Draw(img)

        small_size = max(12, int(style.font_size * h / 1080 * 0.7))
        small_font = self._get_font(style, h, size_override=small_size, sample_text=word_text)
        first_line_h = popup_lines[0][2]
        trail_y = y - int(first_line_h * 0.6)

        trail_count = params["bounce_trail_count"]
        for offset in range(1, min(trail_count + 1, current_idx + 1)):
            prev_idx = current_idx - offset
            if prev_idx < 0:
                break
            prev_word = words[prev_idx]["word"].strip()
            if not prev_word:
                continue

            alpha_val = max(80, 200 - offset * 60)
            dimmed = (alpha_val, alpha_val, alpha_val)

            pbbox = draw.textbbox((0, 0), prev_word, font=small_font)
            pw = pbbox[2] - pbbox[0]
            ph = pbbox[3] - pbbox[1]
            px = (w - pw) // 2
            trail_y -= ph + 4

            self._fb_text(draw, (px, trail_y), prev_word, small_font, dimmed)

        primary_bottom_y = y + block_h
        img = self._draw_bilingual_translation(img, sub, params, primary_bottom_y=primary_bottom_y)
        return img if orig_mode == "RGBA" else img.convert(orig_mode)

    def _draw_karaoke_sweep(self, img: Image.Image, sub, params: dict) -> Image.Image:
        """Sweep mode: words appear one at a time building the full sentence.

        History words render at history_dim opacity.  The newest word fades/pops
        in independently — no full-frame blending, so history stays sharp.
        """
        import math
        from types import SimpleNamespace

        words = self._get_karaoke_words(sub)
        if not words:
            return self._draw_subtitle(img, sub, params)

        current_time = params["preview_time"]
        visible = [w for w in words if w["start"] <= current_time]
        if not visible:
            return img

        entry_style = params["sweep_entry_style"]
        history_dim = params.get("sweep_history_dim", 1.0)
        orig_mode = img.mode

        newest = visible[-1]
        t_in = current_time - newest["start"]
        entry_dur = 0.15

        if entry_style == "fade":
            entry_alpha = min(1.0, t_in / entry_dur)
        elif entry_style == "pop":
            entry_alpha = min(1.0, math.sqrt(max(0.0, t_in / entry_dur)))
        else:
            entry_alpha = 1.0

        style = params["style"]
        base = img.convert("RGBA")
        canvas_w, canvas_h = base.size

        # history hidden: show only the newest word (use _draw_subtitle for glow/shadow)
        if history_dim <= 0.0:
            ns = SimpleNamespace(
                original_text=newest["word"],
                translated_text=getattr(sub, "translated_text", None),
                style_override=getattr(sub, "style_override", None),
            )
            rendered = self._draw_subtitle(base.copy(), ns, params).convert("RGBA")
            if entry_alpha >= 1.0:
                return rendered if orig_mode == "RGBA" else rendered.convert(orig_mode)
            result = Image.blend(base, rendered, entry_alpha)
            return result if orig_mode == "RGBA" else result.convert(orig_mode)

        full_text = " ".join(w["word"] for w in visible)

        # Compute layout from full text — this anchors the centring for ALL frames
        # so history words never shift position as new words are appended.
        meas_draw = ImageDraw.Draw(base)
        font, lines, _, block_h = self._prepare_text_block(
            meas_draw, full_text, style, canvas_w, canvas_h
        )
        y_start = self._compute_y_base(style.position, style, block_h, canvas_h, 0, canvas_w)

        new_word_str = newest["word"].strip()
        oc = self._hex_to_rgb(style.outline_color)
        fc = self._hex_to_rgb(style.primary_color)
        thickness = style.outline_thickness
        _DIR8 = [(-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1)]

        glow_enabled = getattr(style, "glow_enabled", False)
        glow_color = self._hex_to_rgb(getattr(style, "glow_color", "#FFFFFF"))
        glow_radius = max(8, getattr(style, "glow_radius", 8))
        shadow_enabled = getattr(style, "shadow_enabled", False)
        shadow_sc = self._hex_to_rgb(getattr(style, "shadow_color", "#000000"))
        shadow_sx = getattr(style, "shadow_offset_x", 2)
        shadow_sy = getattr(style, "shadow_offset_y", 2)
        shadow_blur = getattr(style, "shadow_blur", 0)

        # Draw a text segment (shadow + glow + outline + fill) onto text_layer at seg_alpha.
        fake_bold = getattr(font, '_fake_bold', False)

        def _fb_seg(d, xy, txt, fnt, clr):
            """draw.text with fake-bold for word-by-word segments."""
            d.text(xy, txt, font=fnt, fill=clr)
            if fake_bold:
                d.text((xy[0] + 1, xy[1]), txt, font=fnt, fill=clr)

        def draw_seg(text, x, y, seg_alpha):
            a = int(max(0, min(1.0, seg_alpha)) * 255)
            if a == 0:
                return

            # Shadow
            if shadow_enabled:
                sh_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
                sh_draw = ImageDraw.Draw(sh_layer)
                _fb_seg(sh_draw, (x + shadow_sx, y + shadow_sy), text, font,
                        (*shadow_sc, int(a * 220 / 255)))
                if shadow_blur > 0:
                    sh_layer = sh_layer.filter(ImageFilter.GaussianBlur(shadow_blur))
                text_layer.alpha_composite(sh_layer)

            # Glow — outer halo only, letter counters filled, alpha amplified
            if glow_enabled:
                tm = Image.new("L", base.size, 0)
                glow_draw = ImageDraw.Draw(tm)
                glow_draw.text((x, y), text, font=font, fill=255)
                if fake_bold:
                    glow_draw.text((x + 1, y), text, font=font, fill=255)
                fill_blur = max(3, glow_radius // 2)
                filled_tm = tm.filter(ImageFilter.GaussianBlur(fill_blur))
                filled_tm = filled_tm.point(lambda p: 255 if p > 20 else 0)
                outer_a = ImageChops.subtract(
                    tm.filter(ImageFilter.GaussianBlur(glow_radius)), filled_tm
                )
                outer_a = outer_a.point(lambda p: min(255, int(p * 2 * seg_alpha)))
                gl_layer = Image.merge("RGBA", (
                    Image.new("L", base.size, glow_color[0]),
                    Image.new("L", base.size, glow_color[1]),
                    Image.new("L", base.size, glow_color[2]),
                    outer_a,
                ))
                text_layer.alpha_composite(gl_layer)

            # Outline + fill
            td = ImageDraw.Draw(text_layer)
            if thickness > 0:
                for dx, dy in _DIR8:
                    _fb_seg(td, (x + dx * thickness, y + dy * thickness),
                            text, font, (*oc, a))
            _fb_seg(td, (x, y), text, font, (*fc, a))

        # Single RGBA layer for all text; history at history_dim, newest at entry_alpha.
        text_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))

        cur_y = y_start
        for line_idx, (line_text, line_w, line_h) in enumerate(lines):
            line_x = (canvas_w - line_w) // 2
            is_last = (line_idx == len(lines) - 1)

            if not is_last:
                draw_seg(line_text, line_x, cur_y, history_dim)
            else:
                if new_word_str and line_text.endswith(new_word_str):
                    pre = line_text[:len(line_text) - len(new_word_str)].rstrip()
                    if pre:
                        draw_seg(pre, line_x, cur_y, history_dim)
                        pre_adv = (
                            meas_draw.textbbox((0, 0), pre + " ", font=font)[2]
                            - meas_draw.textbbox((0, 0), pre + " ", font=font)[0]
                        )
                        new_x = line_x + pre_adv
                    else:
                        new_x = line_x
                    draw_seg(new_word_str, new_x, cur_y, entry_alpha)
                else:
                    draw_seg(line_text, line_x, cur_y, history_dim)

            cur_y += line_h + 2

        if getattr(font, '_fake_italic', False):
            text_layer = self._shear_italic(text_layer, y_start + block_h // 2)
        result = Image.alpha_composite(base, text_layer)
        primary_bottom_y = y_start + block_h
        result = self._draw_bilingual_translation(result, sub, params, primary_bottom_y=primary_bottom_y)
        return result if orig_mode == "RGBA" else result.convert(orig_mode)

    def _get_karaoke_words(self, sub) -> list[dict]:
        if getattr(sub, "words", None):
            return [
                {"word": w.word, "start": float(w.start), "end": float(w.end)}
                for w in sub.words
            ]

        text = (getattr(sub, "original_text", "") or "").strip()
        tokens = text.split()
        if not tokens:
            return []

        start = float(getattr(sub, "start", 0.0))
        end = float(getattr(sub, "end", start + 0.001))
        duration = max(0.001, end - start)
        step = duration / max(1, len(tokens))

        fallback = []
        for i, token in enumerate(tokens):
            w_start = start + i * step
            w_end = end if i == len(tokens) - 1 else min(end, w_start + step)
            fallback.append({"word": token, "start": w_start, "end": w_end})
        return fallback

    @staticmethod
    def _tokenize_for_wrap(text: str) -> list[str]:
        """Split text into wrap-friendly tokens.

        Splits text into tokens for width-based wrapping.  Each token is a
        (text, needs_space_before) tuple.

        - Latin/spaced words become one token each with space separators.
        - CJK characters become individual tokens with no separator, allowing
          line breaks at any character boundary.
        - Mixed text (e.g. "Hello 你好世界 test") handles both correctly.
        """
        import unicodedata

        def _is_cjk(ch: str) -> bool:
            return unicodedata.category(ch).startswith("Lo")

        tokens = []  # list of (text, needs_space_before)
        for i, word in enumerate(text.split()):
            space = i > 0  # space before this word group
            # Check if word contains any CJK
            if any(_is_cjk(ch) for ch in word):
                buf = ""
                for ch in word:
                    if _is_cjk(ch):
                        if buf:
                            tokens.append((buf, space))
                            space = False
                            buf = ""
                        tokens.append((ch, space))
                        space = False
                    else:
                        buf += ch
                if buf:
                    tokens.append((buf, space))
            else:
                tokens.append((word, space))
        return tokens

    def _prepare_text_block(self, draw: ImageDraw.Draw, text: str, style: SubtitleStyle,
                            img_w: int, img_h: int, scale: float = 1.0):
        font = self._get_font(style, img_h, scale=scale, sample_text=text)

        width_pct = max(0, min(100, int(getattr(style, "text_width_percent", 90))))
        max_width = max(1, int(img_w * width_pct / 100))
        lines = []
        tokens = self._tokenize_for_wrap(text)

        if not tokens:
            return font, [], 0, 0

        current_line = ""
        for token_text, needs_space in tokens:
            sep = " " if needs_space and current_line else ""
            test_line = current_line + sep + token_text
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if (bbox[2] - bbox[0]) <= max_width:
                current_line = test_line
            else:
                if current_line:
                    l_bbox = draw.textbbox((0, 0), current_line, font=font)
                    lines.append((current_line, l_bbox[2] - l_bbox[0], l_bbox[3] - l_bbox[1]))
                current_line = token_text

        if current_line:
            l_bbox = draw.textbbox((0, 0), current_line, font=font)
            lines.append((current_line, l_bbox[2] - l_bbox[0], l_bbox[3] - l_bbox[1]))

        block_h = sum(l[2] for l in lines) + (len(lines) - 1) * 2
        block_w = max(l[1] for l in lines) if lines else 0

        return font, lines, block_w, block_h

    def _draw_safe_width_guide(self, img: Image.Image, style: SubtitleStyle, alpha: float = 1.0) -> Image.Image:
        """Draw temporary shaded side regions indicating active subtitle width barrier."""
        width_pct = max(0, min(100, int(getattr(style, "text_width_percent", 90))))
        if width_pct >= 100:
            return img

        w, h = img.size
        safe_w = max(1, int(w * width_pct / 100))
        left = max(0, (w - safe_w) // 2)
        right = min(w, left + safe_w)

        orig_mode = img.mode
        alpha = max(0.0, min(1.0, float(alpha)))

        if orig_mode == "RGBA":
            # mpv overlay path — colorkey transparency is binary so we use a
            # stipple pattern to simulate semi-transparency.
            # ~67% of pixels are dark, giving roughly 60% visual opacity.
            import numpy as np
            arr = np.array(img)
            # Stipple pattern: ~60% of pixels are fully-opaque black dots,
            # the rest stay transparent.  After colorkey compositing the dots
            # survive (RGB 0,0,0 != colorkey 1,1,1) while gaps become the
            # colorkey colour and disappear, letting the video show through.
            yy, xx = np.ogrid[:h, :w]
            checker = ((xx + yy) % 3 != 0)  # ~67% of pixels

            # Apply density based on fade-in alpha (fewer dots when fading in)
            if alpha < 1.0:
                # Thin out the pattern during fade: use a sparser grid
                checker = checker & (((xx * 7 + yy * 13) % 100) < int(alpha * 100))

            # Shade regions — dots are fully opaque black (survives colorkey)
            if left > 0:
                mask = checker[:, :left]
                arr[:h, :left, 0] = np.where(mask, 0, arr[:h, :left, 0])
                arr[:h, :left, 1] = np.where(mask, 0, arr[:h, :left, 1])
                arr[:h, :left, 2] = np.where(mask, 0, arr[:h, :left, 2])
                arr[:h, :left, 3] = np.where(mask, 255, arr[:h, :left, 3])
            if right < w:
                mask = checker[:, :w - right]
                arr[:h, right:, 0] = np.where(mask, 0, arr[:h, right:, 0])
                arr[:h, right:, 1] = np.where(mask, 0, arr[:h, right:, 1])
                arr[:h, right:, 2] = np.where(mask, 0, arr[:h, right:, 2])
                arr[:h, right:, 3] = np.where(mask, 255, arr[:h, right:, 3])

            # Border lines (solid, fully opaque white, 2px wide)
            if left > 0:
                x0, x1 = max(0, left - 1), min(w, left + 1)
                arr[:, x0:x1, 0] = 255
                arr[:, x0:x1, 1] = 255
                arr[:, x0:x1, 2] = 255
                arr[:, x0:x1, 3] = 255
            if right < w:
                x0, x1 = max(0, right - 1), min(w, right + 1)
                arr[:, x0:x1, 0] = 255
                arr[:, x0:x1, 1] = 255
                arr[:, x0:x1, 2] = 255
                arr[:, x0:x1, 3] = 255

            return Image.fromarray(arr, "RGBA")

        # Fallback (RGB) path — normal alpha compositing works fine
        base = img.convert("RGBA")
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        shadow_alpha = int(35 * alpha)
        line_alpha = int(95 * alpha)

        if left > 0:
            draw.rectangle([0, 0, left, h], fill=(0, 0, 0, shadow_alpha))
            draw.line([(left, 0), (left, h)], fill=(255, 255, 255, line_alpha), width=2)
        if right < w:
            draw.rectangle([right, 0, w, h], fill=(0, 0, 0, shadow_alpha))
            draw.line([(right, 0), (right, h)], fill=(255, 255, 255, line_alpha), width=2)

        result = Image.alpha_composite(base, overlay)
        return result.convert(orig_mode)

    def _hex_to_rgb(self, hex_color: str) -> tuple:
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

    # =========================================================================
    # Placeholder (fallback mode only)
    # =========================================================================

    def _show_placeholder(self):
        if self._use_mpv:
            return  # mpv renders its own black frame; no placeholder needed
        self.canvas.delete("all")
        self._canvas_image_id = None
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw > 10 and ch > 10:
            ff = get_font_family()
            self.canvas.create_text(
                cw // 2, ch // 2 - 10,
                text="\u25B6",
                fill="#4B5563",
                font=(ff, 28),
            )
            self.canvas.create_text(
                cw // 2, ch // 2 + 24,
                text="No video loaded",
                fill="#6B7280",
                font=(ff, 13),
            )

    # =========================================================================
    # Time label helpers (fallback pipeline — mpv uses _mpv_scrubber_tick)
    # =========================================================================

    def _update_time_labels(self):
        t = self.state.preview_time
        d = self.state.video_info.get("duration", 0)
        self.time_label.configure(text=self._fmt(t))
        self.duration_label.configure(text=self._fmt(d))
        if d > 0:
            self._suppress_scrub_callback = True
            try:
                self.scrubber.set(t / d)
            finally:
                self._suppress_scrub_callback = False

    @staticmethod
    def _fmt(seconds: float) -> str:
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m:02d}:{s:02d}"

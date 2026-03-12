import customtkinter as ctk
import tkinter as tk
from app.theme import COLORS, SPACING, RADIUS, SIDEBAR
from app.state import AppState
from core.config import load_config
from core.paths import get_asset_path
from ui.sidebar import Sidebar


class SubtitleGeneratorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window setup
        self.title("SubVela")
        self.geometry("1280x800")
        self.minsize(960, 600)
        self._set_window_icon()
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        # App state
        self.app_state = AppState()
        config = load_config()
        self.app_state.transcription_provider = config.get("transcription_provider", self.app_state.transcription_provider)
        self.app_state.translation_provider = config.get("translation_provider", self.app_state.translation_provider)
        self.app_state.whisper_model = config.get("whisper_model", self.app_state.whisper_model)
        self.app_state.add_listener(self._on_state_change)

        # Root grid: sidebar | main content
        self.grid_columnconfigure(0, weight=0)  # sidebar
        self.grid_columnconfigure(1, weight=1)  # main
        self.grid_rowconfigure(0, weight=1)

        self.configure(fg_color=COLORS["bg_primary"])

        # Sidebar
        self.sidebar = Sidebar(self, self.app_state)
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.configure(width=SIDEBAR["expanded_width"])
        self.sidebar.grid_propagate(False)

        # Main content area
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=SPACING["sm"], pady=SPACING["sm"])
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)

        # Draggable split panes
        pane_bg = self._resolve_pane_color()
        self.vertical_pane = tk.PanedWindow(
            self.main_frame,
            orient=tk.VERTICAL,
            sashwidth=4,
            bd=0,
            bg=pane_bg,
            relief=tk.FLAT,
        )
        self.vertical_pane.grid(row=0, column=0, sticky="nsew")

        self.top_pane = tk.PanedWindow(
            self.vertical_pane,
            orient=tk.HORIZONTAL,
            sashwidth=4,
            bd=0,
            bg=pane_bg,
            relief=tk.FLAT,
        )

        self.video_preview = None
        self.subtitle_list = None

        self.video_preview_host = ctk.CTkFrame(self.top_pane, fg_color=COLORS["bg_secondary"], corner_radius=0)
        self.video_preview_host.grid_columnconfigure(0, weight=1)
        self.video_preview_host.grid_rowconfigure(0, weight=1)
        self._preview_loading_label = ctk.CTkLabel(
            self.video_preview_host,
            text="Loading preview...",
            text_color=COLORS["text_muted"],
        )
        self._preview_loading_label.grid(row=0, column=0)

        self.subtitle_list_host = ctk.CTkFrame(self.top_pane, fg_color=COLORS["bg_secondary"], corner_radius=0)
        self.subtitle_list_host.grid_columnconfigure(0, weight=1)
        self.subtitle_list_host.grid_rowconfigure(0, weight=1)

        self.top_pane.add(self.video_preview_host, minsize=500, stretch="always")
        self.top_pane.add(self.subtitle_list_host, minsize=260)

        # Control panel container
        self.control_container = ctk.CTkFrame(
            self.vertical_pane,
            fg_color=COLORS["bg_secondary"],
            corner_radius=0,
        )
        self.control_container.grid_columnconfigure(0, weight=1)
        self.control_container.grid_rowconfigure(0, weight=1)

        self.control_scroll = ctk.CTkScrollableFrame(
            self.control_container,
            fg_color="transparent",
            corner_radius=0,
        )
        self.control_scroll.grid(row=0, column=0, sticky="nsew")
        self.control_scroll.grid_columnconfigure(0, weight=1)

        self.vertical_pane.add(self.top_pane, minsize=260, stretch="always")
        self.vertical_pane.add(self.control_container, minsize=220)

        self._panel_factories = [
            self._create_video_panel,
            self._create_transcribe_panel,
            self._create_style_panel,
            self._create_export_panel,
            self._create_settings_panel,
        ]
        self.panels = [None] * len(self._panel_factories)
        self._active_panel_index = None

        # Show initial panel
        self._show_panel(0)
        self.after(120, self._set_initial_sashes)
        self.after(0, self._finish_startup)

    def _finish_startup(self):
        self.after(40, self._ensure_preview_widgets)
        self.after(120, self._start_background_warmup)

    def _set_window_icon(self):
        try:
            self.iconbitmap(get_asset_path("favicon.ico"))
        except Exception:
            pass

    def _ensure_preview_widgets(self):
        if self.video_preview is None:
            from ui.video_preview import VideoPreview

            self.video_preview = VideoPreview(self.video_preview_host, self.app_state)
            self.video_preview.grid(row=0, column=0, sticky="nsew")
            try:
                self._preview_loading_label.destroy()
            except Exception:
                pass

        if self.subtitle_list is None:
            from ui.subtitle_list import SubtitleList

            self.subtitle_list = SubtitleList(self.subtitle_list_host, self.app_state)
            self.subtitle_list.grid(row=0, column=0, sticky="nsew")

        for widget in (self.video_preview, self.subtitle_list, self.control_container):
            try:
                widget._canvas.configure(highlightthickness=0, bd=0)
            except Exception:
                pass

    def _start_background_warmup(self):
        try:
            from core.transcriber import warmup_transcriber_runtime_async

            warmup_transcriber_runtime_async()
        except Exception:
            pass

    def _on_state_change(self, field):
        if field == "step":
            self._show_panel(self.app_state.current_step)
        elif field == "theme":
            self._update_pane_colors()

    def _show_panel(self, index):
        if not (0 <= index < len(self.panels)):
            return

        if self._active_panel_index == index:
            return

        if self._active_panel_index is not None and 0 <= self._active_panel_index < len(self.panels):
            current_panel = self.panels[self._active_panel_index]
            if current_panel is not None:
                current_panel.grid_remove()

        panel = self._get_panel(index)
        if self._panel_uses_internal_scroll(index):
            self.control_scroll.grid_remove()
            panel.grid(row=0, column=0, sticky="nsew")
            if hasattr(panel, "scroll_to_top"):
                self.after_idle(panel.scroll_to_top)
        else:
            self.control_scroll.grid(row=0, column=0, sticky="nsew")
            panel.grid(row=0, column=0, sticky="nsew")
        self._active_panel_index = index

        if not self._panel_uses_internal_scroll(index):
            parent_canvas = getattr(self.control_scroll, "_parent_canvas", None)
            if parent_canvas is not None:
                self.after_idle(lambda: parent_canvas.yview_moveto(0))

    def _panel_uses_internal_scroll(self, index: int) -> bool:
        return index == 2

    def _get_panel(self, index):
        panel = self.panels[index]
        if panel is not None:
            return panel

        panel = self._panel_factories[index]()
        self.panels[index] = panel
        return panel

    def _create_video_panel(self):
        from ui.panels.video_panel import VideoPanel

        return VideoPanel(self.control_scroll, self.app_state)

    def _create_transcribe_panel(self):
        from ui.panels.transcribe_panel import TranscribePanel

        return TranscribePanel(self.control_scroll, self.app_state)

    def _create_style_panel(self):
        from ui.panels.style_panel import StylePanel

        return StylePanel(self.control_container, self.app_state)

    def _create_export_panel(self):
        from ui.panels.export_panel import ExportPanel

        return ExportPanel(self.control_scroll, self.app_state)

    def _create_settings_panel(self):
        from ui.panels.settings_panel import SettingsPanel

        return SettingsPanel(self.control_scroll, self.app_state)

    def _resolve_pane_color(self) -> str:
        is_dark = ctk.get_appearance_mode().lower() == "dark"
        color = COLORS["bg_primary"][1] if is_dark else COLORS["bg_primary"][0]
        return color

    def _update_pane_colors(self):
        """Update PanedWindow backgrounds on theme change."""
        color = self._resolve_pane_color()
        try:
            self.vertical_pane.configure(bg=color)
            self.top_pane.configure(bg=color)
        except Exception:
            pass

    def _set_initial_sashes(self):
        try:
            w = max(1, self.main_frame.winfo_width())
            h = max(1, self.main_frame.winfo_height())
            self.top_pane.sash_place(0, int(w * 0.62), 0)
            self.vertical_pane.sash_place(0, 0, int(h * 0.62))
        except tk.TclError:
            pass

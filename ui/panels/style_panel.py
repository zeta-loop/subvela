import customtkinter as ctk
import tkinter as tk
from tkinter import colorchooser, font as tkfont, simpledialog
from app.theme import COLORS, FONTS, SPACING, RADIUS, get_font_family
from core.font_catalog import (
    get_font_display_label,
    get_font_dropdown_entries,
    refresh_font_catalog,
    resolve_font_family_name,
)
from core.presets import PresetManager
from core.subtitle_model import SubtitleAnimation


class StylePanel(ctk.CTkFrame):
    def __init__(self, parent, state, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.state = state
        self.preset_manager = PresetManager()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ff = get_font_family()

        # Title
        ctk.CTkLabel(
            self, text="Subtitle Style",
            font=ctk.CTkFont(family=ff, size=FONTS["display"][1], weight="bold"),
            text_color=COLORS["text_heading"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w",
               padx=SPACING["lg"], pady=(SPACING["lg"], SPACING["md"]))

        scope_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"], corner_radius=RADIUS["card"])
        scope_frame.grid(row=1, column=0, sticky="ew",
                         padx=SPACING["lg"], pady=(0, SPACING["md"]))
        scope_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            scope_frame, text="Editing Scope",
            font=ctk.CTkFont(family=ff, size=FONTS["body_bold"][1], weight="bold"),
            text_color=COLORS["text_primary"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(SPACING["lg"], SPACING["md"]), pady=SPACING["md"])

        self.scope_var = ctk.StringVar(value="Global")
        self.scope_btn = ctk.CTkSegmentedButton(
            scope_frame,
            values=["Global", "This Line"],
            variable=self.scope_var,
            font=ctk.CTkFont(family=ff, size=FONTS["body"][1], weight="bold"),
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent_hover"],
            unselected_color=COLORS["entry_bg"],
            unselected_hover_color=COLORS["bg_tertiary"],
            height=40,
            command=self._on_scope_change,
        )
        self.scope_btn.grid(row=0, column=1, sticky="ew", padx=(0, SPACING["lg"]), pady=SPACING["md"])

        self.body_scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=COLORS["scrollbar"],
            scrollbar_button_hover_color=COLORS["scrollbar_hover"],
        )
        self.body_scroll.grid(row=2, column=0, sticky="nsew")
        self.body_scroll.grid_columnconfigure(0, weight=1)
        self.body_scroll.grid_columnconfigure(1, weight=1)

        # --- Preset Section ---
        preset_frame = ctk.CTkFrame(self.body_scroll, fg_color=COLORS["bg_secondary"], corner_radius=RADIUS["card"])
        preset_frame.grid(row=0, column=0, columnspan=2, sticky="ew",
                          padx=SPACING["lg"], pady=(0, SPACING["md"]))
        preset_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            preset_frame, text="Style Preset:",
            font=ctk.CTkFont(family=ff, size=FONTS["body_bold"][1], weight="bold"),
            text_color=COLORS["text_primary"],
        ).grid(row=0, column=0, padx=SPACING["lg"], pady=SPACING["md"])

        preset_names = self.preset_manager.get_all_names()
        self.preset_var = ctk.StringVar(value="")
        self.preset_dropdown = ctk.CTkComboBox(
            preset_frame, values=preset_names if preset_names else ["(none)"],
            variable=self.preset_var,
            font=ctk.CTkFont(family=ff, size=FONTS["body"][1]),
            fg_color=COLORS["entry_bg"], border_color=COLORS["entry_border"],
            button_color=COLORS["accent"], button_hover_color=COLORS["accent_hover"],
            dropdown_fg_color=COLORS["bg_secondary"],
            corner_radius=RADIUS["sm"], height=30,
            command=self._apply_preset,
        )
        self.preset_dropdown.grid(row=0, column=1, sticky="ew", padx=SPACING["sm"], pady=SPACING["md"])

        self.save_preset_btn = ctk.CTkButton(
            preset_frame, text="Save as Preset",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            fg_color=COLORS["button_secondary"],
            hover_color=COLORS["accent"],
            text_color=COLORS["text_primary"],
            height=30, width=110,
            command=self._save_preset,
            cursor="hand2",
        )
        self.save_preset_btn.grid(row=0, column=2, padx=SPACING["xs"], pady=SPACING["md"])

        self.delete_preset_btn = ctk.CTkButton(
            preset_frame, text="Delete",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            fg_color=COLORS["error"],
            hover_color=("#DC2626", "#DC2626"),
            text_color=COLORS["button_text"],
            height=30, width=70,
            command=self._delete_preset,
            cursor="hand2",
        )
        self.delete_preset_btn.grid(row=0, column=3, padx=(0, SPACING["lg"]), pady=SPACING["md"])

        # --- Animation Style card (full width) ---
        self._mode_map = {"Normal": "off", "Sweep": "sweep", "Highlight": "highlight", "Bounce": "bounce"}
        self._mode_reverse = {v: k for k, v in self._mode_map.items()}
        self._entry_anim_map = {"None": "none", "Fade": "fade", "Pop": "pop", "Slide Up": "slide_up", "Typewriter": "typewriter"}
        self._entry_anim_reverse = {v: k for k, v in self._entry_anim_map.items()}
        self._mode_descriptions = {
            "Normal": "Standard subtitle display",
            "Sweep": "Words appear one by one, building the full sentence",
            "Highlight": "All words shown \u2014 spoken words highlighted progressively",
            "Bounce": "Each word appears alone, large and centered",
        }

        anim_card = ctk.CTkFrame(self.body_scroll, fg_color=COLORS["bg_secondary"], corner_radius=RADIUS["card"])
        self._anim_card = anim_card
        anim_card.grid(row=1, column=0, columnspan=2, sticky="ew",
                       padx=SPACING["lg"], pady=(0, SPACING["md"]))
        anim_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            anim_card, text="Animation Style",
            font=ctk.CTkFont(family=ff, size=FONTS["subheading"][1], weight="bold"),
            text_color=COLORS["text_heading"], anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=SPACING["lg"], pady=(SPACING["md"], SPACING["sm"]))

        current_mode = self._mode_reverse.get(state.karaoke_mode, "Normal")
        self.anim_var = ctk.StringVar(value=current_mode)
        self.anim_selector = ctk.CTkSegmentedButton(
            anim_card,
            values=["Normal", "Sweep", "Highlight", "Bounce"],
            variable=self.anim_var,
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent_hover"],
            command=self._on_animation_change,
        )
        self.anim_selector.grid(row=0, column=1, sticky="ew", padx=(0, SPACING["lg"]), pady=(SPACING["md"], SPACING["sm"]))

        self.anim_desc_label = ctk.CTkLabel(
            anim_card, text=self._mode_descriptions[current_mode],
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            text_color=COLORS["text_secondary"],
            anchor="w",
        )
        self.anim_desc_label.grid(row=1, column=0, columnspan=2, sticky="w",
                                  padx=SPACING["lg"], pady=(0, SPACING["xs"]))

        # mode_settings_frame — row=2 in anim_card, swaps sub-frames per mode
        self.mode_settings_frame = ctk.CTkFrame(anim_card, fg_color="transparent")
        self.mode_settings_frame.grid(row=2, column=0, columnspan=2, sticky="ew",
                                       padx=0, pady=(0, SPACING["md"]))
        self.mode_settings_frame.grid_columnconfigure(0, weight=1)

        # ── Normal settings ──────────────────────────────────────────────
        self.normal_settings = ctk.CTkFrame(self.mode_settings_frame, fg_color="transparent")
        self.normal_settings.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self.normal_settings, text="Transition:",
            font=ctk.CTkFont(family=ff, size=FONTS["body"][1]),
            text_color=COLORS["text_secondary"],
        ).grid(row=0, column=0, padx=(SPACING["lg"], SPACING["md"]))

        self.entry_anim_var = ctk.StringVar(value=self._entry_anim_reverse.get(state.animation_style, "None"))
        self.entry_anim_selector = ctk.CTkSegmentedButton(
            self.normal_settings,
            values=["None", "Fade", "Pop", "Slide Up", "Typewriter"],
            variable=self.entry_anim_var,
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent_hover"],
            command=self._on_entry_anim_change,
        )
        self.entry_anim_selector.grid(row=0, column=1, sticky="ew", padx=(0, SPACING["lg"]))

        self.duration_row = ctk.CTkFrame(self.normal_settings, fg_color="transparent")
        self.duration_row.grid(row=1, column=0, columnspan=2, sticky="ew",
                               padx=SPACING["lg"], pady=(SPACING["xs"], 0))
        self.duration_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self.duration_row, text="Duration:",
            font=ctk.CTkFont(family=ff, size=FONTS["body"][1]),
            text_color=COLORS["text_secondary"],
        ).grid(row=0, column=0, padx=(0, SPACING["md"]))

        self.duration_slider = ctk.CTkSlider(
            self.duration_row, from_=0.05, to=1.0, number_of_steps=19,
            progress_color=COLORS["accent"], button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"], fg_color=COLORS["progress_bg"],
            command=self._on_duration_change, height=14,
        )
        self.duration_slider.set(getattr(state, 'transition_duration', 0.30))
        self.duration_slider.grid(row=0, column=1, sticky="ew")

        self.duration_val_label = ctk.CTkLabel(
            self.duration_row,
            text=f"{int(getattr(state, 'transition_duration', 0.30) * 1000)}ms",
            font=ctk.CTkFont(family=FONTS["mono_small"][0], size=FONTS["mono_small"][1]),
            text_color=COLORS["text_secondary"], width=50,
        )
        self.duration_val_label.grid(row=0, column=2, padx=(SPACING["xs"], 0))

        # Hide duration row on init if animation is "none"
        if state.animation_style == "none":
            self.duration_row.grid_remove()

        # ── Highlight settings ────────────────────────────────────────────
        self.highlight_settings = ctk.CTkFrame(self.mode_settings_frame, fg_color="transparent")
        self.highlight_settings.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self.highlight_settings, text="Highlight:",
            font=ctk.CTkFont(family=ff, size=FONTS["body"][1]),
            text_color=COLORS["text_secondary"],
        ).grid(row=0, column=0, padx=(SPACING["lg"], SPACING["sm"]))

        import tkinter as _tk
        self._highlight_swatch = _tk.Canvas(
            self.highlight_settings, width=22, height=22,
            highlightthickness=0, cursor="hand2",
        )
        self._highlight_swatch.grid(row=0, column=1, sticky="w", padx=(0, SPACING["xs"]))
        self._draw_highlight_swatch(state.karaoke_highlight_color)
        self._highlight_swatch.bind("<Button-1>", lambda e: self._pick_highlight_color())

        self._highlight_hex_label = ctk.CTkLabel(
            self.highlight_settings,
            text=state.karaoke_highlight_color,
            font=ctk.CTkFont(family=FONTS["mono_small"][0], size=FONTS["mono_small"][1]),
            text_color=COLORS["text_secondary"],
        )
        self._highlight_hex_label.grid(row=0, column=2, sticky="w")

        ctk.CTkLabel(
            self.highlight_settings, text="Unspoken:",
            font=ctk.CTkFont(family=ff, size=FONTS["body"][1]),
            text_color=COLORS["text_secondary"],
        ).grid(row=1, column=0, padx=(SPACING["lg"], SPACING["md"]), pady=(SPACING["xs"], 0))

        self.dimmed_slider = ctk.CTkSlider(
            self.highlight_settings, from_=0.1, to=0.9, number_of_steps=16,
            progress_color=COLORS["accent"], button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"], fg_color=COLORS["progress_bg"],
            command=self._on_dimmed_change, height=14,
        )
        self.dimmed_slider.set(getattr(state, 'highlight_dimmed_opacity', 0.5))
        self.dimmed_slider.grid(row=1, column=1, sticky="ew",
                                padx=(0, SPACING["xs"]), pady=(SPACING["xs"], 0))

        self.dimmed_val_label = ctk.CTkLabel(
            self.highlight_settings,
            text=f"{int(getattr(state, 'highlight_dimmed_opacity', 0.5) * 100)}%",
            font=ctk.CTkFont(family=FONTS["mono_small"][0], size=FONTS["mono_small"][1]),
            text_color=COLORS["text_secondary"], width=40,
        )
        self.dimmed_val_label.grid(row=1, column=2, sticky="w", pady=(SPACING["xs"], 0))

        ctk.CTkLabel(
            self.highlight_settings, text="Active:",
            font=ctk.CTkFont(family=ff, size=FONTS["body"][1]),
            text_color=COLORS["text_secondary"],
        ).grid(row=2, column=0, padx=(SPACING["lg"], SPACING["md"]), pady=(SPACING["xs"], SPACING["xs"]))

        self.active_marker_var = ctk.StringVar(value={
            "color": "Color", "box": "Box", "color_box": "Color+Box",
        }.get(getattr(state, 'highlight_active_marker', 'color'), "Color"))
        ctk.CTkSegmentedButton(
            self.highlight_settings,
            values=["Color", "Box", "Color+Box"],
            variable=self.active_marker_var,
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent_hover"],
            command=self._on_active_marker_change,
        ).grid(row=2, column=1, columnspan=2, sticky="ew", padx=(0, SPACING["lg"]), pady=(SPACING["xs"], SPACING["xs"]))

        ctk.CTkLabel(
            self.highlight_settings, text="History:",
            font=ctk.CTkFont(family=ff, size=FONTS["body"][1]),
            text_color=COLORS["text_secondary"],
        ).grid(row=3, column=0, padx=(SPACING["lg"], SPACING["md"]), pady=(SPACING["xs"], SPACING["xs"]))

        self.history_on_switch = ctk.CTkSwitch(
            self.highlight_settings, text="Keep history",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            text_color=COLORS["text_secondary"],
            command=self._on_history_on_change,
        )
        if getattr(state, 'highlight_history_on', False):
            self.history_on_switch.select()
        self.history_on_switch.grid(row=3, column=1, columnspan=2, sticky="w",
                                    padx=(0, SPACING["lg"]), pady=(SPACING["xs"], SPACING["xs"]))

        # ── Bounce settings ───────────────────────────────────────────────
        self.bounce_settings = ctk.CTkFrame(self.mode_settings_frame, fg_color="transparent")
        self.bounce_settings.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self.bounce_settings, text="Trail Words:",
            font=ctk.CTkFont(family=ff, size=FONTS["body"][1]),
            text_color=COLORS["text_secondary"],
        ).grid(row=0, column=0, padx=(SPACING["lg"], SPACING["md"]))

        self.bounce_trail_slider = ctk.CTkSlider(
            self.bounce_settings, from_=0, to=5, number_of_steps=5,
            progress_color=COLORS["accent"], button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"], fg_color=COLORS["progress_bg"],
            command=self._on_bounce_trail_change, height=14,
        )
        self.bounce_trail_slider.set(getattr(state, 'bounce_trail_count', 3))
        self.bounce_trail_slider.grid(row=0, column=1, sticky="ew")

        self.bounce_trail_val = ctk.CTkLabel(
            self.bounce_settings,
            text=str(getattr(state, 'bounce_trail_count', 3)),
            font=ctk.CTkFont(family=FONTS["mono_small"][0], size=FONTS["mono_small"][1]),
            text_color=COLORS["text_secondary"], width=40,
        )
        self.bounce_trail_val.grid(row=0, column=2, padx=(SPACING["xs"], SPACING["lg"]))

        ctk.CTkLabel(
            self.bounce_settings, text="Minimum Characters:",
            font=ctk.CTkFont(family=ff, size=FONTS["body"][1]),
            text_color=COLORS["text_secondary"],
        ).grid(row=1, column=0, padx=(SPACING["lg"], SPACING["md"]), pady=(SPACING["xs"], 0))

        self.bounce_min_chars_slider = ctk.CTkSlider(
            self.bounce_settings, from_=0, to=8, number_of_steps=8,
            progress_color=COLORS["accent"], button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"], fg_color=COLORS["progress_bg"],
            command=self._on_bounce_min_chars_change, height=14,
        )
        self.bounce_min_chars_slider.set(getattr(state, 'bounce_min_chars', 3))
        self.bounce_min_chars_slider.grid(row=1, column=1, sticky="ew", pady=(SPACING["xs"], 0))

        self.bounce_min_chars_val = ctk.CTkLabel(
            self.bounce_settings,
            text=str(getattr(state, 'bounce_min_chars', 3)),
            font=ctk.CTkFont(family=FONTS["mono_small"][0], size=FONTS["mono_small"][1]),
            text_color=COLORS["text_secondary"], width=40,
        )
        self.bounce_min_chars_val.grid(row=1, column=2, padx=(SPACING["xs"], SPACING["lg"]),
                                      pady=(SPACING["xs"], 0))

        # ── Sweep settings ────────────────────────────────────────────────
        self.sweep_settings = ctk.CTkFrame(self.mode_settings_frame, fg_color="transparent")
        self.sweep_settings.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self.sweep_settings, text="Entry Style:",
            font=ctk.CTkFont(family=ff, size=FONTS["body"][1]),
            text_color=COLORS["text_secondary"],
        ).grid(row=0, column=0, padx=(SPACING["lg"], SPACING["md"]))

        self.sweep_entry_var = ctk.StringVar(
            value={"instant": "Instant", "fade": "Fade", "pop": "Pop"}.get(
                getattr(state, 'sweep_entry_style', 'instant'), "Instant"
            )
        )
        ctk.CTkSegmentedButton(
            self.sweep_settings,
            values=["Instant", "Fade", "Pop"],
            variable=self.sweep_entry_var,
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent_hover"],
            command=self._on_sweep_entry_change,
        ).grid(row=0, column=1, sticky="ew", padx=(0, SPACING["lg"]))

        ctk.CTkLabel(
            self.sweep_settings, text="History Opacity:",
            font=ctk.CTkFont(family=ff, size=FONTS["body"][1]),
            text_color=COLORS["text_secondary"],
        ).grid(row=1, column=0, padx=(SPACING["lg"], SPACING["md"]), pady=(SPACING["xs"], SPACING["xs"]))

        self.sweep_dim_slider = ctk.CTkSlider(
            self.sweep_settings, from_=0.0, to=1.0, number_of_steps=20,
            progress_color=COLORS["accent"], button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"], fg_color=COLORS["progress_bg"],
            command=self._on_sweep_dim_change, height=14,
        )
        self.sweep_dim_slider.set(getattr(state, "sweep_history_dim", 1.0))
        self.sweep_dim_slider.grid(row=1, column=1, sticky="ew",
                                     padx=(0, SPACING["xs"]), pady=(SPACING["xs"], SPACING["xs"]))

        self.sweep_dim_val = ctk.CTkLabel(
            self.sweep_settings,
            text=f"{getattr(state, 'sweep_history_dim', 1.0):.0%}",
            font=ctk.CTkFont(family=FONTS["mono_small"][0], size=FONTS["mono_small"][1]),
            text_color=COLORS["text_secondary"], width=36,
        )
        self.sweep_dim_val.grid(row=1, column=2, padx=(SPACING["xs"], SPACING["lg"]),
                                  pady=(SPACING["xs"], SPACING["xs"]))

        # Show the correct sub-frame for the initial mode
        self._show_mode_settings(current_mode)

        # --- Appearance Area ---
        # ── Translation Animation card (only shown after translation) ────────
        self._trans_anim_map = {"None": "none", "Fade": "fade", "Pop": "pop", "Slide Up": "slide_up"}
        self._trans_anim_rev = {v: k for k, v in self._trans_anim_map.items()}

        self.trans_anim_card = ctk.CTkFrame(self.body_scroll, fg_color=COLORS["bg_secondary"], corner_radius=RADIUS["card"])
        self.trans_anim_card.grid(row=2, column=0, columnspan=2, sticky="ew",
                                   padx=SPACING["lg"], pady=(0, SPACING["md"]))
        self.trans_anim_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self.trans_anim_card, text="Translation Transition",
            font=ctk.CTkFont(family=ff, size=FONTS["subheading"][1], weight="bold"),
            text_color=COLORS["text_heading"], anchor="w",
        ).grid(row=0, column=0, padx=(SPACING["lg"], SPACING["md"]), pady=(SPACING["md"], SPACING["sm"]))

        self.trans_anim_var = ctk.StringVar(
            value=self._trans_anim_rev.get(state.translation_animation_style, "None")
        )
        ctk.CTkSegmentedButton(
            self.trans_anim_card,
            values=["None", "Fade", "Pop", "Slide Up"],
            variable=self.trans_anim_var,
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent_hover"],
            command=self._on_translation_anim_change,
        ).grid(row=0, column=1, sticky="ew", padx=(0, SPACING["lg"]), pady=(SPACING["md"], SPACING["sm"]))

        # Hidden until translation exists
        self.trans_anim_card.grid_remove()

        self.style_container = ctk.CTkFrame(self.body_scroll, fg_color="transparent")
        self.style_container.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=SPACING["lg"])
        self.style_container.grid_columnconfigure(0, weight=1)
        self.style_container.grid_columnconfigure(1, weight=1)

        # Main appearance section title
        self.appearance_main_title = ctk.CTkLabel(
            self.style_container, text="Appearance Settings",
            font=ctk.CTkFont(family=ff, size=FONTS["subheading"][1], weight="bold"),
            text_color=COLORS["text_heading"], anchor="w",
        )
        self.appearance_main_title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, SPACING["xs"]))

        # Horizontal separator
        self.title_sep = ctk.CTkFrame(self.style_container, height=2, fg_color=COLORS["accent_muted"])
        self.title_sep.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, SPACING["sm"]))

        # Primary Header (Full Width initially, or shared)
        self.appearance_header = ctk.CTkLabel(
            self.style_container, text="Primary (Original)",
            font=ctk.CTkFont(family=ff, size=FONTS["body_bold"][1], weight="bold"),
            text_color=COLORS["accent"], anchor="w",
        )
        # grid() called in _update_secondary_visibility

        # Secondary header (only shown when bilingual)
        self.secondary_header = ctk.CTkLabel(
            self.style_container, text="Secondary (Translation)",
            font=ctk.CTkFont(family=ff, size=FONTS["body_bold"][1], weight="bold"),
            text_color=COLORS["warning"], anchor="w",
        )
        # grid() called in _update_secondary_visibility

        self.primary_controls = StyleColumn(self.style_container, state, "primary", "")
        self.primary_controls.grid(row=4, column=0, sticky="nsew", padx=(0, SPACING["sm"]))

        self.secondary_controls = StyleColumn(self.style_container, state, "secondary", "")
        self.secondary_controls.grid(row=4, column=1, sticky="nsew", padx=(SPACING["sm"], 0))

        # Cross-reference so each column can update the other's slider on overlap
        self.primary_controls._sibling = self.secondary_controls
        self.secondary_controls._sibling = self.primary_controls

        # Listen for state changes
        self.state.add_listener(self._on_state_change)
        self._update_secondary_visibility()

    def scroll_to_top(self):
        canvas = getattr(self.body_scroll, "_parent_canvas", None)
        if canvas is not None:
            canvas.yview_moveto(0)

    def _apply_preset(self, name):
        preset = self.preset_manager.get_preset(name)
        if not preset:
            return
        if self.scope_var.get() == "This Line":
            import copy

            idx = self.state.selected_subtitle_index
            if not (0 <= idx < len(self.state.subtitles)):
                return
            sub = self.state.subtitles[idx]
            sub.primary_style_override = copy.deepcopy(preset.primary)
            if self.state.bilingual and preset.secondary is not None:
                sub.secondary_style_override = copy.deepcopy(preset.secondary)
            elif not self.state.bilingual:
                sub.secondary_style_override = None
            if preset.animation is not None:
                sub.animation_override = SubtitleAnimation.from_dict(preset.animation.to_dict())
            self.state.notify("subtitles_edited")
            self.state.notify("style")
            self._refresh_scope_display()
            self._apply_animation_controls_from_scope()
            return

        self.state.update_primary_style(**preset.primary.to_dict())
        self.primary_controls.refresh_from_style()
        if preset.secondary is not None:
            self.state.update_secondary_style(**preset.secondary.to_dict())
            self.secondary_controls.refresh_from_style()
        if preset.animation is not None:
            self.state.apply_animation_preset(preset.animation)

    def _save_preset(self):
        name = simpledialog.askstring("Save Preset", "Enter preset name:")
        if name and name.strip():
            name = name.strip()
            from core.subtitle_model import SubtitleAnimation
            anim = self.state.get_animation_settings_for_subtitle(None)
            secondary = self.state.secondary_style if self.state.bilingual else None
            self.preset_manager.save_user_preset(
                name,
                primary=self.state.primary_style,
                secondary=secondary,
                animation=anim,
            )
            self._refresh_preset_dropdown()
            self.preset_var.set(name)

    def _delete_preset(self):
        name = self.preset_var.get()
        if not name:
            return
        if not self.preset_manager.is_user_preset(name):
            return  # Can't delete built-in presets
        self.preset_manager.delete_user_preset(name)
        self._refresh_preset_dropdown()
        self.preset_var.set("")

    def _refresh_preset_dropdown(self):
        names = self.preset_manager.get_all_names()
        self.preset_dropdown.configure(values=names if names else ["(none)"])

    def _show_mode_settings(self, mode_label: str):
        for f in (self.normal_settings, self.highlight_settings,
                  self.bounce_settings, self.sweep_settings):
            f.grid_remove()
        m = {"Normal": self.normal_settings, "Highlight": self.highlight_settings,
             "Bounce": self.bounce_settings, "Sweep": self.sweep_settings}
        if mode_label in m:
            m[mode_label].grid(row=0, column=0, sticky="ew")

    def _on_animation_change(self, value):
        self._update_animation_settings(karaoke_mode=self._mode_map.get(value, "off"))
        self.anim_desc_label.configure(text=self._mode_descriptions.get(value, ""))
        self._show_mode_settings(value)
        self._update_translation_animation_visibility()

    def _on_entry_anim_change(self, value):
        self._update_animation_settings(animation_style=self._entry_anim_map.get(value, "none"))
        if value == "None":
            self.duration_row.grid_remove()
        else:
            self.duration_row.grid()

    def _on_duration_change(self, value):
        self.duration_val_label.configure(text=f"{int(float(value) * 1000)}ms")
        self._update_animation_settings(transition_duration=float(value))

    def _on_dimmed_change(self, value):
        self.dimmed_val_label.configure(text=f"{int(float(value) * 100)}%")
        self._update_animation_settings(highlight_dimmed_opacity=float(value))

    def _on_bounce_trail_change(self, value):
        count = int(round(float(value)))
        self.bounce_trail_val.configure(text=str(count))
        self._update_animation_settings(bounce_trail_count=count)

    def _on_bounce_min_chars_change(self, value):
        count = int(round(float(value)))
        self.bounce_min_chars_val.configure(text=str(count))
        self._update_animation_settings(bounce_min_chars=count)

    def _on_sweep_entry_change(self, value):
        self._update_animation_settings(sweep_entry_style=value.lower())

    def _on_sweep_dim_change(self, value):
        self.sweep_dim_val.configure(text=f"{float(value):.0%}")
        self._update_animation_settings(sweep_history_dim=float(value))

    def _on_active_marker_change(self, value):
        mapping = {"Color": "color", "Box": "box", "Color+Box": "color_box"}
        self._update_animation_settings(highlight_active_marker=mapping.get(value, "color"))

    def _on_history_on_change(self):
        self._update_animation_settings(highlight_history_on=self.history_on_switch.get() == 1)

    def _on_translation_anim_change(self, value):
        self._update_animation_settings(translation_animation_style=self._trans_anim_map.get(value, "none"))

    def _on_state_change(self, field):
        if field in ("bilingual", "subtitles", "subtitles_edited", "karaoke_mode"):
            self._update_secondary_visibility()
        if field == "karaoke_mode":
            display = self._mode_reverse.get(self._get_animation_settings_for_scope().karaoke_mode, "Normal")
            self.anim_var.set(display)
            self.anim_desc_label.configure(text=self._mode_descriptions.get(display, ""))
            self._show_mode_settings(display)
        elif field == "animation_style":
            current = self._get_animation_settings_for_scope().animation_style
            self.entry_anim_var.set(self._entry_anim_reverse.get(current, "None"))
            if current == "none":
                self.duration_row.grid_remove()
            else:
                self.duration_row.grid()
        elif field == "highlight_active_marker":
            mapping = {"color": "Color", "box": "Box", "color_box": "Color+Box"}
            self.active_marker_var.set(mapping.get(self.state.highlight_active_marker, "Color"))
        elif field == "highlight_history_on":
            if self.state.highlight_history_on:
                self.history_on_switch.select()
            else:
                self.history_on_switch.deselect()
        elif field == "karaoke_highlight_color":
            self._draw_highlight_swatch(self.state.karaoke_highlight_color)
            self._highlight_hex_label.configure(text=self.state.karaoke_highlight_color)
        elif field == "transition_duration":
            self.duration_slider.set(self.state.transition_duration)
            self.duration_val_label.configure(text=f"{int(self.state.transition_duration * 1000)}ms")
        elif field == "highlight_dimmed_opacity":
            self.dimmed_slider.set(self.state.highlight_dimmed_opacity)
            self.dimmed_val_label.configure(text=f"{int(self.state.highlight_dimmed_opacity * 100)}%")
        elif field == "bounce_trail_count":
            self.bounce_trail_slider.set(self.state.bounce_trail_count)
            self.bounce_trail_val.configure(text=str(self.state.bounce_trail_count))
        elif field == "bounce_min_chars":
            self.bounce_min_chars_slider.set(self.state.bounce_min_chars)
            self.bounce_min_chars_val.configure(text=str(self.state.bounce_min_chars))
        elif field == "sweep_entry_style":
            self.sweep_entry_var.set(self.state.sweep_entry_style.capitalize())
        elif field == "sweep_history_dim":
            self.sweep_dim_slider.set(self.state.sweep_history_dim)
            self.sweep_dim_val.configure(text=f"{self.state.sweep_history_dim:.0%}")
        elif field == "selected_subtitle":
            if self.scope_var.get() == "This Line":
                self._refresh_scope_display()
                self._apply_animation_controls_from_scope()
        elif field == "style":
            if self.scope_var.get() == "Global":
                self.primary_controls.refresh_from_style()
                if self.state.bilingual:
                    self.secondary_controls.refresh_from_style()
            else:
                self._refresh_scope_display()
        elif field == "subtitles_edited" and self.scope_var.get() == "This Line":
            self._refresh_scope_display()
            self._apply_animation_controls_from_scope()

    def _on_scope_change(self, value):
        if value == "This Line":
            if self.state.selected_subtitle_index < 0:
                self.scope_var.set("Global")
                return
            self._refresh_scope_display()
        else:
            self.primary_controls.set_scope("global", self.state.primary_style)
            self.secondary_controls.set_scope("global", self.state.secondary_style)
        self._apply_animation_controls_from_scope()
        self._update_translation_animation_visibility()

    def _refresh_scope_display(self):
        idx = self.state.selected_subtitle_index
        if idx < 0:
            self.scope_var.set("Global")
            self.primary_controls.set_scope("global", self.state.primary_style)
            self.secondary_controls.set_scope("global", self.state.secondary_style)
            return
        sub = self.state.subtitles[idx]
        self.primary_controls.set_scope("line", self.state.get_primary_style_for_subtitle(sub))
        self.secondary_controls.set_scope("line", self.state.get_secondary_style_for_subtitle(sub))

    def _draw_highlight_swatch(self, color):
        self._highlight_swatch.delete("all")
        self._highlight_swatch.create_oval(2, 2, 20, 20, fill=color, outline=color, width=1)
        is_dark = ctk.get_appearance_mode().lower() == "dark"
        border = COLORS["border"][1] if is_dark else COLORS["border"][0]
        self._highlight_swatch.create_oval(2, 2, 20, 20, outline=border, width=1)
        bg = COLORS["bg_secondary"][1] if is_dark else COLORS["bg_secondary"][0]
        self._highlight_swatch.configure(bg=bg)

    def _pick_highlight_color(self):
        result = colorchooser.askcolor(
            color=self.state.karaoke_highlight_color, title="Choose Highlight Color"
        )
        if result[1]:
            self._update_animation_settings(karaoke_highlight_color=result[1])

    def _get_selected_subtitle(self):
        idx = self.state.selected_subtitle_index
        if 0 <= idx < len(self.state.subtitles):
            return self.state.subtitles[idx]
        return None

    def _get_animation_settings_for_scope(self):
        sub = self._get_selected_subtitle() if self.scope_var.get() == "This Line" else None
        return self.state.get_animation_settings_for_subtitle(sub)

    def _update_animation_settings(self, **kwargs):
        if self.scope_var.get() == "This Line":
            sub = self._get_selected_subtitle()
            if sub is None:
                return
            if sub.animation_override is None:
                sub.animation_override = SubtitleAnimation.from_dict(
                    self.state.get_animation_settings_for_subtitle(sub).to_dict()
                )
            for key, value in kwargs.items():
                if hasattr(sub.animation_override, key):
                    setattr(sub.animation_override, key, value)
            self.state.notify("subtitles_edited")
            return

        setter_map = {
            "karaoke_mode": self.state.set_karaoke_mode,
            "animation_style": self.state.set_animation_style,
            "translation_animation_style": self.state.set_translation_animation_style,
            "transition_duration": self.state.set_transition_duration,
            "karaoke_highlight_color": self.state.set_karaoke_highlight_color,
            "highlight_dimmed_opacity": self.state.set_highlight_dimmed_opacity,
            "bounce_trail_count": self.state.set_bounce_trail_count,
            "bounce_min_chars": self.state.set_bounce_min_chars,
            "sweep_entry_style": self.state.set_sweep_entry_style,
            "sweep_history_dim": self.state.set_sweep_history_dim,
            "highlight_active_marker": self.state.set_highlight_active_marker,
            "highlight_history_on": self.state.set_highlight_history_on,
        }
        for key, value in kwargs.items():
            setter = setter_map.get(key)
            if setter is not None:
                setter(value)

    def _apply_animation_controls_from_scope(self):
        settings = self._get_animation_settings_for_scope()
        mode_label = self._mode_reverse.get(settings.karaoke_mode, "Normal")
        self.anim_var.set(mode_label)
        self.anim_desc_label.configure(text=self._mode_descriptions.get(mode_label, ""))
        self._show_mode_settings(mode_label)

        self.entry_anim_var.set(self._entry_anim_reverse.get(settings.animation_style, "None"))
        self.duration_slider.set(settings.transition_duration)
        self.duration_val_label.configure(text=f"{int(settings.transition_duration * 1000)}ms")
        if settings.animation_style == "none":
            self.duration_row.grid_remove()
        else:
            self.duration_row.grid()

        self._draw_highlight_swatch(settings.karaoke_highlight_color)
        self._highlight_hex_label.configure(text=settings.karaoke_highlight_color)
        self.dimmed_slider.set(settings.highlight_dimmed_opacity)
        self.dimmed_val_label.configure(text=f"{int(settings.highlight_dimmed_opacity * 100)}%")
        self.active_marker_var.set({
            "color": "Color",
            "box": "Box",
            "color_box": "Color+Box",
        }.get(settings.highlight_active_marker, "Color"))
        if settings.highlight_history_on:
            self.history_on_switch.select()
        else:
            self.history_on_switch.deselect()
        self.bounce_trail_slider.set(settings.bounce_trail_count)
        self.bounce_trail_val.configure(text=str(settings.bounce_trail_count))
        self.bounce_min_chars_slider.set(settings.bounce_min_chars)
        self.bounce_min_chars_val.configure(text=str(settings.bounce_min_chars))
        self.sweep_entry_var.set({
            "instant": "Instant",
            "fade": "Fade",
            "pop": "Pop",
        }.get(settings.sweep_entry_style, "Instant"))
        self.sweep_dim_slider.set(settings.sweep_history_dim)
        self.sweep_dim_val.configure(text=f"{settings.sweep_history_dim:.0%}")
        self.trans_anim_var.set(self._trans_anim_rev.get(settings.translation_animation_style, "None"))

    def _update_translation_animation_visibility(self):
        has_translation = self.state.bilingual and any(s.translated_text for s in self.state.subtitles)
        is_karaoke = self._get_animation_settings_for_scope().karaoke_mode != "off"
        if has_translation and is_karaoke:
            self.trans_anim_card.grid()
        else:
            self.trans_anim_card.grid_remove()


    def _update_secondary_visibility(self):
        self._update_translation_animation_visibility()

        if self.state.bilingual:
            self.appearance_main_title.configure(text="Appearance Settings")
            self.appearance_header.grid(row=2, column=0, sticky="w", pady=(SPACING["sm"], 0))
            self.secondary_header.grid(row=2, column=1, sticky="w", padx=(SPACING["sm"], 0), pady=(SPACING["sm"], 0))
            self.primary_controls.grid(row=3, column=0, columnspan=1, sticky="nsew", padx=(0, SPACING["sm"]))
            self.secondary_controls.grid(row=3, column=1, columnspan=1, sticky="nsew", padx=(SPACING["sm"], 0))
            self.style_container.grid_rowconfigure(3, weight=1)
            swapped = getattr(self.state, "position_swapped", False)
            self.primary_controls.show_bilingual_order(True, swapped)
            self.secondary_controls.show_bilingual_spacer(True)
            # Apply position constraints
            self.primary_controls._apply_position_constraints()
            self.secondary_controls._apply_position_constraints()
        else:
            self.appearance_main_title.configure(text="Appearance Settings")
            self.appearance_header.grid(row=2, column=0, columnspan=2, sticky="w", pady=(SPACING["sm"], 0))
            self.secondary_header.grid_remove()
            self.primary_controls.show_bilingual_order(False)
            self.secondary_controls.show_bilingual_spacer(False)
            self.primary_controls.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=0)
            self.secondary_controls.grid_remove()

class StyleColumn(ctk.CTkFrame):
    def __init__(self, parent, state, style_key, title, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_secondary"], corner_radius=RADIUS["card"], **kwargs)
        self.state = state
        self.style_key = style_key
        self._scope = "global"  # "global" or "line"
        self._sibling = None    # set by parent to the other StyleColumn

        style = self.state.primary_style if style_key == "primary" else self.state.secondary_style
        ff = get_font_family()

        self.grid_columnconfigure(0, weight=1)

        row = 0

        # Section title (only show if title provided)
        if title:
            ctk.CTkLabel(
                self, text=title,
                font=ctk.CTkFont(family=ff, size=FONTS["subheading"][1], weight="bold"),
                text_color=COLORS["text_heading"],
                anchor="w",
            ).grid(row=row, column=0, sticky="w", padx=SPACING["lg"], pady=(SPACING["md"], SPACING["sm"]))
            row += 1
        else:
            # Add top padding if no title
            ctk.CTkFrame(self, height=SPACING["md"], fg_color="transparent").grid(row=row, column=0)
            row += 1

        # Font family
        row = self._add_label(row, "Font Family", ff)
        self._font_label_to_family = {}
        self._font_family_to_label = {}
        self.font_var = ctk.StringVar(value=get_font_display_label(style.font_family) or style.font_family)
        self._font_trace_active = True
        self.font_var.trace_add("write", self._on_font_var_change)

        font_row = ctk.CTkFrame(self, fg_color="transparent")
        font_row.grid(row=row, column=0, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["sm"]))
        font_row.grid_columnconfigure(0, weight=1)

        self.font_dropdown = ctk.CTkComboBox(
            font_row, values=[], variable=self.font_var,
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            fg_color=COLORS["entry_bg"], border_color=COLORS["entry_border"],
            button_color=COLORS["accent"], button_hover_color=COLORS["accent_hover"],
            dropdown_fg_color=COLORS["bg_secondary"],
            corner_radius=RADIUS["sm"], height=30,
        )
        self.font_dropdown.grid(row=0, column=0, sticky="ew", padx=(0, SPACING["xs"]))

        self.refresh_fonts_btn = ctk.CTkButton(
            font_row,
            text="Refresh",
            width=72,
            height=30,
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            fg_color=COLORS["button_secondary"],
            hover_color=COLORS["button_secondary_hover"],
            text_color=COLORS["text_primary"],
            command=self._on_refresh_fonts,
            cursor="hand2",
        )
        self.refresh_fonts_btn.grid(row=0, column=1)

        self._reload_font_dropdown()
        row += 1

        # Separator
        row = self._add_separator(row)

        # Font size with min/max labels
        row = self._add_label(row, "Font Size", ff)
        size_frame = ctk.CTkFrame(self, fg_color="transparent")
        size_frame.grid(row=row, column=0, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["xxs"]))
        size_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            size_frame, text="16",
            font=ctk.CTkFont(family=ff, size=FONTS["caption"][1]),
            text_color=COLORS["text_muted"], width=20,
        ).grid(row=0, column=0)

        self.size_slider = ctk.CTkSlider(
            size_frame, from_=16, to=120, number_of_steps=104,
            progress_color=COLORS["accent"], button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"], fg_color=COLORS["progress_bg"],
            command=self._on_size_change, height=14,
        )
        self.size_slider.set(style.font_size)
        self.size_slider.grid(row=0, column=1, sticky="ew", padx=SPACING["xs"])

        self.size_label = ctk.CTkLabel(
            size_frame, text=str(style.font_size),
            font=ctk.CTkFont(family=FONTS["mono_small"][0], size=FONTS["mono_small"][1]),
            text_color=COLORS["text_secondary"], width=35,
        )
        self.size_label.grid(row=0, column=2)

        ctk.CTkLabel(
            size_frame, text="120",
            font=ctk.CTkFont(family=ff, size=FONTS["caption"][1]),
            text_color=COLORS["text_muted"], width=24,
        ).grid(row=0, column=3)
        row += 1

        # Separator
        row = self._add_separator(row)

        # Text color with canvas swatch
        row = self._add_label(row, "Text Color", ff)
        color_frame = ctk.CTkFrame(self, fg_color="transparent")
        color_frame.grid(row=row, column=0, sticky="w", padx=SPACING["lg"], pady=(0, SPACING["sm"]))

        self.color_swatch = tk.Canvas(
            color_frame, width=24, height=24,
            highlightthickness=0, cursor="hand2",
        )
        self.color_swatch.grid(row=0, column=0, padx=(0, SPACING["sm"]))
        self._draw_swatch(self.color_swatch, style.primary_color)
        self.color_swatch.bind("<Button-1>", lambda e: self._pick_color("primary_color", self.color_swatch, self.color_hex_label))

        self.color_hex_label = ctk.CTkLabel(
            color_frame, text=style.primary_color,
            font=ctk.CTkFont(family=FONTS["mono_small"][0], size=FONTS["mono_small"][1]),
            text_color=COLORS["text_secondary"],
        )
        self.color_hex_label.grid(row=0, column=1)
        row += 1

        # Separator
        row = self._add_separator(row)

        # Outline color + thickness
        row = self._add_label(row, "Outline", ff)
        outline_frame = ctk.CTkFrame(self, fg_color="transparent")
        outline_frame.grid(row=row, column=0, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["sm"]))
        outline_frame.grid_columnconfigure(2, weight=1)

        self.outline_swatch = tk.Canvas(
            outline_frame, width=24, height=24,
            highlightthickness=0, cursor="hand2",
        )
        self.outline_swatch.grid(row=0, column=0, padx=(0, SPACING["sm"]))
        self._draw_swatch(self.outline_swatch, style.outline_color)
        self.outline_swatch.bind("<Button-1>", lambda e: self._pick_color("outline_color", self.outline_swatch, self.outline_hex_label))

        self.outline_hex_label = ctk.CTkLabel(
            outline_frame, text=style.outline_color,
            font=ctk.CTkFont(family=FONTS["mono_small"][0], size=FONTS["mono_small"][1]),
            text_color=COLORS["text_secondary"],
            width=60,
        )
        self.outline_hex_label.grid(row=0, column=1, padx=(0, SPACING["sm"]))

        self.outline_slider = ctk.CTkSlider(
            outline_frame, from_=0, to=8, number_of_steps=8,
            progress_color=COLORS["accent"], button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"], fg_color=COLORS["progress_bg"],
            command=self._on_outline_change, height=14,
        )
        self.outline_slider.set(style.outline_thickness)
        self.outline_slider.grid(row=0, column=2, sticky="ew")
        row += 1

        # Separator
        row = self._add_separator(row)

        # Bold / Italic toggles
        row = self._add_label(row, "Style", ff)
        toggle_frame = ctk.CTkFrame(self, fg_color="transparent")
        toggle_frame.grid(row=row, column=0, sticky="w", padx=SPACING["lg"], pady=(0, SPACING["sm"]))

        self.bold_switch = ctk.CTkSwitch(
            toggle_frame, text="Bold",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            text_color=COLORS["text_secondary"],
            command=lambda: self._update_style(bold=bool(self.bold_switch.get())),
        )
        self.bold_switch.grid(row=0, column=0, padx=(0, SPACING["lg"]))
        if style.bold:
            self.bold_switch.select()

        self.italic_switch = ctk.CTkSwitch(
            toggle_frame, text="Italic",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            text_color=COLORS["text_secondary"],
            command=lambda: self._update_style(italic=bool(self.italic_switch.get())),
        )
        self.italic_switch.grid(row=0, column=1)
        if style.italic:
            self.italic_switch.select()
        row += 1

        # Separator
        row = self._add_separator(row)

        # Background box
        row = self._add_label(row, "Background Box", ff)
        bg_frame = ctk.CTkFrame(self, fg_color="transparent")
        bg_frame.grid(row=row, column=0, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["xs"]))

        self.bg_switch = ctk.CTkSwitch(
            bg_frame, text="Enable",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            text_color=COLORS["text_secondary"],
            command=self._on_background_toggle,
        )
        self.bg_switch.grid(row=0, column=0, sticky="w")
        if style.background_enabled:
            self.bg_switch.select()

        row += 1

        self.bg_details_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.bg_details_frame.grid(row=row, column=0, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["sm"]))
        self.bg_details_frame.grid_columnconfigure(1, weight=1)

        self.bg_swatch = tk.Canvas(
            self.bg_details_frame, width=22, height=22, highlightthickness=0, cursor="hand2",
        )
        self.bg_swatch.grid(row=0, column=0, padx=(0, SPACING["xs"]), pady=(0, SPACING["xs"]))
        self._draw_swatch(self.bg_swatch, getattr(style, 'background_color', '#000000'))
        self.bg_swatch.bind("<Button-1>", lambda e: self._pick_color("background_color", self.bg_swatch, self.bg_color_label))

        self.bg_color_label = ctk.CTkLabel(
            self.bg_details_frame, text=getattr(style, 'background_color', '#000000'),
            font=ctk.CTkFont(family=FONTS["mono_small"][0], size=FONTS["mono_small"][1]),
            text_color=COLORS["text_secondary"], width=64,
        )
        self.bg_color_label.grid(row=0, column=1, sticky="w", pady=(0, SPACING["xs"]))

        opacity_frame = ctk.CTkFrame(self.bg_details_frame, fg_color="transparent")
        opacity_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        opacity_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            opacity_frame, text="Opacity:",
            font=ctk.CTkFont(family=ff, size=FONTS["caption"][1]),
            text_color=COLORS["text_muted"],
        ).grid(row=0, column=0, padx=(0, SPACING["xs"]))

        self.bg_opacity_slider = ctk.CTkSlider(
            opacity_frame, from_=0.0, to=1.0, number_of_steps=20,
            progress_color=COLORS["accent"], button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"], fg_color=COLORS["progress_bg"],
            command=self._on_background_opacity_change,
            height=14,
        )
        self.bg_opacity_slider.set(style.background_opacity)
        self.bg_opacity_slider.grid(row=0, column=1, sticky="ew", padx=(0, SPACING["xs"]))

        self.bg_opacity_label = ctk.CTkLabel(
            opacity_frame,
            text=f"{int(style.background_opacity * 100)}%",
            font=ctk.CTkFont(family=FONTS["mono_small"][0], size=FONTS["mono_small"][1]),
            text_color=COLORS["text_secondary"], width=42,
        )
        self.bg_opacity_label.grid(row=0, column=2)
        row += 1

        # Separator
        row = self._add_separator(row)

        # Position
        row = self._add_label(row, "Position", ff)
        self.position_var = ctk.StringVar(value=style.position.capitalize())
        self.position_seg = ctk.CTkSegmentedButton(
            self, values=["Top", "Center", "Bottom"],
            variable=self.position_var,
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent_hover"],
            command=self._on_position_preset_change,
        )
        self.position_seg.grid(row=row, column=0, sticky="ew",
                                padx=SPACING["lg"], pady=(0, SPACING["sm"]))
        row += 1

        # Absolute vertical position slider (0-100)
        offset_frame = ctk.CTkFrame(self, fg_color="transparent")
        offset_frame.grid(row=row, column=0, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["sm"]))
        offset_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            offset_frame, text="Vertical:",
            font=ctk.CTkFont(family=ff, size=FONTS["caption"][1]),
            text_color=COLORS["text_muted"],
        ).grid(row=0, column=0, padx=(0, SPACING["xs"]))
        self.pos_offset_slider = ctk.CTkSlider(
            offset_frame, from_=0, to=100, number_of_steps=100,
            progress_color=COLORS["accent"], button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"], fg_color=COLORS["progress_bg"],
            command=self._on_pos_offset_change, height=14,
        )
        pos_y = int(getattr(style, 'position_y_percent', self._position_to_percent(getattr(style, 'position', 'bottom'))))
        self.pos_offset_slider.set(pos_y)
        self.pos_offset_slider.grid(row=0, column=1, sticky="ew", padx=SPACING["xs"])
        self.pos_offset_label = ctk.CTkLabel(
            offset_frame,
            text=f"{pos_y}%",
            font=ctk.CTkFont(family=FONTS["mono_small"][0], size=FONTS["mono_small"][1]),
            text_color=COLORS["text_secondary"], width=40,
        )
        self.pos_offset_label.grid(row=0, column=2)
        row += 1

        # Clamp hint (shown when slider hits overlap boundary)
        self.clamp_hint = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(family=ff, size=FONTS["caption"][1]),
            text_color=COLORS["warning"], anchor="w", height=16,
        )
        self.clamp_hint.grid(row=row, column=0, sticky="w", padx=SPACING["lg"])
        self.clamp_hint.grid_remove()  # hidden by default
        row += 1

        # Bilingual Order (only shown for primary column in bilingual mode)
        self.bilingual_order_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.bilingual_order_frame.grid(row=row, column=0, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["xs"]))
        self.bilingual_order_var = ctk.StringVar(value="Original \u2191")
        ctk.CTkLabel(
            self.bilingual_order_frame, text="Bilingual Order:",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1], weight="bold"),
            text_color=COLORS["text_muted"], anchor="w",
        ).pack(side="left", padx=(0, SPACING["sm"]))
        self.bilingual_order_seg = ctk.CTkSegmentedButton(
            self.bilingual_order_frame,
            values=["Original \u2191", "Translation \u2191"],
            variable=self.bilingual_order_var,
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent_hover"],
            command=self._on_bilingual_order_change,
        )
        self.bilingual_order_seg.pack(side="left")
        self.bilingual_order_frame.grid_remove()  # hidden by default

        # Spacer to maintain vertical alignment with sibling column when bilingual order is hidden
        self._bilingual_spacer = ctk.CTkFrame(self, fg_color="transparent", height=28)
        self._bilingual_spacer.grid(row=row, column=0, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["xs"]))
        self._bilingual_spacer.grid_propagate(False)
        self._bilingual_spacer.grid_remove()  # hidden by default
        row += 1

        # Separator
        row = self._add_separator(row)

        # Text width barrier (0-100%)
        row = self._add_label(row, "Text Width", ff)
        width_frame = ctk.CTkFrame(self, fg_color="transparent")
        width_frame.grid(row=row, column=0, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["sm"]))
        width_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            width_frame, text="0",
            font=ctk.CTkFont(family=ff, size=FONTS["caption"][1]),
            text_color=COLORS["text_muted"], width=16,
        ).grid(row=0, column=0)

        self.text_width_slider = ctk.CTkSlider(
            width_frame, from_=0, to=100, number_of_steps=100,
            progress_color=COLORS["accent"], button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"], fg_color=COLORS["progress_bg"],
            command=self._on_text_width_change, height=14,
        )
        self.text_width_slider.set(getattr(style, "text_width_percent", 90))
        self.text_width_slider.grid(row=0, column=1, sticky="ew", padx=SPACING["xs"])
        self.text_width_slider.bind("<ButtonRelease-1>", lambda e: self.state.notify("text_width_release"))
        # Track which column is adjusting text width for the visual guide
        self.text_width_slider.bind("<ButtonPress-1>", lambda e: setattr(self.state, '_active_width_style_key', self.style_key))

        self.text_width_label = ctk.CTkLabel(
            width_frame,
            text=f"{int(getattr(style, 'text_width_percent', 90))}%",
            font=ctk.CTkFont(family=FONTS["mono_small"][0], size=FONTS["mono_small"][1]),
            text_color=COLORS["text_secondary"], width=42,
        )
        self.text_width_label.grid(row=0, column=2)

        ctk.CTkLabel(
            width_frame, text="100",
            font=ctk.CTkFont(family=ff, size=FONTS["caption"][1]),
            text_color=COLORS["text_muted"], width=24,
        ).grid(row=0, column=3)
        row += 1

        # Separator
        row = self._add_separator(row)

        # Shadow
        row = self._add_label(row, "Shadow", ff)
        shadow_frame = ctk.CTkFrame(self, fg_color="transparent")
        shadow_frame.grid(row=row, column=0, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["xs"]))

        self.shadow_switch = ctk.CTkSwitch(
            shadow_frame, text="Enable",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            text_color=COLORS["text_secondary"],
            command=self._on_shadow_toggle,
        )
        self.shadow_switch.grid(row=0, column=0, sticky="w")
        if getattr(style, 'shadow_enabled', False):
            self.shadow_switch.select()

        row += 1

        self.shadow_details_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.shadow_details_frame.grid(row=row, column=0, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["sm"]))
        self.shadow_details_frame.grid_columnconfigure(2, weight=1)

        self.shadow_swatch = tk.Canvas(
            self.shadow_details_frame, width=22, height=22, highlightthickness=0, cursor="hand2",
        )
        self.shadow_swatch.grid(row=0, column=0, padx=(0, SPACING["xs"]), pady=(0, SPACING["xs"]))
        self._draw_swatch(self.shadow_swatch, getattr(style, 'shadow_color', '#000000'))
        self.shadow_swatch.bind("<Button-1>", lambda e: self._pick_color("shadow_color", self.shadow_swatch, self.shadow_color_label))

        self.shadow_color_label = ctk.CTkLabel(
            self.shadow_details_frame, text=getattr(style, 'shadow_color', '#000000'),
            font=ctk.CTkFont(family=FONTS["mono_small"][0], size=FONTS["mono_small"][1]),
            text_color=COLORS["text_secondary"], width=60,
        )
        self.shadow_color_label.grid(row=0, column=1, sticky="w", pady=(0, SPACING["xs"]))
        row += 1

        # Shadow offsets + blur
        shadow_sliders = ctk.CTkFrame(self.shadow_details_frame, fg_color="transparent")
        shadow_sliders.grid(row=1, column=0, columnspan=2, sticky="ew")
        shadow_sliders.grid_columnconfigure(1, weight=1)
        shadow_sliders.grid_columnconfigure(3, weight=1)
        shadow_sliders.grid_columnconfigure(5, weight=1)

        ctk.CTkLabel(shadow_sliders, text="X:", font=ctk.CTkFont(family=ff, size=FONTS["caption"][1]),
                     text_color=COLORS["text_muted"]).grid(row=0, column=0, padx=(0, 2))
        self.shadow_x_slider = ctk.CTkSlider(
            shadow_sliders, from_=0, to=20, number_of_steps=20,
            progress_color=COLORS["accent"], button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"], fg_color=COLORS["progress_bg"],
            command=lambda v: self._update_style(shadow_offset_x=int(v)), height=12,
        )
        self.shadow_x_slider.set(getattr(style, 'shadow_offset_x', 2))
        self.shadow_x_slider.grid(row=0, column=1, sticky="ew", padx=(0, SPACING["sm"]))

        ctk.CTkLabel(shadow_sliders, text="Y:", font=ctk.CTkFont(family=ff, size=FONTS["caption"][1]),
                     text_color=COLORS["text_muted"]).grid(row=0, column=2, padx=(0, 2))
        self.shadow_y_slider = ctk.CTkSlider(
            shadow_sliders, from_=0, to=20, number_of_steps=20,
            progress_color=COLORS["accent"], button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"], fg_color=COLORS["progress_bg"],
            command=lambda v: self._update_style(shadow_offset_y=int(v)), height=12,
        )
        self.shadow_y_slider.set(getattr(style, 'shadow_offset_y', 2))
        self.shadow_y_slider.grid(row=0, column=3, sticky="ew", padx=(0, SPACING["sm"]))

        ctk.CTkLabel(shadow_sliders, text="Blur:", font=ctk.CTkFont(family=ff, size=FONTS["caption"][1]),
                     text_color=COLORS["text_muted"]).grid(row=0, column=4, padx=(0, 2))
        self.shadow_blur_slider = ctk.CTkSlider(
            shadow_sliders, from_=0, to=20, number_of_steps=20,
            progress_color=COLORS["accent"], button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"], fg_color=COLORS["progress_bg"],
            command=lambda v: self._update_style(shadow_blur=int(v)), height=12,
        )
        self.shadow_blur_slider.set(getattr(style, 'shadow_blur', 0))
        self.shadow_blur_slider.grid(row=0, column=5, sticky="ew")
        row += 1

        # Separator
        row = self._add_separator(row)

        # Glow
        row = self._add_label(row, "Glow", ff)
        glow_frame = ctk.CTkFrame(self, fg_color="transparent")
        glow_frame.grid(row=row, column=0, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["xs"]))

        self.glow_switch = ctk.CTkSwitch(
            glow_frame, text="Enable",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            text_color=COLORS["text_secondary"],
            command=self._on_glow_toggle,
        )
        self.glow_switch.grid(row=0, column=0, sticky="w")
        if getattr(style, 'glow_enabled', False):
            self.glow_switch.select()

        self.glow_note_label = ctk.CTkLabel(
            glow_frame,
            text="Glow can look a little less obvious in burned video than in preview.",
            font=ctk.CTkFont(family=ff, size=FONTS["caption"][1]),
            text_color=COLORS["text_muted"],
            anchor="w",
            justify="left",
            wraplength=520,
        )
        self.glow_note_label.grid(row=1, column=0, sticky="ew", pady=(SPACING["xs"], 0))
        glow_frame.bind(
            "<Configure>",
            lambda event, label=self.glow_note_label: label.configure(wraplength=max(240, event.width - 8)),
        )

        row += 1

        self.glow_details_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.glow_details_frame.grid(row=row, column=0, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["lg"]))
        self.glow_details_frame.grid_columnconfigure(2, weight=1)

        self.glow_swatch = tk.Canvas(
            self.glow_details_frame, width=22, height=22, highlightthickness=0, cursor="hand2",
        )
        self.glow_swatch.grid(row=0, column=0, padx=(0, SPACING["xs"]), pady=(0, SPACING["xs"]))
        self._draw_swatch(self.glow_swatch, getattr(style, 'glow_color', '#FFFFFF'))
        self.glow_swatch.bind("<Button-1>", lambda e: self._pick_color("glow_color", self.glow_swatch, self.glow_color_label))

        self.glow_color_label = ctk.CTkLabel(
            self.glow_details_frame, text=getattr(style, 'glow_color', '#FFFFFF'),
            font=ctk.CTkFont(family=FONTS["mono_small"][0], size=FONTS["mono_small"][1]),
            text_color=COLORS["text_secondary"], width=60,
        )
        self.glow_color_label.grid(row=0, column=1, sticky="w", pady=(0, SPACING["xs"]))
        row += 1

        glow_radius_frame = ctk.CTkFrame(self.glow_details_frame, fg_color="transparent")
        glow_radius_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        glow_radius_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(glow_radius_frame, text="Radius:",
                     font=ctk.CTkFont(family=ff, size=FONTS["caption"][1]),
                     text_color=COLORS["text_muted"]).grid(row=0, column=0, padx=(0, SPACING["xs"]))
        self.glow_radius_slider = ctk.CTkSlider(
            glow_radius_frame, from_=1, to=30, number_of_steps=29,
            progress_color=COLORS["accent"], button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"], fg_color=COLORS["progress_bg"],
            command=self._on_glow_radius_change, height=12,
        )
        self.glow_radius_slider.set(getattr(style, 'glow_radius', 5))
        self.glow_radius_slider.grid(row=0, column=1, sticky="ew", padx=SPACING["xs"])
        self.glow_radius_label = ctk.CTkLabel(
            glow_radius_frame,
            text=str(getattr(style, 'glow_radius', 5)),
            font=ctk.CTkFont(family=FONTS["mono_small"][0], size=FONTS["mono_small"][1]),
            text_color=COLORS["text_secondary"], width=30,
        )
        self.glow_radius_label.grid(row=0, column=2)

        self._toggle_background_details(getattr(style, 'background_enabled', False))
        self._toggle_shadow_details(getattr(style, 'shadow_enabled', False))
        self._toggle_glow_details(getattr(style, 'glow_enabled', False))

    def _get_current_style(self):
        """Return the style object this column should read/write, based on current scope."""
        if self._scope == "line":
            idx = self.state.selected_subtitle_index
            if 0 <= idx < len(self.state.subtitles):
                sub = self.state.subtitles[idx]
                if self.style_key == "primary":
                    return self.state.get_primary_style_for_subtitle(sub)
                return self.state.get_secondary_style_for_subtitle(sub)
        return self.state.primary_style if self.style_key == "primary" else self.state.secondary_style

    def set_scope(self, scope: str, style=None):
        """Switch between 'global' and 'line' scope and optionally refresh widgets."""
        self._scope = scope
        self.refresh_from_style(style)

    def refresh_from_style(self, style=None):
        """Sync all UI controls to match the given style (or current scope style if None)."""
        if style is None:
            style = self._get_current_style()
        self._font_trace_active = False
        self.font_var.set(self._display_label_for_family(style.font_family))
        self._font_trace_active = True
        self.size_slider.set(style.font_size)
        self.size_label.configure(text=str(style.font_size))
        self._draw_swatch(self.color_swatch, style.primary_color)
        self.color_hex_label.configure(text=style.primary_color)
        self._draw_swatch(self.outline_swatch, style.outline_color)
        self.outline_hex_label.configure(text=style.outline_color)
        self.outline_slider.set(style.outline_thickness)
        if style.bold:
            self.bold_switch.select()
        else:
            self.bold_switch.deselect()
        if style.italic:
            self.italic_switch.select()
        else:
            self.italic_switch.deselect()
        if style.background_enabled:
            self.bg_switch.select()
        else:
            self.bg_switch.deselect()
        self._draw_swatch(self.bg_swatch, getattr(style, 'background_color', '#000000'))
        self.bg_color_label.configure(text=getattr(style, 'background_color', '#000000'))
        self.bg_opacity_slider.set(style.background_opacity)
        self.bg_opacity_label.configure(text=f"{int(style.background_opacity * 100)}%")
        self._toggle_background_details(style.background_enabled)
        self.position_var.set(style.position.capitalize())
        pos_y = int(getattr(style, 'position_y_percent', self._position_to_percent(getattr(style, 'position', 'bottom'))))
        self.pos_offset_slider.set(pos_y)
        self.pos_offset_label.configure(text=f"{pos_y}%")
        width_pct = int(getattr(style, 'text_width_percent', 90))
        self.text_width_slider.set(width_pct)
        self.text_width_label.configure(text=f"{width_pct}%")
        self._draw_swatch(self.shadow_swatch, getattr(style, 'shadow_color', '#000000'))
        self.shadow_color_label.configure(text=getattr(style, 'shadow_color', '#000000'))
        self.shadow_x_slider.set(getattr(style, 'shadow_offset_x', 2))
        self.shadow_y_slider.set(getattr(style, 'shadow_offset_y', 2))
        self.shadow_blur_slider.set(getattr(style, 'shadow_blur', 0))
        if getattr(style, 'shadow_enabled', False):
            self.shadow_switch.select()
        else:
            self.shadow_switch.deselect()
        self._toggle_shadow_details(getattr(style, 'shadow_enabled', False))
        self._draw_swatch(self.glow_swatch, getattr(style, 'glow_color', '#FFFFFF'))
        self.glow_color_label.configure(text=getattr(style, 'glow_color', '#FFFFFF'))
        self.glow_radius_slider.set(getattr(style, 'glow_radius', 5))
        self.glow_radius_label.configure(text=str(getattr(style, 'glow_radius', 5)))
        if getattr(style, 'glow_enabled', False):
            self.glow_switch.select()
        else:
            self.glow_switch.deselect()
        self._toggle_glow_details(getattr(style, 'glow_enabled', False))
        self._apply_position_constraints()

    def _add_label(self, row, text, ff=None):
        if ff is None:
            ff = get_font_family()
        ctk.CTkLabel(
            self, text=text,
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1], weight="bold"),
            text_color=COLORS["text_muted"],
            anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=SPACING["lg"], pady=(SPACING["xs"], SPACING["xxs"]))
        return row + 1

    def _add_separator(self, row):
        ctk.CTkFrame(
            self, fg_color=COLORS["border_subtle"], height=1,
        ).grid(row=row, column=0, sticky="ew", padx=SPACING["lg"], pady=SPACING["xs"])
        return row + 1

    def _draw_swatch(self, canvas, color):
        canvas.delete("all")
        canvas.create_oval(2, 2, 22, 22, fill=color, outline=color, width=1)
        is_dark = ctk.get_appearance_mode().lower() == "dark"
        border = COLORS["border"][1] if is_dark else COLORS["border"][0]
        canvas.create_oval(2, 2, 22, 22, outline=border, width=1)
        bg = COLORS["bg_secondary"][1] if is_dark else COLORS["bg_secondary"][0]
        canvas.configure(bg=bg)

    def _on_size_change(self, value):
        size = int(value)
        self.size_label.configure(text=str(size))
        self._update_style(font_size=size)

    def _on_outline_change(self, value):
        self._update_style(outline_thickness=int(value))

    def _on_background_toggle(self):
        enabled = bool(self.bg_switch.get())
        self._toggle_background_details(enabled)
        self._update_style(background_enabled=enabled)

    def _on_background_opacity_change(self, value):
        opacity = round(float(value), 2)
        self.bg_opacity_label.configure(text=f"{int(opacity * 100)}%")
        self._update_style(background_opacity=opacity)

    def _toggle_background_details(self, visible: bool):
        if visible:
            self.bg_details_frame.grid()
        else:
            self.bg_details_frame.grid_remove()

    def _on_pos_offset_change(self, value):
        v = int(round(float(value)))
        constrained = self._constrain_position_percent(v)
        if constrained != v:
            self.pos_offset_slider.set(constrained)
            self._show_clamp_hint("Use Bilingual Order to swap order.")
        v = constrained
        self.pos_offset_label.configure(text=f"{v}%")
        self._update_style(position_y_percent=v)

    def _show_clamp_hint(self, text):
        """Show a clamp hint below this column's position slider."""
        self.clamp_hint.configure(text=text)
        self.clamp_hint.grid()
        # Cancel any pending hide so rapid drags reset the timer
        if hasattr(self, '_clamp_hint_after_id') and self._clamp_hint_after_id is not None:
            try:
                self.clamp_hint.after_cancel(self._clamp_hint_after_id)
            except Exception:
                pass
        self._clamp_hint_after_id = self.clamp_hint.after(7000, self._hide_clamp_hint)

    def _hide_clamp_hint(self):
        self.clamp_hint.configure(text="")
        self.clamp_hint.grid_remove()
        self._clamp_hint_after_id = None

    def show_bilingual_order(self, visible: bool, swapped: bool = False):
        """Show or hide the Bilingual Order control (primary column only)."""
        if visible:
            self.bilingual_order_frame.grid()
            self._bilingual_spacer.grid_remove()
            self.bilingual_order_var.set("Translation \u2191" if swapped else "Original \u2191")
        else:
            self.bilingual_order_frame.grid_remove()
            self._bilingual_spacer.grid_remove()

    def show_bilingual_spacer(self, visible: bool):
        """Show spacer to align rows with the sibling column's bilingual order control."""
        if visible:
            self._bilingual_spacer.grid()
            self.bilingual_order_frame.grid_remove()
        else:
            self._bilingual_spacer.grid_remove()

    def _on_bilingual_order_change(self, value):
        want_swapped = (value == "Translation \u2191")
        if want_swapped != getattr(self.state, "position_swapped", False):
            self.state.toggle_position_swap()
        self.refresh_from_style()
        if self._sibling is not None:
            self._sibling.refresh_from_style()
            self._sibling._hide_clamp_hint()
        self._hide_clamp_hint()

    def _apply_position_constraints(self):
        """Disable impossible preset combinations based on current slot order."""
        if self._sibling is None:
            return

        for preset in ("top", "center", "bottom"):
            btn = self.position_seg._buttons_dict.get(preset.capitalize())
            if btn is None:
                continue
            btn.configure(state="normal" if self._is_position_allowed(preset) else "disabled")

    @staticmethod
    def _position_to_percent(position: str) -> int:
        return {"top": 15, "center": 50, "bottom": 85}.get((position or "bottom").lower(), 85)

    @staticmethod
    def _position_rank(position: str) -> int:
        return {"top": 0, "center": 1, "bottom": 2}.get((position or "bottom").lower(), 2)

    def _ordered_columns(self):
        if self._sibling is None:
            return self, None
        swapped = getattr(self.state, "position_swapped", False)
        primary_col = self if self.style_key == "primary" else self._sibling
        secondary_col = self._sibling if self.style_key == "primary" else self
        if swapped:
            return secondary_col, primary_col
        return primary_col, secondary_col

    def _is_position_allowed(self, candidate_position: str) -> bool:
        if not self.state.bilingual or self._sibling is None:
            return True

        upper_col, lower_col = self._ordered_columns()
        other_col = self._sibling
        other_position = other_col.position_var.get().lower()
        candidate_rank = self._position_rank(candidate_position)
        other_rank = self._position_rank(other_position)

        if self is upper_col:
            return candidate_rank <= other_rank
        if self is lower_col:
            return candidate_rank >= other_rank
        return True

    def _constrain_position_percent(self, candidate_percent: int) -> int:
        candidate_percent = max(0, min(100, int(candidate_percent)))
        if not self.state.bilingual or self._sibling is None:
            return candidate_percent

        upper_col, lower_col = self._ordered_columns()
        other_style = self._sibling._get_current_style()
        other_percent = int(getattr(other_style, "position_y_percent", self._position_to_percent(other_style.position)))

        if self is upper_col:
            return min(candidate_percent, other_percent)
        if self is lower_col:
            return max(candidate_percent, other_percent)
        return candidate_percent

    def _sync_both_for_overlap(self, position: str):
        """When both presets match, nudge so the anchor item (i=0) gets default-1%
        and the follower (i=1, top-anchored) gets default+1%.

        When swapped, secondary is the anchor (i=0), so it gets the lower value.
        """
        if self._sibling is None:
            return
        default_y = self._position_to_percent(position)
        swapped = getattr(self.state, "position_swapped", False)
        if swapped:
            pri_y = min(100, default_y + 1)
            sec_y = max(0, default_y - 1)
        else:
            pri_y = max(0, default_y - 1)
            sec_y = min(100, default_y + 1)

        if position == "bottom":
            if swapped:
                pri_y = 86
                sec_y = 84
            else:
                pri_y = 84
                sec_y = 86

        pri_col = self if self.style_key == "primary" else self._sibling
        sec_col = self._sibling if self.style_key == "primary" else self

        pri_col.pos_offset_slider.set(pri_y)
        pri_col.pos_offset_label.configure(text=f"{pri_y}%")
        pri_col._update_style(position=position, position_y_percent=pri_y)

        sec_col.pos_offset_slider.set(sec_y)
        sec_col.pos_offset_label.configure(text=f"{sec_y}%")
        sec_col._update_style(position=position, position_y_percent=sec_y)

    def _on_position_preset_change(self, value):
        position = (value or "Bottom").lower()
        if not self._is_position_allowed(position):
            current = self.position_var.get().lower()
            self.position_var.set(current.capitalize())
            self._show_clamp_hint("Use Bilingual Order to swap order.")
            self._apply_position_constraints()
            if self._sibling is not None:
                self._sibling._apply_position_constraints()
            return
        pos_y = self._position_to_percent(position)
        self.pos_offset_slider.set(pos_y)
        self.pos_offset_label.configure(text=f"{pos_y}%")
        self._update_style(position=position, position_y_percent=pos_y)
        # Update preset constraints on both columns
        self._apply_position_constraints()
        if self._sibling is not None:
            self._sibling._apply_position_constraints()
            # Auto-nudge both when presets collide (symmetric — fires from either side)
            if self._sibling.position_var.get().lower() == position:
                self._sync_both_for_overlap(position)

    def _on_font_var_change(self, *_args):
        """Trace callback for font_var — fires on dropdown selection AND typed input."""
        if not self._font_trace_active:
            return
        value = self.font_var.get()
        if value:
            family = resolve_font_family_name(value)
            if not family:
                return
            display_value = self._display_label_for_family(family)
            if display_value and display_value != value:
                self._font_trace_active = False
                self.font_var.set(display_value)
                self._font_trace_active = True
            self._update_style(font_family=family)

    def _reload_font_dropdown(self, force_refresh: bool = False):
        entries = get_font_dropdown_entries(force_refresh=force_refresh)
        self._font_label_to_family = {}
        self._font_family_to_label = {}

        if entries:
            values = []
            for entry in entries:
                label = entry.get("label", "")
                family = entry.get("canonical_name", "")
                if not label or not family:
                    continue
                values.append(label)
                self._font_label_to_family[label] = family
                self._font_family_to_label[family.casefold()] = label
        else:
            values = sorted(
                {f.strip() for f in tkfont.families() if f and not f.startswith("@")},
                key=str.casefold,
            )
            self._font_label_to_family = {value: value for value in values}
            self._font_family_to_label = {value.casefold(): value for value in values}

        self.font_dropdown.configure(values=values or [self.font_var.get() or "Arial"])

    def _display_label_for_family(self, family: str) -> str:
        resolved = resolve_font_family_name(family)
        if not resolved:
            return family
        return self._font_family_to_label.get(resolved.casefold(), get_font_display_label(resolved) or resolved)

    def _set_font_refresh_state(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.refresh_fonts_btn.configure(state=state)
        if self._sibling is not None:
            self._sibling.refresh_fonts_btn.configure(state=state)

    def _on_refresh_fonts(self):
        self._set_font_refresh_state(False)
        try:
            refresh_font_catalog()
            self._reload_font_dropdown()
            self.refresh_from_style()
            if self._sibling is not None:
                self._sibling._reload_font_dropdown()
                self._sibling.refresh_from_style()
        finally:
            self._set_font_refresh_state(True)

    def _on_text_width_change(self, value):
        v = int(round(float(value)))
        self.text_width_label.configure(text=f"{v}%")
        self._update_style(text_width_percent=v)

    def _on_glow_radius_change(self, value):
        v = int(value)
        self.glow_radius_label.configure(text=str(v))
        self._update_style(glow_radius=v)

    def _on_shadow_toggle(self):
        enabled = bool(self.shadow_switch.get())
        self._toggle_shadow_details(enabled)
        self._update_style(shadow_enabled=enabled)

    def _toggle_shadow_details(self, visible: bool):
        if visible:
            self.shadow_details_frame.grid()
        else:
            self.shadow_details_frame.grid_remove()

    def _on_glow_toggle(self):
        enabled = bool(self.glow_switch.get())
        self._toggle_glow_details(enabled)
        self._update_style(glow_enabled=enabled)

    def _toggle_glow_details(self, visible: bool):
        if visible:
            self.glow_details_frame.grid()
        else:
            self.glow_details_frame.grid_remove()

    def _pick_color(self, attr, swatch_canvas, hex_label):
        style = self._get_current_style()
        current = getattr(style, attr)
        result = colorchooser.askcolor(color=current, title=f"Choose {attr.replace('_', ' ').title()}")
        if result[1]:
            hex_color = result[1]
            self._draw_swatch(swatch_canvas, hex_color)
            hex_label.configure(text=hex_color)
            self._update_style(**{attr: hex_color})

    def _update_style(self, **kwargs):
        if self._scope == "line":
            import copy
            idx = self.state.selected_subtitle_index
            if 0 <= idx < len(self.state.subtitles):
                sub = self.state.subtitles[idx]
                if self.style_key == "primary":
                    attr = "primary_style_override"
                    fallback = self.state.get_primary_style_for_subtitle(sub)
                else:
                    attr = "secondary_style_override"
                    fallback = self.state.get_secondary_style_for_subtitle(sub)
                if getattr(sub, attr, None) is None:
                    setattr(sub, attr, copy.deepcopy(fallback))
                target = getattr(sub, attr)
                for k, v in kwargs.items():
                    if hasattr(target, k):
                        setattr(target, k, v)
                self.state.notify("subtitles_edited")
                self.state.notify("style")
                if "text_width_percent" in kwargs:
                    self.state.notify("text_width_percent")
        elif self.style_key == "primary":
            self.state.update_primary_style(**kwargs)
            if "text_width_percent" in kwargs:
                self.state.notify("text_width_percent")
        else:
            self.state.update_secondary_style(**kwargs)
            if "text_width_percent" in kwargs:
                self.state.notify("text_width_percent")

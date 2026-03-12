import customtkinter as ctk
import tkinter as tk

from PIL import Image, ImageDraw

from app.theme import COLORS, FONTS, SIDEBAR, STEPS, SPACING, RADIUS, IconRenderer, get_font_family


class Sidebar(ctk.CTkFrame):
    def __init__(self, parent, state, **kwargs):
        super().__init__(parent, fg_color=COLORS["sidebar_bg"], corner_radius=0, **kwargs)
        self.state = state
        self.expanded = True
        self.target_width = SIDEBAR["expanded_width"]
        self.step_canvases = []
        self.connector_canvases = []
        self.step_labels = []
        self.desc_labels = []
        self._animating = False
        self._completed_steps = set()
        self._labels_visible = True

        self.grid_columnconfigure(0, weight=1)

        # Brand area
        self.brand_frame = ctk.CTkFrame(self, fg_color="transparent", height=52)
        self.brand_frame.grid(row=0, column=0, sticky="ew", padx=SPACING["sm"], pady=(SPACING["md"], SPACING["xs"]))
        self.brand_frame.grid_columnconfigure(2, weight=1)

        self.toggle_btn = ctk.CTkButton(
            self.brand_frame,
            text="\u2630",
            width=36, height=36,
            fg_color="transparent",
            hover_color=COLORS["sidebar_hover"],
            text_color=COLORS["text_primary"],
            font=ctk.CTkFont(size=18),
            corner_radius=RADIUS["md"],
            command=self.toggle_collapse,
        )
        self.toggle_btn.grid(row=0, column=0, sticky="w")

        ff = get_font_family()
        self._brand_logo = self._build_brand_logo()
        self.brand_logo = ctk.CTkLabel(
            self.brand_frame,
            text="",
            image=self._brand_logo,
            width=32,
            height=32,
        )
        self.brand_logo.grid(row=0, column=1, sticky="w", padx=(0, SPACING["xs"]))

        self.brand_inner = ctk.CTkFrame(self.brand_frame, fg_color="transparent")
        self.brand_inner.grid(row=0, column=2, sticky="w")

        self.title_label = ctk.CTkLabel(
            self.brand_inner,
            text="SubVela",
            font=ctk.CTkFont(family=ff, size=FONTS["brand"][1], weight="bold"),
            text_color=COLORS["text_heading"],
        )
        self.title_label.grid(row=0, column=0, sticky="w")

        # Separator
        self.separator = ctk.CTkFrame(self, fg_color=COLORS["border_subtle"], height=1)
        self.separator.grid(row=1, column=0, sticky="ew", padx=SPACING["lg"], pady=(SPACING["xs"], SPACING["sm"]))

        # Steps frame
        self.steps_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.steps_frame.grid(row=2, column=0, sticky="new", padx=SPACING["sm"], pady=SPACING["xs"])
        self.steps_frame.grid_columnconfigure(1, weight=1)

        grid_row = 0
        ind_size = SIDEBAR["step_indicator_size"]

        for i, step in enumerate(STEPS):
            # Step indicator canvas
            canvas = tk.Canvas(
                self.steps_frame,
                width=ind_size, height=ind_size,
                highlightthickness=0, cursor="hand2",
            )
            canvas.grid(row=grid_row, column=0, padx=(SPACING["sm"], SPACING["sm"]), pady=(SPACING["xs"], 0))
            canvas.bind("<Button-1>", lambda e, idx=i: self._on_step_click(idx))
            self.step_canvases.append(canvas)

            # Step label + description container
            label_frame = ctk.CTkFrame(self.steps_frame, fg_color="transparent", cursor="hand2")
            label_frame.grid(row=grid_row, column=1, sticky="w", pady=(SPACING["xs"], 0))
            label_frame.bind("<Button-1>", lambda e, idx=i: self._on_step_click(idx))

            text_label = ctk.CTkLabel(
                label_frame,
                text=step["label"],
                font=ctk.CTkFont(family=ff, size=FONTS["sidebar_label"][1], weight="bold"),
                text_color=COLORS["text_primary"],
                anchor="w",
            )
            text_label.grid(row=0, column=0, sticky="w")
            text_label.bind("<Button-1>", lambda e, idx=i: self._on_step_click(idx))

            desc_label = ctk.CTkLabel(
                label_frame,
                text=step["description"],
                font=ctk.CTkFont(family=ff, size=FONTS["sidebar_label_small"][1]),
                text_color=COLORS["text_muted"],
                anchor="w",
            )
            desc_label.grid(row=1, column=0, sticky="w")
            desc_label.bind("<Button-1>", lambda e, idx=i: self._on_step_click(idx))

            self.step_labels.append(text_label)
            self.desc_labels.append(desc_label)

            # Hover bindings on step row
            for widget in (canvas, label_frame, text_label, desc_label):
                widget.bind("<Enter>", lambda e, idx=i: self._on_hover(idx, True))
                widget.bind("<Leave>", lambda e, idx=i: self._on_hover(idx, False))

            grid_row += 1

            # Connector line between steps (except after last)
            if i < len(STEPS) - 1:
                conn = tk.Canvas(
                    self.steps_frame,
                    width=ind_size, height=14,
                    highlightthickness=0,
                )
                conn.grid(row=grid_row, column=0, padx=(SPACING["sm"], SPACING["sm"]))
                self.connector_canvases.append(conn)
                grid_row += 1

        # Spacer
        spacer = ctk.CTkFrame(self, fg_color="transparent")
        spacer.grid(row=3, column=0, sticky="nsew")
        self.grid_rowconfigure(3, weight=1)

        # Settings gear button
        self.settings_btn = ctk.CTkButton(
            self, text="⚙  Settings",
            font=ctk.CTkFont(family=ff, size=FONTS["sidebar_label"][1]),
            fg_color="transparent",
            hover_color=COLORS["sidebar_hover"],
            text_color=COLORS["text_secondary"],
            anchor="w", height=36,
            corner_radius=RADIUS["md"],
            cursor="hand2",
            command=self._on_settings_click,
        )
        self.settings_btn.grid(row=4, column=0, sticky="ew", padx=SPACING["sm"], pady=(0, SPACING["xs"]))

        # Theme toggle at bottom
        self.theme_frame = ctk.CTkFrame(self, fg_color="transparent", height=48)
        self.theme_frame.grid(row=5, column=0, sticky="ew", padx=SPACING["sm"], pady=SPACING["md"])
        self.theme_frame.grid_columnconfigure(1, weight=1)

        # Pillow sun/moon icon
        self._theme_icon_sun = IconRenderer.get("sun", 18)
        self._theme_icon_moon = IconRenderer.get("moon", 18)
        is_dark = ctk.get_appearance_mode() == "Dark"

        self.theme_icon = ctk.CTkLabel(
            self.theme_frame,
            text="",
            image=self._theme_icon_moon if is_dark else self._theme_icon_sun,
            width=36, height=36,
        )
        self.theme_icon.grid(row=0, column=0, padx=(SPACING["xs"], SPACING["sm"]))

        self.theme_switch = ctk.CTkSwitch(
            self.theme_frame,
            text="Dark",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1]),
            text_color=COLORS["text_secondary"],
            command=self._toggle_theme,
            width=40,
            onvalue=1, offvalue=0,
        )
        self.theme_switch.grid(row=0, column=1, sticky="w")
        if is_dark:
            self.theme_switch.select()

        # Initial draw
        self._update_all_indicators()

        # Listen to state
        self.state.add_listener(self._on_state_change)

    def _on_step_click(self, index):
        self.state.set_step(index)

    def _on_settings_click(self):
        self.state.set_step(4)

    def _on_hover(self, index, entering):
        if index == self.state.current_step:
            return
        # Light up the canvas bg on hover
        canvas = self.step_canvases[index]
        if entering:
            bg = self._resolve_color(COLORS["sidebar_hover"])
            canvas.configure(bg=bg)
        else:
            bg = self._resolve_color(COLORS["sidebar_bg"])
            canvas.configure(bg=bg)

    def _get_completed_steps(self) -> set:
        completed = set()
        # Step 0 (Import): completed when video is loaded
        if self.state.video_path:
            completed.add(0)
        # Step 1 (Transcribe): completed when subtitles exist
        if self.state.subtitles:
            completed.add(1)
        # Step 2 (Style): considered completed if subtitles exist (always styled)
        if self.state.subtitles:
            completed.add(2)
        return completed

    def _update_all_indicators(self):
        self._completed_steps = self._get_completed_steps()
        is_dark = ctk.get_appearance_mode().lower() == "dark"
        ind_size = SIDEBAR["step_indicator_size"]
        sidebar_bg = self._resolve_color(COLORS["sidebar_bg"])

        for i, step in enumerate(STEPS):
            canvas = self.step_canvases[i]
            canvas.configure(bg=sidebar_bg)
            canvas.delete("all")

            cx, cy = ind_size // 2, ind_size // 2
            r = ind_size // 2 - 2

            if i in self._completed_steps and i != self.state.current_step:
                # Completed: green filled circle with checkmark
                fill = self._resolve_color(COLORS["step_completed"])
                canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=fill, outline="")
                # Draw checkmark
                canvas.create_line(
                    cx - r // 3, cy,
                    cx - r // 8, cy + r // 3,
                    cx + r // 3, cy - r // 4,
                    fill="white", width=2, smooth=False,
                )
            elif i == self.state.current_step:
                # Active: blue filled circle with white number
                fill = self._resolve_color(COLORS["step_active"])
                canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=fill, outline="")
                ff = get_font_family()
                canvas.create_text(cx, cy, text=str(step["number"]),
                                   fill="white", font=(ff, 10, "bold"))
            else:
                # Pending: hollow circle with number
                outline_color = self._resolve_color(COLORS["step_pending"])
                text_color = self._resolve_color(COLORS["text_muted"])
                canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                   outline=outline_color, width=2, fill="")
                ff = get_font_family()
                canvas.create_text(cx, cy, text=str(step["number"]),
                                   fill=text_color, font=(ff, 10))

            # Update label colors
            if i == self.state.current_step:
                self.step_labels[i].configure(text_color=COLORS["accent"])
            elif i in self._completed_steps:
                self.step_labels[i].configure(text_color=COLORS["step_completed"])
            else:
                self.step_labels[i].configure(text_color=COLORS["text_primary"])

        # Draw connector lines
        line_color = self._resolve_color(COLORS["step_line"])
        for j, conn in enumerate(self.connector_canvases):
            conn.configure(bg=sidebar_bg)
            conn.delete("all")
            cx = ind_size // 2
            # Use completed color if step above is completed
            if j in self._completed_steps:
                c = self._resolve_color(COLORS["step_completed"])
            else:
                c = line_color
            conn.create_line(cx, 0, cx, 14, fill=c, width=2)

    def _on_state_change(self, field):
        if field == "step":
            self._update_all_indicators()
            is_settings = self.state.current_step == 4
            self.settings_btn.configure(
                fg_color=COLORS["sidebar_active"] if is_settings else "transparent",
                text_color=COLORS["sidebar_icon_active"] if is_settings else COLORS["text_secondary"],
            )
        elif field in ("video", "subtitles"):
            self._update_all_indicators()

    def toggle_collapse(self):
        if self._animating:
            return
        self.expanded = not self.expanded
        self._animating = True

        if self.expanded:
            self._animate_width(SIDEBAR["collapsed_width"], SIDEBAR["expanded_width"])
        else:
            self._animate_width(SIDEBAR["expanded_width"], SIDEBAR["collapsed_width"])

    def _animate_width(self, from_w, to_w):
        steps = SIDEBAR["animation_steps"]
        step_size = (to_w - from_w) / steps
        self._anim_step(from_w, step_size, 0, steps, to_w)

    def _anim_step(self, current, step_size, count, total, target):
        if count >= total:
            self._apply_width(target)
            self._animating = False
            return
        w = int(current + step_size)
        self._apply_width(w)
        self.after(SIDEBAR["animation_delay_ms"],
                   lambda: self._anim_step(w, step_size, count + 1, total, target))

    def _apply_width(self, width):
        self.configure(width=width)
        show_labels = width > SIDEBAR["collapsed_width"] + 20
        if show_labels != self._labels_visible:
            self._labels_visible = show_labels
            for lbl in self.step_labels:
                if show_labels:
                    lbl.grid()
                else:
                    lbl.grid_remove()
            for desc in self.desc_labels:
                if show_labels:
                    desc.grid()
                else:
                    desc.grid_remove()
            if show_labels:
                self.brand_inner.grid()
                self.theme_switch.grid()
                self.separator.grid()
                self.settings_btn.configure(text="⚙  Settings")
            else:
                self.brand_inner.grid_remove()
                self.theme_switch.grid_remove()
                self.separator.grid_remove()
                self.settings_btn.configure(text="⚙")

    def _toggle_theme(self):
        mode = "Dark" if self.theme_switch.get() else "Light"
        ctk.set_appearance_mode(mode)
        is_dark = mode == "Dark"
        self.theme_icon.configure(image=self._theme_icon_moon if is_dark else self._theme_icon_sun)
        self.theme_switch.configure(text=mode)
        # Refresh indicators after theme change
        self.after(50, self._update_all_indicators)
        # Notify listeners (app.py uses this to update PanedWindow)
        self.state.notify("theme")

    def _resolve_color(self, color_tuple) -> str:
        if isinstance(color_tuple, tuple):
            is_dark = ctk.get_appearance_mode().lower() == "dark"
            return color_tuple[1] if is_dark else color_tuple[0]
        return color_tuple

    def _build_brand_logo(self):
        target_size = 32
        render_size = 96
        scale = render_size / 400.0
        image = Image.new("RGBA", (render_size, render_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image, "RGBA")

        def point(x: float, y: float) -> tuple[int, int]:
            return (round(x * scale), round(y * scale))

        draw.polygon(
            [point(170, 108), point(170, 212), point(258, 160)],
            fill=(96, 165, 250, round(255 * 0.4)),
        )
        draw.rounded_rectangle(
            (point(112, 238), point(288, 248)),
            radius=round(5 * scale),
            fill=(96, 165, 250, round(255 * 0.8)),
        )
        draw.rounded_rectangle(
            (point(140, 262), point(260, 270)),
            radius=round(4 * scale),
            fill=(59, 130, 246, round(255 * 0.4)),
        )

        logo_image = image.resize((target_size, target_size), Image.LANCZOS)
        return ctk.CTkImage(light_image=logo_image, dark_image=logo_image, size=(target_size, target_size))

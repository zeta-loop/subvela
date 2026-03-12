import customtkinter as ctk
import tkinter as tk
from tkinter import font as tkfont
from tkinter import colorchooser
from app.theme import COLORS, FONTS, SPACING, RADIUS, get_font_family
from core.subtitle_model import remap_word_timestamps, SubtitleStyle


class SubtitleList(ctk.CTkFrame):
    INDEX_W = 30
    TIME_W = 100
    DOT_W = 20
    TIME_RIGHT_PAD = 6
    ORIGINAL_LEFT_PAD = 8
    ORIGINAL_RIGHT_PAD = 8

    def __init__(self, parent, state, **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_secondary"], corner_radius=0, **kwargs)
        self.state = state
        self.rows = []
        self._active_editor = None
        self._font_lookup = self._build_font_lookup()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ff = get_font_family()

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent", height=40)
        header.grid(row=0, column=0, sticky="ew", padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"]))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header, text="Subtitles",
            font=ctk.CTkFont(family=ff, size=FONTS["subheading"][1], weight="bold"),
            text_color=COLORS["text_heading"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self.count_label = ctk.CTkLabel(
            header, text="0 lines",
            font=ctk.CTkFont(family=ff, size=FONTS["caption"][1]),
            text_color=COLORS["text_muted"],
        )
        self.count_label.grid(row=0, column=1, sticky="e")

        # Column headers with background bar
        self.col_header = ctk.CTkFrame(self, fg_color=COLORS["bg_tertiary"], height=28,
                                   corner_radius=0)
        self.col_header.grid(row=1, column=0, sticky="ew", padx=SPACING["sm"])
        self._build_column_headers()

        # Scrollable list
        self.scroll_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORS["bg_secondary"],
            scrollbar_button_color=COLORS["scrollbar"],
            scrollbar_button_hover_color=COLORS["scrollbar_hover"],
        )
        self.scroll_frame.grid(row=2, column=0, sticky="nsew", padx=SPACING["sm"], pady=(SPACING["xs"], SPACING["sm"]))
        self.scroll_frame.grid_columnconfigure(0, weight=1)

        # Sync header width to scroll content area (accounts for scrollbar + internal padding).
        # Bind to inner frame Configure so it re-syncs on every resize.
        self.scroll_frame._parent_frame.bind("<Configure>", self._sync_header_width, add="+")
        self.after(150, self._sync_header_width)

        # Hover hint — placed as overlay so it never shifts layout
        self.hint_label = ctk.CTkLabel(
            self, text="✎  Double-click a cell to edit",
            font=ctk.CTkFont(family=ff, size=FONTS["small"][1], weight="bold"),
            text_color=COLORS["accent"],
            fg_color=COLORS["bg_tertiary"],
            corner_radius=RADIUS["xs"],
            anchor="w",
        )
        # Not placed yet; shown via place(), hidden via place_forget()

        # Listen to state
        self.state.add_listener(self._on_state_change)

    @staticmethod
    def _build_font_lookup() -> dict[str, str]:
        try:
            return {name.lower(): name for name in tkfont.families()}
        except Exception:
            return {}

    @staticmethod
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

    @staticmethod
    def _is_likely_cjk_family(family: str) -> bool:
        name = (family or "").lower()
        cjk_tokens = (
            "yahei", "simhei", "simsun", "msyh", "noto sans cjk", "source han",
            "gothic", "meiryo", "malgun", "pingfang", "heiti", "song", "kai",
        )
        return any(tok in name for tok in cjk_tokens)

    def _pick_text_family(self, text: str, preferred: str | None = None) -> str:
        preferred = preferred or get_font_family()
        if not text:
            return preferred

        # For CJK and other non-Latin scripts, pick broader-coverage UI fonts.
        if self._contains_cjk(text):
            cjk_fallbacks = [
                "Microsoft YaHei UI",
                "Microsoft YaHei",
                "SimHei",
                "SimSun",
                "Yu Gothic UI",
                "Meiryo UI",
                "Segoe UI",
            ]
            if self._is_likely_cjk_family(preferred):
                candidates = [preferred] + cjk_fallbacks
            else:
                candidates = cjk_fallbacks + [preferred]
        elif any(ord(ch) > 0x024F for ch in text):
            candidates = [
                "Segoe UI",
                "Nirmala UI",
                "Leelawadee UI",
                "Arial Unicode MS",
            ]
        else:
            return preferred

        for name in candidates:
            if name.lower() in self._font_lookup:
                return self._font_lookup[name.lower()]
        return preferred

    def _set_clipped_label_text(self, label: tk.Label, text: str):
        full_text = (text or "").strip() or "…"
        setattr(label, "_full_text", full_text)
        self._apply_label_clipping(label)

    def _apply_label_clipping(self, label: tk.Label):
        full_text = getattr(label, "_full_text", "")
        if not getattr(label, "_clip_enabled", False):
            label.configure(text=full_text)
            return

        try:
            width_px = int(label.winfo_width()) - 2
            if width_px <= 8:
                label.configure(text=full_text)
                return

            font_obj = tkfont.Font(font=label.cget("font"))
            if font_obj.measure(full_text) <= width_px:
                label.configure(text=full_text)
                return

            ellipsis = "…"
            ellipsis_w = font_obj.measure(ellipsis)
            if ellipsis_w >= width_px:
                label.configure(text=ellipsis)
                return

            lo, hi = 0, len(full_text)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                candidate = full_text[:mid] + ellipsis
                if font_obj.measure(candidate) <= width_px:
                    lo = mid
                else:
                    hi = mid - 1

            label.configure(text=full_text[:lo] + ellipsis)
        except Exception:
            label.configure(text=full_text)

    def _build_column_headers(self):
        ff = get_font_family()
        for w in self.col_header.winfo_children():
            w.destroy()

        # Reset geometry each rebuild so header and rows stay in lock-step.
        for col in range(8):
            self.col_header.grid_columnconfigure(col, weight=0, minsize=0)

        has_translation = self.state.bilingual and any(s.translated_text for s in self.state.subtitles)

        # (label_text, minsize, weight, left_padx, right_padx)
        # Empty text = no label widget (spacer / dot columns must not add padx noise).
        columns = [
            ("",            2,               0, 0, 0),
            ("#",           self.INDEX_W,    0, 2, 2),
            ("TIME",        self.TIME_W,     0, 2, self.TIME_RIGHT_PAD),
        ]
        columns.append(("ORIGINAL", 0, 1, self.ORIGINAL_LEFT_PAD, self.ORIGINAL_RIGHT_PAD))
        if has_translation:
            columns.append(("TRANSLATION", 0, 1, 2, 2))

        columns.append(("", self.DOT_W, 0, 0, 0))

        for col, (text, min_w, weight, lpad, rpad) in enumerate(columns):
            self.col_header.grid_columnconfigure(col, weight=weight, minsize=min_w)
            if not text:
                continue
            ctk.CTkLabel(
                self.col_header, text=text,
                font=ctk.CTkFont(family=ff, size=FONTS["caption"][1], weight="bold"),
                text_color=COLORS["text_muted"],
                anchor="w",
            ).grid(row=0, column=col, sticky="w", padx=(lpad, rpad))

    def _sync_header_width(self, event=None):
        """Align col_header's padx to exactly match the rows' rendered width."""
        try:
            self.update_idletasks()
            # Use the first row as ground truth — it IS what we need to align with.
            # Fall back to _parent_frame only when no rows exist yet.
            if self.rows:
                ref = self.rows[0][0]
                ref.update_idletasks()
            else:
                ref = self.scroll_frame._parent_frame
            if ref.winfo_width() <= 1:
                return
            left_pad  = ref.winfo_rootx() - self.winfo_rootx()
            right_pad = (self.winfo_rootx() + self.winfo_width()) - (ref.winfo_rootx() + ref.winfo_width())
            if left_pad < 0 or right_pad < 0:
                return
            self.col_header.grid_configure(padx=(left_pad, right_pad))
            self.after(50, self._sync_header_columns)
        except Exception:
            pass

    def _on_state_change(self, field):
        if field == "subtitles":
            self._build_column_headers()
            self._rebuild_list()
        elif field == "selected_subtitle":
            self._update_selection()
        elif field == "bilingual":
            self._build_column_headers()
            self._rebuild_list()
        elif field == "subtitles_edited":
            self._rebuild_list()
        elif field == "theme":
            self._apply_theme()
            self._build_column_headers()
            self._rebuild_list()

    def _apply_theme(self):
        self.configure(fg_color=COLORS["bg_secondary"])
        self.col_header.configure(fg_color=COLORS["bg_tertiary"])
        self.scroll_frame.configure(
            fg_color=COLORS["bg_secondary"],
            scrollbar_button_color=COLORS["scrollbar"],
            scrollbar_button_hover_color=COLORS["scrollbar_hover"],
        )
        self.count_label.configure(text_color=COLORS["text_muted"])
        self.hint_label.configure(
            text_color=COLORS["accent"],
            fg_color=COLORS["bg_tertiary"],
        )

    def _rebuild_list(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.rows = []

        ff = get_font_family()
        subs = self.state.subtitles
        self.count_label.configure(text=f"{len(subs)} lines")

        has_translation = self.state.bilingual and any(s.translated_text for s in subs)

        for i, sub in enumerate(subs):
            row_color = COLORS["row_even"] if i % 2 == 0 else COLORS["row_odd"]
            row_bg = self._resolve_color(row_color)

            # Outer row frame
            row = ctk.CTkFrame(
                self.scroll_frame,
                fg_color=row_color,
                corner_radius=0,
                height=24,
                cursor="hand2",
            )
            row.grid(row=i, column=0, sticky="ew", pady=0)
            row.grid_propagate(False) # Force the height to exactly 24px

            col_idx = 0
            # Configure row columns to match header exactly.
            for col in range(8):
                row.grid_columnconfigure(col, weight=0, minsize=0)
            row.grid_columnconfigure(0, minsize=2)

            cfg_col = 1
            row.grid_columnconfigure(cfg_col, minsize=self.INDEX_W)
            cfg_col += 1
            row.grid_columnconfigure(cfg_col, minsize=self.TIME_W)
            cfg_col += 1
            if has_translation:
                row.grid_columnconfigure(cfg_col, weight=1)
                cfg_col += 1
                row.grid_columnconfigure(cfg_col, weight=1)
                cfg_col += 1
            else:
                row.grid_columnconfigure(cfg_col, weight=2)
                cfg_col += 1

            row.grid_columnconfigure(cfg_col, minsize=self.DOT_W)
            row.grid_rowconfigure(0, weight=1)

            # Selection accent strip (always in grid, colour toggled)
            accent_strip = ctk.CTkFrame(row, fg_color="transparent", width=2, corner_radius=0)
            accent_strip.grid(row=0, column=col_idx, sticky="ns", rowspan=1)
            col_idx += 1

            # Index
            index_label = tk.Label(
                row,
                text=str(sub.index),
                font=(FONTS["mono_small"][0], 9),
                fg=self._resolve_color(COLORS["text_secondary"]),
                bg=row_bg,
                anchor="center",
                padx=0,
                pady=0,
            )
            index_label.grid(row=0, column=col_idx, padx=(2, 2), sticky="nsew")
            col_idx += 1

            # Time
            time_str = f"{self._fmt(sub.start)}-{self._fmt(sub.end)}"
            time_label = tk.Label(
                row,
                text=time_str,
                font=(FONTS["mono_small"][0], 9),
                fg=self._resolve_color(COLORS["text_primary"]),
                bg=row_bg,
                anchor="w",
                padx=0,
                pady=0,
            )
            setattr(time_label, "_column_role", "time")
            time_label.grid(row=0, column=col_idx, padx=(2, self.TIME_RIGHT_PAD), sticky="nsew")
            col_idx += 1

            text_widgets = [index_label, time_label]

            # Original text (visible + editable via double-click)
            original_display = sub.original_text.strip() if sub.original_text else ""
            if not original_display and getattr(sub, "words", None):
                original_display = " ".join((w.word or "").strip() for w in sub.words).strip()
            if not original_display:
                original_display = "…"

            original_family = self._pick_text_family(original_display, ff)

            orig_label = tk.Label(
                row,
                font=(original_family, 10),
                fg=self._resolve_color(COLORS["text_primary"]),
                bg=self._column_bg("original", row_bg),
                text="", width=1, anchor="w", justify="left",
                padx=0, pady=0, cursor="xterm",
            )
            setattr(orig_label, "_column_role", "original")
            orig_label.grid(row=0, column=col_idx, sticky="nsew", padx=(self.ORIGINAL_LEFT_PAD, self.ORIGINAL_RIGHT_PAD))
            setattr(orig_label, "_clip_enabled", True)
            setattr(orig_label, "_preferred_family", ff)
            self._set_clipped_label_text(orig_label, original_display)
            orig_label.bind("<Configure>", lambda e, w=orig_label: self._apply_label_clipping(w))
            orig_label.bind("<Double-Button-1>", lambda e, idx=i: self._start_inline_edit(e.widget, idx, "original"))
            text_widgets.append(orig_label)
            col_idx += 1

            # Translation text
            if has_translation:
                trans_text = (sub.translated_text or "").strip() or "…"
                translated_family = self._pick_text_family(trans_text, ff)
                trans_label = tk.Label(
                    row,
                    font=(translated_family, 10),
                    fg=self._resolve_color(COLORS["subtitle_translation_text"]),
                    bg=row_bg,
                    text="", width=1, anchor="w", justify="left",
                    padx=0, pady=0, cursor="xterm",
                )
                setattr(trans_label, "_column_role", "translation")
                trans_label.grid(row=0, column=col_idx, sticky="nsew", padx=(2, 2))
                setattr(trans_label, "_clip_enabled", True)
                setattr(trans_label, "_preferred_family", ff)
                self._set_clipped_label_text(trans_label, trans_text)
                trans_label.bind("<Configure>", lambda e, w=trans_label: self._apply_label_clipping(w))
                trans_label.bind("<Double-Button-1>", lambda e, idx=i: self._start_inline_edit(e.widget, idx, "translated"))
                text_widgets.append(trans_label)
                col_idx += 1

            # Override style indicator dot (shown if the line has any style override)
            has_override = self.state.subtitle_has_style_override(sub)
            override_dot = tk.Label(
                row,
                text="●" if has_override else "○",
                font=(ff, 8),
                fg=self._resolve_color(COLORS["accent"]) if has_override else self._resolve_color(COLORS["text_muted"]),
                bg=row_bg,
                anchor="center",
                cursor="hand2",
                padx=0, pady=0,
                width=2,
            )
            override_dot.grid(row=0, column=col_idx, padx=(0, 2), sticky="nsew")
            text_widgets.append(override_dot)

            # Row click + hover bindings on all children
            for child in row.winfo_children():
                child.bind("<Button-1>", lambda e, idx=i: self._on_row_click(idx))
                child.bind("<Enter>", lambda e, idx=i: self._on_row_hover(idx, True))
                child.bind("<Leave>", lambda e, idx=i: self._on_row_hover(idx, False))
                child.bind("<Button-3>", lambda e, idx=i: self._on_row_right_click(e, idx))

            row.bind("<Button-1>", lambda e, idx=i: self._on_row_click(idx))
            row.bind("<Enter>", lambda e, idx=i: self._on_row_hover(idx, True))
            row.bind("<Leave>", lambda e, idx=i: self._on_row_hover(idx, False))
            row.bind("<Button-3>", lambda e, idx=i: self._on_row_right_click(e, idx))

            self.rows.append((row, accent_strip, text_widgets))

        self._update_selection()
        # Grid layout settles asynchronously; re-clip after it stabilises.
        self.after(60, self._reclip_all)

    def _sync_header_columns(self):
        """Mirror exact grid cell widths from the first row onto the header columns."""
        if not self.rows:
            return
        try:
            self.update_idletasks()
            row_frame, _, _ = self.rows[0]
            row_frame.update_idletasks()

            has_translation = self.state.bilingual and any(
                s.translated_text for s in self.state.subtitles
            )

            # (header_col, row_col) — row col indices match _rebuild_list cfg_col order
            col_pairs = [(1, 1), (2, 2)]   # # and TIME
            hcol = 3; rcol = 3
            col_pairs.append((hcol, rcol)); hcol += 1; rcol += 1    # ORIGINAL
            if has_translation:
                col_pairs.append((hcol, rcol))                       # TRANSLATION

            for h_col, r_col in col_pairs:
                bbox = row_frame.grid_bbox(r_col, 0)   # full cell incl. padx
                if bbox and bbox[2] > 1:
                    self.col_header.grid_columnconfigure(h_col, weight=0, minsize=bbox[2])
        except Exception:
            pass

    def _reclip_all(self):
        for _, _, widgets in self.rows:
            for w in widgets:
                if isinstance(w, tk.Label) and getattr(w, "_clip_enabled", False):
                    self._apply_label_clipping(w)
        self._sync_header_columns()

    def _on_row_click(self, index):
        self.state.set_selected_subtitle(index)

    def _on_row_hover(self, index, entering):
        if index >= len(self.rows):
            return
        # Hint logic runs regardless of selection state
        if entering:
            if hasattr(self, '_hint_hide_id'):
                self.after_cancel(self._hint_hide_id)
            self.hint_label.place(relx=0, rely=1.0, anchor="sw",
                                  relwidth=1.0, y=-SPACING["xs"])
        else:
            self._hint_hide_id = self.after(300, self.hint_label.place_forget)
        row, _, widgets = self.rows[index]
        if index == self.state.selected_subtitle_index:
            return
        if entering:
            row.configure(fg_color=COLORS["row_hover"])
            self._set_widget_row_bg(widgets, self._resolve_color(COLORS["row_hover"]))
        else:
            color = COLORS["row_even"] if index % 2 == 0 else COLORS["row_odd"]
            row.configure(fg_color=color)
            self._set_widget_row_bg(widgets, self._resolve_color(color))

    def _start_inline_edit(self, label_widget, index, field):
        if index >= len(self.state.subtitles):
            return

        if self._active_editor is not None:
            self._commit_inline_edit()

        sub = self.state.subtitles[index]
        if field == "original":
            current = sub.original_text or ""
        else:
            current = sub.translated_text or ""

        label_widget.update_idletasks()
        row = label_widget.master
        row.update_idletasks()

        x = label_widget.winfo_x()
        y = label_widget.winfo_y()
        w = max(80, label_widget.winfo_width())
        h = max(22, label_widget.winfo_height())

        entry = tk.Entry(
            row,
            font=label_widget.cget("font"),
            fg=label_widget.cget("fg"),
            bg=self._resolve_color(COLORS["entry_bg"]),
            insertbackground=self._resolve_color(COLORS["text_primary"]),
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=self._resolve_color(COLORS["border_subtle"]),
            highlightcolor=self._resolve_color(COLORS["accent"]),
        )
        entry.insert(0, current)
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus_set()
        entry.selection_range(0, tk.END)

        entry.bind("<Return>", lambda e: self._commit_inline_edit())
        entry.bind("<KP_Enter>", lambda e: self._commit_inline_edit())
        entry.bind("<Escape>", lambda e: self._cancel_inline_edit())
        entry.bind("<FocusOut>", lambda e: self._commit_inline_edit())

        self._active_editor = {
            "entry": entry,
            "index": index,
            "field": field,
            "label": label_widget,
        }

    def _commit_inline_edit(self):
        if self._active_editor is None:
            return

        editor = self._active_editor
        entry = editor["entry"]
        index = editor["index"]
        field = editor["field"]
        label_widget = editor["label"]

        try:
            new_text = entry.get()
        except Exception:
            self._active_editor = None
            return

        if 0 <= index < len(self.state.subtitles):
            sub = self.state.subtitles[index]
            if field == "original":
                if sub.words and new_text.strip():
                    sub.words = remap_word_timestamps(
                        sub.words, new_text.strip(), sub.start, sub.end
                    )
                elif not new_text.strip():
                    sub.words = []
                sub.original_text = new_text
                display = new_text.strip() or "…"
                preferred = getattr(label_widget, "_preferred_family", get_font_family())
                family = self._pick_text_family(display, preferred)
                label_widget.configure(font=(family, 10))
                self._set_clipped_label_text(label_widget, display)
            else:
                sub.translated_text = new_text
                display = new_text.strip() or "…"
                preferred = getattr(label_widget, "_preferred_family", get_font_family())
                family = self._pick_text_family(display, preferred)
                label_widget.configure(font=(family, 10))
                self._set_clipped_label_text(label_widget, display)
                self.state.sync_bilingual_with_translations()
            self.state.notify("subtitles_edited")

        try:
            entry.destroy()
        except Exception:
            pass
        self._active_editor = None

    def _cancel_inline_edit(self):
        if self._active_editor is None:
            return
        entry = self._active_editor.get("entry")
        try:
            entry.destroy()
        except Exception:
            pass
        self._active_editor = None

    def _update_selection(self):
        sel = self.state.selected_subtitle_index
        for i, (row, accent_strip, widgets) in enumerate(self.rows):
            if i == sel:
                row.configure(fg_color=COLORS["row_selected"])
                accent_strip.configure(fg_color=COLORS["accent"])
                self._set_widget_row_bg(widgets, self._resolve_color(COLORS["row_selected"]))
            else:
                color = COLORS["row_even"] if i % 2 == 0 else COLORS["row_odd"]
                row.configure(fg_color=color)
                accent_strip.configure(fg_color="transparent")
                self._set_widget_row_bg(widgets, self._resolve_color(color))

    def _set_widget_row_bg(self, widgets, bg_color: str):
        for widget in widgets:
            try:
                if isinstance(widget, tk.Label):
                    widget.configure(bg=self._column_bg(getattr(widget, "_column_role", "default"), bg_color))
                else:
                    widget.configure(fg_color=bg_color)
            except Exception:
                pass

    def _column_bg(self, role: str, base_bg: str) -> str:
        if role != "original":
            return base_bg
        delta = 10 if ctk.get_appearance_mode().lower() == "dark" else -10
        return self._shift_hex_color(base_bg, delta)

    @staticmethod
    def _shift_hex_color(color: str, delta: int) -> str:
        if not isinstance(color, str) or not color.startswith("#") or len(color) != 7:
            return color
        try:
            red = max(0, min(255, int(color[1:3], 16) + delta))
            green = max(0, min(255, int(color[3:5], 16) + delta))
            blue = max(0, min(255, int(color[5:7], 16) + delta))
        except ValueError:
            return color
        return f"#{red:02X}{green:02X}{blue:02X}"

    @staticmethod
    def _resolve_color(color) -> str:
        if isinstance(color, (tuple, list)) and len(color) >= 2:
            is_dark = ctk.get_appearance_mode().lower() == "dark"
            return color[1] if is_dark else color[0]
        return color

    def _on_row_right_click(self, event, index):
        self.state.set_selected_subtitle(index)
        menu = tk.Menu(self, tearoff=0)
        has_override = self.state.subtitle_has_style_override(self.state.subtitles[index])
        menu.add_command(label="Set line style…", command=lambda: self._open_line_style_dialog(index))
        if has_override:
            menu.add_command(label="Clear line style", command=lambda: self._clear_line_style(index))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _open_line_style_dialog(self, index):
        if index >= len(self.state.subtitles):
            return
        sub = self.state.subtitles[index]
        base_style = self.state.get_primary_style_for_subtitle(sub)
        # If no override yet, clone the current effective style
        current = self.state.get_primary_style_for_subtitle(sub)
        dialog = LineStyleDialog(self, self.state, index, current)
        dialog.grab_set()

    def _clear_line_style(self, index):
        if index < len(self.state.subtitles):
            sub = self.state.subtitles[index]
            sub.style_override = None
            sub.primary_style_override = None
            sub.secondary_style_override = None
            self.state.notify("subtitles_edited")
            self._rebuild_list()

    @staticmethod
    def _fmt(seconds: float) -> str:
        total = max(0.0, float(seconds))
        h = int(total // 3600)
        m = int((total % 3600) // 60)
        s = total % 60
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:05.2f}"
        return f"{m:02d}:{s:05.2f}"


class LineStyleDialog(ctk.CTkToplevel):
    """Compact dialog for setting a per-line style override on a subtitle entry."""

    def __init__(self, parent, state, subtitle_index: int, current_style: SubtitleStyle):
        super().__init__(parent)
        self.state = state
        self.subtitle_index = subtitle_index
        self.style = SubtitleStyle(**current_style.to_dict())  # working copy

        ff = get_font_family()
        self.title("Line Style Override")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["bg_primary"] if isinstance(COLORS["bg_primary"], str)
                       else COLORS["bg_primary"][1])

        self.grid_columnconfigure(0, weight=1)

        row = 0
        ctk.CTkLabel(
            self, text="Override style for this line",
            font=ctk.CTkFont(family=ff, size=13, weight="bold"),
            text_color=COLORS["text_heading"],
        ).grid(row=row, column=0, columnspan=2, padx=16, pady=(14, 8), sticky="w")
        row += 1

        # Text color
        row = self._add_color_row(row, ff, "Text Color", "primary_color")
        # Outline color
        row = self._add_color_row(row, ff, "Outline Color", "outline_color")

        # Font size
        ctk.CTkLabel(self, text="Font Size:", font=ctk.CTkFont(family=ff, size=12),
                     text_color=COLORS["text_secondary"]).grid(row=row, column=0, sticky="w", padx=16, pady=(4, 0))
        size_frame = ctk.CTkFrame(self, fg_color="transparent")
        size_frame.grid(row=row, column=1, sticky="ew", padx=16, pady=(4, 0))
        size_frame.grid_columnconfigure(0, weight=1)
        self.size_slider = ctk.CTkSlider(
            size_frame, from_=16, to=120, number_of_steps=104,
            progress_color=COLORS["accent"], button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"], fg_color=COLORS["progress_bg"],
            command=self._on_size_change, height=14,
        )
        self.size_slider.set(self.style.font_size)
        self.size_slider.grid(row=0, column=0, sticky="ew")
        self.size_label = ctk.CTkLabel(
            size_frame, text=str(self.style.font_size),
            font=ctk.CTkFont(family=ff, size=11),
            text_color=COLORS["text_secondary"], width=35,
        )
        self.size_label.grid(row=0, column=1)
        row += 1

        # Bold / Italic
        toggle_frame = ctk.CTkFrame(self, fg_color="transparent")
        toggle_frame.grid(row=row, column=0, columnspan=2, sticky="w", padx=16, pady=(6, 0))
        self.bold_sw = ctk.CTkSwitch(toggle_frame, text="Bold",
                                     font=ctk.CTkFont(family=ff, size=12),
                                     text_color=COLORS["text_secondary"],
                                     command=lambda: setattr(self.style, 'bold', bool(self.bold_sw.get())))
        self.bold_sw.grid(row=0, column=0, padx=(0, 16))
        if self.style.bold:
            self.bold_sw.select()

        self.italic_sw = ctk.CTkSwitch(toggle_frame, text="Italic",
                                       font=ctk.CTkFont(family=ff, size=12),
                                       text_color=COLORS["text_secondary"],
                                       command=lambda: setattr(self.style, 'italic', bool(self.italic_sw.get())))
        self.italic_sw.grid(row=0, column=1)
        if self.style.italic:
            self.italic_sw.select()
        row += 1

        # Absolute vertical position
        ctk.CTkLabel(self, text="Vertical:", font=ctk.CTkFont(family=ff, size=12),
                     text_color=COLORS["text_secondary"]).grid(row=row, column=0, sticky="w", padx=16, pady=(6, 0))
        off_frame = ctk.CTkFrame(self, fg_color="transparent")
        off_frame.grid(row=row, column=1, sticky="ew", padx=16, pady=(6, 0))
        off_frame.grid_columnconfigure(0, weight=1)
        self.offset_slider = ctk.CTkSlider(
            off_frame, from_=0, to=100, number_of_steps=100,
            progress_color=COLORS["accent"], button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"], fg_color=COLORS["progress_bg"],
            command=self._on_offset_change, height=14,
        )
        pos_y = int(getattr(self.style, 'position_y_percent', {"top": 15, "center": 50, "bottom": 85}.get(getattr(self.style, 'position', 'bottom'), 85)))
        self.offset_slider.set(pos_y)
        self.offset_slider.grid(row=0, column=0, sticky="ew")
        self.offset_label = ctk.CTkLabel(
            off_frame, text=f"{pos_y}%",
            font=ctk.CTkFont(family=ff, size=11),
            text_color=COLORS["text_secondary"], width=40,
        )
        self.offset_label.grid(row=0, column=1)
        row += 1

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=row, column=0, columnspan=2, pady=(12, 14), padx=16, sticky="ew")
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            btn_frame, text="Apply",
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            font=ctk.CTkFont(family=ff, size=12),
            command=self._apply, height=30,
        ).grid(row=0, column=0, padx=(0, 6), sticky="ew")

        ctk.CTkButton(
            btn_frame, text="Cancel",
            fg_color=COLORS["button_secondary"], hover_color=COLORS["button_secondary_hover"],
            font=ctk.CTkFont(family=ff, size=12),
            text_color=COLORS["text_primary"],
            command=self.destroy, height=30,
        ).grid(row=0, column=1, padx=(6, 0), sticky="ew")

    def _add_color_row(self, row: int, ff, label: str, attr: str) -> int:
        ctk.CTkLabel(self, text=f"{label}:", font=ctk.CTkFont(family=ff, size=12),
                     text_color=COLORS["text_secondary"]).grid(row=row, column=0, sticky="w", padx=16, pady=(4, 0))

        color_frame = ctk.CTkFrame(self, fg_color="transparent")
        color_frame.grid(row=row, column=1, sticky="w", padx=16, pady=(4, 0))

        swatch = tk.Canvas(color_frame, width=22, height=22, highlightthickness=0, cursor="hand2")
        swatch.grid(row=0, column=0, padx=(0, 6))
        current_color = getattr(self.style, attr)
        self._draw_swatch(swatch, current_color)

        hex_label = ctk.CTkLabel(color_frame, text=current_color,
                                 font=ctk.CTkFont(family=ff, size=11),
                                 text_color=COLORS["text_secondary"])
        hex_label.grid(row=0, column=1)

        swatch.bind("<Button-1>", lambda e, a=attr, s=swatch, hl=hex_label: self._pick_color(a, s, hl))
        return row + 1

    def _draw_swatch(self, canvas, color: str):
        canvas.delete("all")
        canvas.create_oval(2, 2, 20, 20, fill=color, outline=color)
        is_dark = ctk.get_appearance_mode().lower() == "dark"
        border = COLORS["border"][1] if isinstance(COLORS["border"], (list, tuple)) else COLORS["border"]
        bg = COLORS["bg_secondary"][1] if isinstance(COLORS["bg_secondary"], (list, tuple)) else COLORS["bg_secondary"]
        canvas.create_oval(2, 2, 20, 20, outline=border if is_dark else "#CCCCCC", width=1)
        canvas.configure(bg=bg if is_dark else "#F3F4F6")

    def _pick_color(self, attr: str, swatch, label):
        current = getattr(self.style, attr)
        result = colorchooser.askcolor(color=current, title=f"Choose {attr.replace('_', ' ').title()}")
        if result[1]:
            setattr(self.style, attr, result[1])
            self._draw_swatch(swatch, result[1])
            label.configure(text=result[1])

    def _on_size_change(self, value):
        self.style.font_size = int(value)
        self.size_label.configure(text=str(int(value)))

    def _on_offset_change(self, value):
        v = int(round(float(value)))
        self.style.position_y_percent = v
        self.offset_label.configure(text=f"{v}%")

    def _apply(self):
        if self.subtitle_index < len(self.state.subtitles):
            sub = self.state.subtitles[self.subtitle_index]
            sub.primary_style_override = self.style
            sub.style_override = None
            self.state.notify("subtitles_edited")
        self.destroy()

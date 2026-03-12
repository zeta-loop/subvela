import customtkinter as ctk
import os
from tkinter import filedialog
from app.theme import COLORS, FONTS, SPACING, RADIUS, IconRenderer, get_font_family
from core.video_utils import get_video_info, format_duration

# Try tkinterdnd2 for drag-and-drop
try:
    from tkinterdnd2 import DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False

VIDEO_EXTENSIONS = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v")


class VideoPanel(ctk.CTkFrame):
    def __init__(self, parent, state, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.state = state

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ff = get_font_family()

        # Title
        ctk.CTkLabel(
            self, text="Import Video",
            font=ctk.CTkFont(family=ff, size=FONTS["display"][1], weight="bold"),
            text_color=COLORS["text_heading"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=SPACING["lg"], pady=(SPACING["lg"], SPACING["md"]))

        # Drop zone
        self.drop_zone = ctk.CTkFrame(
            self,
            fg_color=COLORS["drop_zone_bg"],
            border_color=COLORS["drop_zone_border"],
            border_width=2,
            corner_radius=RADIUS["xl"],
        )
        self.drop_zone.grid(row=1, column=0, sticky="nsew", padx=SPACING["lg"], pady=(0, SPACING["md"]))
        self.drop_zone.grid_columnconfigure(0, weight=1)
        self.drop_zone.grid_rowconfigure(0, weight=1)

        # Drop zone content
        inner = ctk.CTkFrame(self.drop_zone, fg_color="transparent")
        inner.place(relx=0.5, rely=0.5, anchor="center")

        self._import_icon = IconRenderer.get("import", 48)
        self._check_icon = IconRenderer.get_colored("check", 48, "#059669")

        self.drop_icon = ctk.CTkLabel(
            inner, text="",
            image=self._import_icon,
        )
        self.drop_icon.pack(pady=(0, SPACING["md"]))

        self.drop_text = ctk.CTkLabel(
            inner,
            text="Drop video file here\nor click Browse",
            font=ctk.CTkFont(family=ff, size=FONTS["body"][1]),
            text_color=COLORS["text_secondary"],
            justify="center",
        )
        self.drop_text.pack(pady=(0, SPACING["lg"]))

        self.browse_btn = ctk.CTkButton(
            inner,
            text="Browse Files",
            font=ctk.CTkFont(family=ff, size=FONTS["body_bold"][1]),
            fg_color=COLORS["button_primary"],
            hover_color=COLORS["button_primary_hover"],
            text_color=COLORS["button_text"],
            corner_radius=RADIUS["md"],
            height=40,
            width=160,
            command=self._browse,
            cursor="hand2",
        )
        self.browse_btn.pack()

        # Video info display (initially hidden)
        self.info_frame = ctk.CTkFrame(
            self,
            fg_color=COLORS["bg_secondary"],
            corner_radius=RADIUS["card"],
        )
        self.info_frame.grid(row=2, column=0, sticky="ew", padx=SPACING["lg"], pady=(0, SPACING["lg"]))
        self.info_frame.grid_columnconfigure(1, weight=1)
        self.info_frame.grid_columnconfigure(3, weight=1)
        self.info_frame.grid_remove()

        self.info_labels = {}
        info_items = [("Filename", 0, 0), ("Duration", 0, 2), ("Resolution", 1, 0), ("FPS", 1, 2)]
        for key, r, c in info_items:
            ctk.CTkLabel(
                self.info_frame, text=f"{key}:",
                font=ctk.CTkFont(family=ff, size=FONTS["caption"][1]),
                text_color=COLORS["text_muted"],
                anchor="w",
            ).grid(row=r, column=c, sticky="w", padx=(SPACING["lg"], SPACING["xs"]), pady=SPACING["sm"])
            lbl = ctk.CTkLabel(
                self.info_frame, text="",
                font=ctk.CTkFont(family=ff, size=FONTS["body"][1]),
                text_color=COLORS["text_primary"],
                anchor="w",
            )
            lbl.grid(row=r, column=c + 1, sticky="w", padx=(0, SPACING["lg"]), pady=SPACING["sm"])
            self.info_labels[key] = lbl

        # Setup drag-and-drop if available
        self._setup_dnd()

    def _setup_dnd(self):
        if not HAS_DND:
            return
        try:
            self.drop_zone.drop_target_register(DND_FILES)
            self.drop_zone.dnd_bind("<<Drop>>", self._on_drop)
            self.drop_zone.dnd_bind("<<DragEnter>>", self._on_drag_enter)
            self.drop_zone.dnd_bind("<<DragLeave>>", self._on_drag_leave)
        except Exception:
            pass

    def _on_drop(self, event):
        self.drop_zone.configure(border_color=COLORS["drop_zone_border"])
        path = event.data.strip().strip("{}")
        if os.path.isfile(path) and path.lower().endswith(VIDEO_EXTENSIONS):
            self._load_video(path)

    def _on_drag_enter(self, event):
        self.drop_zone.configure(border_color=COLORS["accent"])

    def _on_drag_leave(self, event):
        self.drop_zone.configure(border_color=COLORS["drop_zone_border"])

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=[
                ("Video files", " ".join(f"*{ext}" for ext in VIDEO_EXTENSIONS)),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._load_video(path)

    def _load_video(self, path):
        info = get_video_info(path)
        if info is None:
            self.drop_text.configure(text="Failed to load video.\nTry another file.")
            return

        self.state.set_video(path, info)

        # Update UI
        self.drop_text.configure(text=f"Loaded: {info['filename']}")
        self.drop_icon.configure(image=self._check_icon)

        # Show info
        self.info_labels["Filename"].configure(text=info["filename"])
        self.info_labels["Duration"].configure(text=format_duration(info["duration"]))
        self.info_labels["Resolution"].configure(text=f"{info['width']}x{info['height']}")
        self.info_labels["FPS"].configure(text=f"{info['fps']:.1f}")
        self.info_frame.grid()

# Cinema Studio design system
# Each value is a (light_mode, dark_mode) tuple for CustomTkinter

from functools import lru_cache
from PIL import Image, ImageDraw
from customtkinter import CTkImage
from tkinter import font as tkfont

COLORS = {
    # Backgrounds — 4 depth layers, cinematic dark navy
    "bg_primary": ("#E5E7EB", "#0A0E17"),
    "bg_secondary": ("#FFFFFF", "#111827"),
    "bg_tertiary": ("#E5E7EB", "#1F2937"),
    "bg_elevated": ("#FFFFFF", "#243044"),
    "bg_glass": ("#FFFFFFCC", "#1E293BCC"),

    # Sidebar
    "sidebar_bg": ("#E5E7EB", "#080C14"),
    "sidebar_active": ("#3B82F6", "#3B82F6"),
    "sidebar_hover": ("#D1D5DB", "#1F2937"),
    "sidebar_icon": ("#6B7280", "#9CA3AF"),
    "sidebar_icon_active": ("#FFFFFF", "#FFFFFF"),

    # Text
    "text_primary": ("#0F172A", "#F1F5F9"),
    "text_secondary": ("#4B5563", "#9CA3AF"),
    "text_muted": ("#6B7280", "#6B7280"),
    "text_heading": ("#111827", "#F9FAFB"),
    "subtitle_translation_text": ("#6B7280", "#9CA3AF"),

    # Accent
    "accent": ("#3B82F6", "#60A5FA"),
    "accent_hover": ("#2563EB", "#93C5FD"),
    "accent_muted": ("#93C5FD", "#1E3A5F"),
    "accent_subtle": ("#EFF6FF", "#172554"),

    # Semantic colors — warmer tones
    "success": ("#059669", "#34D399"),
    "warning": ("#D97706", "#FBBF24"),
    "error": ("#DC2626", "#F87171"),

    # Borders
    "border": ("#D1D5DB", "#374151"),
    "border_light": ("#E5E7EB", "#1F2937"),
    "border_subtle": ("#F3F4F6", "#1F2937"),
    "border_focus": ("#3B82F6", "#60A5FA"),

    # Interactive areas
    "drop_zone_bg": ("#F9FAFB", "#0F172A"),
    "drop_zone_border": ("#9CA3AF", "#4B5563"),
    "drop_zone_active": ("#DBEAFE", "#1E3A5F"),

    # Preview
    "preview_bg": ("#000000", "#000000"),

    # Buttons
    "button_primary": ("#3B82F6", "#3B82F6"),
    "button_primary_hover": ("#2563EB", "#2563EB"),
    "button_secondary": ("#D1D5DB", "#374151"),
    "button_secondary_hover": ("#B0B8C4", "#4B5563"),
    "button_text": ("#FFFFFF", "#FFFFFF"),
    "button_text_secondary": ("#111827", "#F1F5F9"),

    # Inputs
    "entry_bg": ("#FFFFFF", "#1F2937"),
    "entry_border": ("#D1D5DB", "#4B5563"),
    "entry_focus": ("#3B82F6", "#60A5FA"),

    # Scrollbar
    "scrollbar": ("#D1D5DB", "#374151"),
    "scrollbar_hover": ("#9CA3AF", "#4B5563"),

    # Progress bar
    "progress_bg": ("#E5E7EB", "#1F2937"),
    "progress_fill": ("#3B82F6", "#60A5FA"),

    # Subtitle list rows
    "row_even": ("#FFFFFF", "#111827"),
    "row_odd": ("#F9FAFB", "#0F1629"),
    "row_selected": ("#DBEAFE", "#1E3A5F"),
    "row_hover": ("#F3F4F6", "#1A2744"),

    # Step indicators
    "step_completed": ("#059669", "#34D399"),
    "step_active": ("#3B82F6", "#60A5FA"),
    "step_pending": ("#D1D5DB", "#4B5563"),
    "step_line": ("#9CA3AF", "#374151"),
}


def get_font_family() -> str:
    """Return Inter if available, else fallback to Segoe UI."""
    try:
        available = tkfont.families()
        if "Inter" in available:
            return "Inter"
    except Exception:
        pass
    return "Segoe UI"


def _ff():
    """Shorthand for font family at import-time — deferred first call."""
    return get_font_family()


# Typography — Inter with fallback chain
# NOTE: These are evaluated lazily via get_font_family() on first use
FONTS = {
    "display": ("Inter", 22),          # page titles
    "heading": ("Inter", 16),
    "subheading": ("Inter", 13),
    "body": ("Inter", 13),
    "body_bold": ("Inter", 13),
    "small": ("Inter", 11),
    "small_bold": ("Inter", 11),
    "caption": ("Inter", 10),           # labels, badges
    "brand": ("Inter", 14),             # app name
    "mono": ("Cascadia Code", 12),
    "mono_small": ("Cascadia Code", 10),
    "sidebar_label": ("Inter", 12),
    "sidebar_label_small": ("Inter", 10),
    "subtitle_preview": ("Inter", 11),
}

# Spacing constants
SPACING = {
    "xxs": 2,
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 24,
    "xxl": 32,
    "xxxl": 48,
}

# Corner radius
RADIUS = {
    "xs": 4,
    "sm": 6,
    "md": 8,
    "card": 10,
    "lg": 12,
    "xl": 16,
    "pill": 999,
}

# Sidebar dimensions
SIDEBAR = {
    "expanded_width": 200,
    "collapsed_width": 56,
    "animation_steps": 8,
    "animation_delay_ms": 15,
    "step_indicator_size": 28,
}

# Step definitions for sidebar
STEPS = [
    {"label": "Import", "number": 1, "icon": "import", "description": "Select video file"},
    {"label": "Transcribe", "number": 2, "icon": "waveform", "description": "Speech to text"},
    {"label": "Style", "number": 3, "icon": "palette", "description": "Customize subtitles"},
    {"label": "Export", "number": 4, "icon": "download", "description": "Export & burn-in"},
]


class IconRenderer:
    """Pillow-based icon renderer producing CTkImage with light/dark variants."""

    _cache = {}

    @classmethod
    def get(cls, name: str, size: int = 20) -> CTkImage:
        key = (name, size)
        if key in cls._cache:
            return cls._cache[key]

        light = cls._render(name, size, dark_mode=False)
        dark = cls._render(name, size, dark_mode=True)
        img = CTkImage(light_image=light, dark_image=dark, size=(size, size))
        cls._cache[key] = img
        return img

    @classmethod
    def get_colored(cls, name: str, size: int, color: str) -> CTkImage:
        """Get icon with a specific color (same for both modes)."""
        key = (name, size, color)
        if key in cls._cache:
            return cls._cache[key]

        img_pil = cls._render_colored(name, size, color)
        img = CTkImage(light_image=img_pil, dark_image=img_pil, size=(size, size))
        cls._cache[key] = img
        return img

    @classmethod
    def _render(cls, name: str, size: int, dark_mode: bool) -> Image.Image:
        color = "#F1F5F9" if dark_mode else "#111827"
        return cls._render_colored(name, size, color)

    @classmethod
    def _render_colored(cls, name: str, size: int, color: str) -> Image.Image:
        s = size * 2  # 2x for antialiasing
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        m = s // 8  # margin

        if name == "import":
            # Arrow pointing down into a tray
            cx = s // 2
            draw.line([(cx, m + 2), (cx, s - m * 3)], fill=color, width=max(2, s // 10))
            aw = s // 4
            ay = s - m * 3
            draw.polygon([(cx - aw, ay - aw), (cx + aw, ay - aw), (cx, ay + 2)], fill=color)
            draw.line([(m, s - m * 2), (m, s - m), (s - m, s - m), (s - m, s - m * 2)], fill=color, width=max(2, s // 12))

        elif name == "waveform":
            # Sound waveform bars
            bars = 5
            bw = max(2, (s - 2 * m) // (bars * 2))
            heights = [0.3, 0.7, 1.0, 0.6, 0.4]
            gap = (s - 2 * m) / bars
            for i, h in enumerate(heights):
                x = int(m + gap * i + gap / 2 - bw / 2)
                bh = int((s - 2 * m) * h * 0.5)
                cy = s // 2
                draw.rounded_rectangle([x, cy - bh, x + bw, cy + bh], radius=bw // 2, fill=color)

        elif name == "palette":
            # Paint palette circle with dots
            cx, cy = s // 2, s // 2
            r = s // 2 - m
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=max(2, s // 12))
            # Small dots inside
            dot_r = max(2, s // 12)
            for dx, dy in [(-r // 3, -r // 4), (r // 4, -r // 3), (0, r // 4)]:
                draw.ellipse([cx + dx - dot_r, cy + dy - dot_r, cx + dx + dot_r, cy + dy + dot_r], fill=color)

        elif name == "download":
            # Down arrow with line
            cx = s // 2
            draw.line([(cx, m), (cx, s - m * 3)], fill=color, width=max(2, s // 10))
            aw = s // 4
            ay = s - m * 3
            draw.polygon([(cx - aw, ay - aw), (cx + aw, ay - aw), (cx, ay + 2)], fill=color)
            draw.line([(m * 2, s - m), (s - m * 2, s - m)], fill=color, width=max(2, s // 10))

        elif name == "play":
            # Triangle play
            draw.polygon([(m * 2, m), (s - m, s // 2), (m * 2, s - m)], fill=color)

        elif name == "pause":
            # Two bars
            bw = s // 5
            draw.rounded_rectangle([m * 2, m, m * 2 + bw, s - m], radius=2, fill=color)
            draw.rounded_rectangle([s - m * 2 - bw, m, s - m * 2, s - m], radius=2, fill=color)

        elif name == "volume":
            # Speaker with waves
            draw.polygon([(m, s // 2 - s // 6), (s // 3, s // 2 - s // 6),
                          (s // 2, m), (s // 2, s - m),
                          (s // 3, s // 2 + s // 6), (m, s // 2 + s // 6)], fill=color)
            # Sound arcs
            for r_off in [s // 6, s // 3]:
                draw.arc([s // 2, s // 2 - r_off, s // 2 + r_off * 2, s // 2 + r_off],
                         start=-40, end=40, fill=color, width=max(2, s // 14))

        elif name == "volume_mute":
            # Speaker without waves, with X
            draw.polygon([(m, s // 2 - s // 6), (s // 3, s // 2 - s // 6),
                          (s // 2, m), (s // 2, s - m),
                          (s // 3, s // 2 + s // 6), (m, s // 2 + s // 6)], fill=color)
            xm = s * 5 // 8
            xw = s // 5
            draw.line([(xm, s // 2 - xw), (xm + xw * 2, s // 2 + xw)], fill=color, width=max(2, s // 10))
            draw.line([(xm, s // 2 + xw), (xm + xw * 2, s // 2 - xw)], fill=color, width=max(2, s // 10))

        elif name == "sun":
            cx, cy = s // 2, s // 2
            r = s // 5
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
            import math
            ray_len = s // 4
            for angle in range(0, 360, 45):
                rad = math.radians(angle)
                x1 = int(cx + (r + 3) * math.cos(rad))
                y1 = int(cy + (r + 3) * math.sin(rad))
                x2 = int(cx + (r + ray_len) * math.cos(rad))
                y2 = int(cy + (r + ray_len) * math.sin(rad))
                draw.line([(x1, y1), (x2, y2)], fill=color, width=max(2, s // 14))

        elif name == "moon":
            cx, cy = s // 2, s // 2
            r = s // 3
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
            # Cut out crescent
            offset = s // 5
            draw.ellipse([cx - r + offset, cy - r - offset // 2,
                          cx + r + offset, cy + r - offset // 2], fill=(0, 0, 0, 0))

        elif name == "check":
            # Checkmark
            lw = max(3, s // 6)
            draw.line([(m * 2, s // 2), (s * 2 // 5, s - m * 2), (s - m, m * 2)], fill=color, width=lw, joint="curve")

        elif name == "film":
            # Film strip / clapperboard
            draw.rounded_rectangle([m, m, s - m, s - m], radius=s // 10, outline=color, width=max(2, s // 12))
            draw.line([(m, s // 3), (s - m, s // 3)], fill=color, width=max(2, s // 12))
            # Perforations
            pw = max(2, s // 14)
            for x_off in [s // 4, s // 2, s * 3 // 4]:
                draw.rectangle([x_off - pw, m + 2, x_off + pw, s // 3 - 2], fill=color)

        # Downsample for antialiasing
        return img.resize((size, size), Image.LANCZOS)

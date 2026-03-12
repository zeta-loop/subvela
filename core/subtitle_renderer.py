import os
import re

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from core.font_catalog import resolve_cached_font_variant, resolve_font_family_name
from core.subtitle_model import SubtitleStyle


_FONT_REGISTRY: dict | None = None

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

        for alias, canonical in _FONT_ALIAS_MAP.items():
            canonical_path = _FONT_REGISTRY.get(canonical.casefold())
            if canonical_path:
                _FONT_REGISTRY.setdefault(alias.casefold(), canonical_path)
    except Exception:
        pass
    return _FONT_REGISTRY


def _resolve_font_path(family: str, bold: bool, italic: bool) -> str | None:
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
        key = base.casefold()
        if base and key not in seen_bases:
            deduped_bases.append(base)
            seen_bases.add(key)

    for raw_base in deduped_bases:
        words = raw_base.split()
        for length in range(len(words), 0, -1):
            base = " ".join(words[:length]).casefold()
            if style_suffix:
                path = registry.get(base + " " + style_suffix)
                if path and os.path.exists(path):
                    return path
            path = registry.get(base)
            if path and os.path.exists(path):
                return path

    return None


def build_render_params(
    state,
    current_time: float,
    sub,
    canvas_w: int,
    canvas_h: int,
    *,
    is_playing: bool,
    safe_area_alpha: float = 0.0,
) -> dict:
    anim_settings = state.get_animation_settings_for_subtitle(sub)
    return {
        "video_path": state.video_path,
        "preview_time": current_time,
        "canvas_w": canvas_w,
        "canvas_h": canvas_h,
        "subtitle": sub,
        "karaoke_mode": anim_settings.karaoke_mode,
        "animation_style": anim_settings.animation_style,
        "translation_animation_style": anim_settings.translation_animation_style,
        "transition_duration": anim_settings.transition_duration,
        "karaoke_highlight_color": anim_settings.karaoke_highlight_color,
        "highlight_dimmed_opacity": anim_settings.highlight_dimmed_opacity,
        "highlight_active_marker": anim_settings.highlight_active_marker,
        "highlight_history_on": anim_settings.highlight_history_on,
        "bounce_trail_count": anim_settings.bounce_trail_count,
        "bounce_min_chars": anim_settings.bounce_min_chars,
        "sweep_entry_style": anim_settings.sweep_entry_style,
        "sweep_history_dim": anim_settings.sweep_history_dim,
        "bilingual": state.bilingual,
        "secondary_style": state.get_secondary_style_for_subtitle(sub) if sub else state.secondary_style,
        "is_playing": is_playing,
        "style": state.get_primary_style_for_subtitle(sub) if sub else state.primary_style,
        "safe_area_alpha": safe_area_alpha,
        "video_info": state.video_info,
        "position_swapped": getattr(state, "position_swapped", False),
        "active_width_style_key": getattr(state, "_active_width_style_key", "primary"),
    }


class SubtitleOverlayRenderer:
    _ITALIC_SHEAR = 0.20

    def __init__(self, video_info: dict | None = None):
        self.video_info = video_info or {}

    def render_overlay(self, width: int, height: int, sub, params: dict) -> Image.Image:
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        return self.render_on_image(overlay, sub, params)

    def render_on_image(self, image: Image.Image, sub, params: dict) -> Image.Image:
        self.video_info = params.get("video_info", self.video_info)
        safe_area_alpha = float(params.get("safe_area_alpha", 0.0))
        if safe_area_alpha > 0.0:
            active_key = params.get("active_width_style_key", "primary")
            guide_style = params["secondary_style"] if active_key == "secondary" else params["style"]
            image = self._draw_safe_width_guide(image, guide_style, safe_area_alpha)

        if sub is None:
            return image

        karaoke = params["karaoke_mode"]
        if karaoke == "highlight" and getattr(sub, "words", None):
            return self._draw_karaoke_highlight(image, sub, params)
        if karaoke == "bounce" and getattr(sub, "words", None):
            return self._draw_karaoke_bounce(image, sub, params)
        if karaoke == "sweep" and getattr(sub, "words", None):
            return self._draw_karaoke_sweep(image, sub, params)
        effect = self._compute_anim_effect(sub, params)
        return self._draw_subtitle(image, sub, params, effect=effect)

    @staticmethod
    def _tag_font(font, want_bold: bool, want_italic: bool, got_variant: str = "regular"):
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
                    return self._tag_font(
                        font,
                        want_bold,
                        want_italic,
                        ("bold_" if want_bold else "") + ("italic" if want_italic else "") or "regular",
                    )
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

        for file_name in ["msyh.ttc", "simhei.ttf", "arial.ttf", "msgothic.ttc"]:
            try:
                font = ImageFont.truetype(file_name, font_size)
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
                "fade": {"type": "fade", "alpha": 1.0},
                "pop": {"type": "pop", "scale": 1.0},
                "slide_up": {"type": "slide_up", "y_offset": 0},
                "typewriter": {"type": "typewriter", "char_frac": 1.0},
            }
            return stable.get(anim, {})

        t = params["preview_time"]
        dur = max(0.001, params["transition_duration"])
        t_in = t - sub.start
        t_out = sub.end - t
        if anim == "fade":
            return {"type": "fade", "alpha": min(min(1.0, t_in / dur), min(1.0, t_out / (dur * 0.67)))}
        if anim == "pop":
            progress = min(1.0, t_in / dur) if t_in < dur else 1.0
            ease = 1.0 - (1.0 - progress) ** 2
            return {"type": "pop", "scale": 0.5 + 0.5 * ease}
        if anim == "slide_up":
            return {"type": "slide_up", "y_offset": int(60 * max(0.0, 1.0 - t_in / dur)) if t_in < dur else 0}
        if anim == "typewriter":
            total = max(0.001, sub.end - sub.start)
            return {"type": "typewriter", "char_frac": min(1.0, t_in / (total * 0.85))}
        return {}

    def _draw_bilingual_translation(self, img: Image.Image, sub, params: dict,
                                    primary_bottom_y: int | None = None,
                                    absolute_y: int | None = None) -> Image.Image:
        if not (params.get("bilingual") and getattr(sub, "translated_text", "")):
            return img
        style = params["secondary_style"]
        width, height = img.size
        trans_anim = params.get("translation_animation_style", "none")

        effect = {}
        if trans_anim != "none":
            effect = self._compute_anim_effect(sub, params, anim_style_override=trans_anim)

        scale = effect.get("scale", 1.0)
        anim_y_offset = effect.get("y_offset", 0)
        gap = 10
        abs_y = absolute_y + anim_y_offset if absolute_y is not None else None
        if abs_y is None and primary_bottom_y is not None:
            abs_y = primary_bottom_y + gap + anim_y_offset

        def _render_translation(target: Image.Image) -> Image.Image:
            if abs_y is not None:
                return self._draw_stacked_texts_at_y(
                    target,
                    [(sub.translated_text, style)],
                    width,
                    height,
                    y_start=abs_y,
                    scale=scale,
                )
            return self._draw_stacked_texts(
                target,
                [(sub.translated_text, style)],
                width,
                height,
                scale=scale,
                y_offset=anim_y_offset,
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

    def _resolve_bilingual_block_positions(self, img_w: int, img_h: int,
                                           primary_style: SubtitleStyle, primary_h: int,
                                           secondary_style: SubtitleStyle | None = None,
                                           secondary_h: int | None = None,
                                           y_offset: int = 0,
                                           swapped: bool = False) -> tuple[int, int | None]:
        primary_y = self._compute_y_base(
            primary_style.position,
            primary_style,
            primary_h,
            img_h,
            y_offset,
            img_w,
            anchor="bottom",
        )
        if secondary_style is None or secondary_h is None:
            return primary_y, None

        secondary_y = self._compute_y_base(
            secondary_style.position,
            secondary_style,
            secondary_h,
            img_h,
            y_offset,
            img_w,
            anchor="top",
        )

        if swapped:
            secondary_y = self._compute_y_base(
                secondary_style.position,
                secondary_style,
                secondary_h,
                img_h,
                y_offset,
                img_w,
                anchor="bottom",
            )
            primary_y = self._compute_y_base(
                primary_style.position,
                primary_style,
                primary_h,
                img_h,
                y_offset,
                img_w,
                anchor="top",
            )
            primary_y = max(primary_y, secondary_y + secondary_h + 4)
            return primary_y, secondary_y

        secondary_y = max(secondary_y, primary_y + primary_h + 4)
        return primary_y, secondary_y

    def _draw_subtitle(self, img: Image.Image, sub, params: dict, effect: dict = None) -> Image.Image:
        anim_type = (effect or {}).get("type", "none")
        if anim_type == "typewriter":
            from types import SimpleNamespace

            frac = effect.get("char_frac", 1.0)
            chars = max(1, int(len(sub.original_text) * frac))
            sub = SimpleNamespace(
                original_text=sub.original_text[:chars],
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
                r, g, b, a = rendered.convert("RGBA").split()
                a = a.point(lambda p: int(p * alpha))
                return Image.merge("RGBA", (r, g, b, a))
            base = img.copy()
            blended = Image.blend(base.convert("RGBA"), rendered.convert("RGBA"), alpha)
            return blended.convert(orig_mode)

        return self._draw_subtitle_content(img, sub, params, scale=scale, y_offset=y_offset)

    def _draw_subtitle_content(self, img: Image.Image, sub, params: dict,
                               scale: float = 1.0, y_offset: int = 0) -> Image.Image:
        img = img.copy()
        width, height = img.size
        primary_style = params["style"]

        texts = [(sub.original_text, primary_style)]
        if params["bilingual"] and getattr(sub, "translated_text", ""):
            texts.append((sub.translated_text, params["secondary_style"]))

        if params.get("position_swapped", False) and len(texts) > 1:
            texts = [texts[1], texts[0]]

        return self._draw_stacked_texts(img, texts, width, height, scale=scale, y_offset=y_offset)

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
        video_width = (self.video_info or {}).get("width", 0)
        video_height = (self.video_info or {}).get("height", 0)
        if video_width <= 0 or video_height <= 0 or img_w <= 0 or img_h <= 0:
            return 0, 0, img_w, img_h
        ratio = min(img_w / video_width, img_h / video_height)
        content_w = int(video_width * ratio)
        content_h = int(video_height * ratio)
        offset_x = (img_w - content_w) // 2
        offset_y = (img_h - content_h) // 2
        return offset_x, offset_y, content_w, content_h

    def _compute_y_base(self, position: str, style: SubtitleStyle, total_stack_h: int,
                        img_h: int, y_offset: int = 0, img_w: int = 0,
                        anchor: str | None = None) -> int:
        pos_pct = self._style_vertical_percent(style)
        _, video_y, _, video_h = self._video_content_rect(img_w or img_h, img_h)
        if video_h <= 0:
            video_y, video_h = 0, img_h
        if anchor is None:
            anchor = "bottom"
        anchor_px = video_y + int(video_h * pos_pct / 100)
        y = anchor_px if anchor == "top" else anchor_px - total_stack_h
        return y + y_offset

    def _draw_stacked_texts(self, img: Image.Image, items,
                            img_w: int, img_h: int, scale: float = 1.0, y_offset: int = 0) -> Image.Image:
        if not items:
            return img

        orig_mode = img.mode
        if orig_mode != "RGBA":
            img = img.convert("RGBA")

        draw = ImageDraw.Draw(img)
        gap = 10
        blocks = []
        total_stack_h = 0
        for text, style in items:
            font, lines, block_w, block_h = self._prepare_text_block(draw, text, style, img_w, img_h, scale=scale)
            blocks.append({"style": style, "font": font, "lines": lines, "w": block_w, "h": block_h})
            total_stack_h += block_h + gap
        total_stack_h -= gap

        render_items = []
        prev_bottom_y = None
        for index, block in enumerate(blocks):
            item_anchor = "bottom" if index == 0 else "top"
            block_y = self._compute_y_base(
                block["style"].position,
                block["style"],
                block["h"],
                img_h,
                y_offset,
                img_w,
                anchor=item_anchor,
            )
            if index > 0 and prev_bottom_y is not None:
                block_y = max(block_y, prev_bottom_y + 4)
            prev_bottom_y = block_y + block["h"]
            line_y = block_y
            for line_text, line_w, line_h in block["lines"]:
                x = (img_w - line_w) // 2
                render_items.append((block["style"], block["font"], line_text, x, line_y, line_w, line_h))
                line_y += line_h + 2

        if any(item[0].background_enabled for item in render_items):
            overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            pad = 6
            for style, _, _, x, y, width, height in render_items:
                if style.background_enabled:
                    bg = self._hex_to_rgb(style.background_color)
                    opacity = int(style.background_opacity * 255)
                    overlay_draw.rounded_rectangle(
                        [x - pad, y - 2, x + width + pad, y + height + 2],
                        radius=4,
                        fill=(*bg, opacity),
                    )
            img = Image.alpha_composite(img, overlay)

        img = self._render_text_items(img, render_items)
        if orig_mode != "RGBA":
            img = img.convert(orig_mode)
        return img

    def _draw_stacked_texts_at_y(self, img: Image.Image, items, img_w: int, img_h: int,
                                 y_start: int, scale: float = 1.0) -> Image.Image:
        if not items:
            return img
        orig_mode = img.mode
        if orig_mode != "RGBA":
            img = img.convert("RGBA")

        draw = ImageDraw.Draw(img)
        gap = 10
        blocks = []
        for text, style in items:
            font, lines, block_w, block_h = self._prepare_text_block(draw, text, style, img_w, img_h, scale=scale)
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
            overlay_draw = ImageDraw.Draw(overlay)
            pad = 6
            for style, _, _, x, y, width, height in render_items:
                if style.background_enabled:
                    bg = self._hex_to_rgb(style.background_color)
                    opacity = int(style.background_opacity * 255)
                    overlay_draw.rounded_rectangle(
                        [x - pad, y - 2, x + width + pad, y + height + 2],
                        radius=4,
                        fill=(*bg, opacity),
                    )
            img = Image.alpha_composite(img, overlay)

        img = self._render_text_items(img, render_items)
        if orig_mode != "RGBA":
            img = img.convert(orig_mode)
        return img

    def _render_text_items(self, img, render_items):
        neighbors = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
        for style, font, text, x, y, _, _ in render_items:
            img = self._apply_glow(img, style, font, text, x, y)
            img = self._apply_shadow(img, style, font, text, x, y)
            if getattr(font, "_fake_italic", False):
                img = self._render_text_block_italic(img, style, font, text, x, y)
                continue
            draw = ImageDraw.Draw(img)
            thickness = style.outline_thickness
            if thickness > 0:
                outline = self._hex_to_rgb(style.outline_color)
                for dx, dy in neighbors:
                    self._fb_text(draw, (x + dx * thickness, y + dy * thickness), text, font, outline)
            self._fb_text(draw, (x, y), text, font, self._hex_to_rgb(style.primary_color))
        return img

    @staticmethod
    def _fb_text(draw, xy, text, font, fill, **kwargs):
        draw.text(xy, text, font=font, fill=fill, **kwargs)
        if getattr(font, "_fake_bold", False):
            draw.text((xy[0] + 1, xy[1]), text, font=font, fill=fill, **kwargs)

    def _shear_italic(self, layer: Image.Image, y_center: int) -> Image.Image:
        width, height = layer.size
        return layer.transform(
            (width, height),
            Image.AFFINE,
            (1, self._ITALIC_SHEAR, -self._ITALIC_SHEAR * y_center, 0, 1, 0),
            resample=Image.BILINEAR,
        )

    def _render_text_block_italic(self, img, style, font, text, x, y):
        bbox = font.getbbox(text)
        text_height = bbox[3] - bbox[1]
        y_center = y + text_height // 2
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        layer_draw = ImageDraw.Draw(layer)
        thickness = style.outline_thickness
        neighbors = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
        if thickness > 0:
            outline = self._hex_to_rgb(style.outline_color)
            for dx, dy in neighbors:
                self._fb_text(layer_draw, (x + dx * thickness, y + dy * thickness), text, font, outline)
        self._fb_text(layer_draw, (x, y), text, font, self._hex_to_rgb(style.primary_color))
        layer = self._shear_italic(layer, y_center)
        return Image.alpha_composite(img.convert("RGBA"), layer)

    def _glow_shadow_y_center(self, font, text, y):
        bbox = font.getbbox(text)
        return y + (bbox[3] - bbox[1]) // 2

    def _apply_glow(self, img: Image.Image, style: SubtitleStyle,
                    font, text: str, x: int, y: int) -> Image.Image:
        if not getattr(style, "glow_enabled", False):
            return img
        radius = max(3.0, float(getattr(style, "glow_radius", 8)))
        glow_color = self._hex_to_rgb(getattr(style, "glow_color", "#FFFFFF"))

        text_mask = Image.new("L", img.size, 0)
        mask_draw = ImageDraw.Draw(text_mask)
        mask_draw.text((x, y), text, font=font, fill=255)
        if getattr(font, "_fake_bold", False):
            mask_draw.text((x + 1, y), text, font=font, fill=255)
        fill_blur = max(1.0, radius * 0.45)
        filled_mask = text_mask.filter(ImageFilter.GaussianBlur(fill_blur))
        filled_mask = filled_mask.point(lambda p: int(p * 0.65))

        blurred_alpha = text_mask.filter(ImageFilter.GaussianBlur(radius * 1.15))
        outer_alpha = ImageChops.subtract(blurred_alpha, filled_mask)
        outer_alpha = outer_alpha.filter(ImageFilter.GaussianBlur(max(0.5, radius * 0.2)))
        outer_alpha = outer_alpha.point(lambda p: min(255, int(p * 0.9)))

        glow_layer = Image.merge("RGBA", (
            Image.new("L", img.size, glow_color[0]),
            Image.new("L", img.size, glow_color[1]),
            Image.new("L", img.size, glow_color[2]),
            outer_alpha,
        ))
        if getattr(font, "_fake_italic", False):
            glow_layer = self._shear_italic(glow_layer, self._glow_shadow_y_center(font, text, y))

        orig_mode = img.mode
        result = Image.alpha_composite(img.convert("RGBA"), glow_layer)
        return result if orig_mode == "RGBA" else result.convert(orig_mode)

    def _apply_shadow(self, img: Image.Image, style: SubtitleStyle,
                      font, text: str, x: int, y: int) -> Image.Image:
        if not getattr(style, "shadow_enabled", False):
            return img
        sx = getattr(style, "shadow_offset_x", 2)
        sy = getattr(style, "shadow_offset_y", 2)
        blur = getattr(style, "shadow_blur", 0)
        shadow_color = self._hex_to_rgb(getattr(style, "shadow_color", "#000000"))

        shadow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_layer)
        self._fb_text(shadow_draw, (x + sx, y + sy), text, font, (*shadow_color, 220))
        if blur > 0:
            shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(blur))
        if getattr(font, "_fake_italic", False):
            shadow_layer = self._shear_italic(shadow_layer, self._glow_shadow_y_center(font, text, y))

        orig_mode = img.mode
        result = Image.alpha_composite(img.convert("RGBA"), shadow_layer)
        return result if orig_mode == "RGBA" else result.convert(orig_mode)

    def _draw_karaoke_highlight(self, img: Image.Image, sub, params: dict) -> Image.Image:
        orig_mode = img.mode
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        img = img.copy()
        draw = ImageDraw.Draw(img)
        width, height = img.size
        current_time = params["preview_time"]

        style = params["style"]
        font = self._get_font(style, height, sample_text=(sub.original_text or ""))
        words = self._get_karaoke_words(sub)
        if not words:
            result = self._draw_subtitle(img, sub, params)
            return result if orig_mode == "RGBA" else result.convert(orig_mode)

        word_metrics = []
        space_w = draw.textbbox((0, 0), " ", font=font)[2] - draw.textbbox((0, 0), " ", font=font)[0]
        for index, word_entry in enumerate(words):
            text = word_entry["word"].strip()
            if not text:
                continue
            bbox = draw.textbbox((0, 0), text, font=font)
            word_metrics.append({
                "text": text,
                "w": bbox[2] - bbox[0],
                "h": bbox[3] - bbox[1],
                "start": word_entry["start"],
                "end": word_entry["end"],
                "index": index,
            })

        if not word_metrics:
            result = self._draw_subtitle(img, sub, params)
            return result if orig_mode == "RGBA" else result.convert(orig_mode)

        max_width = max(1, int(width * max(0, min(100, int(getattr(style, "text_width_percent", 90)))) / 100))
        line_gap = 4
        lines = []
        current_line = []
        current_width = 0
        current_height = 0
        for metric in word_metrics:
            add_width = metric["w"] if not current_line else (space_w + metric["w"])
            if current_line and (current_width + add_width) > max_width:
                lines.append((current_line, current_width, current_height))
                current_line = [metric]
                current_width = metric["w"]
                current_height = metric["h"]
            else:
                current_line.append(metric)
                current_width += add_width
                current_height = max(current_height, metric["h"])
        if current_line:
            lines.append((current_line, current_width, current_height))

        total_stack_h = sum(line_h for _, _, line_h in lines) + (len(lines) - 1) * line_gap
        secondary_y = None
        if params.get("bilingual") and getattr(sub, "translated_text", ""):
            trans_draw = ImageDraw.Draw(Image.new("RGBA", img.size, (0, 0, 0, 0)))
            _, _, _, trans_h = self._prepare_text_block(
                trans_draw,
                sub.translated_text,
                params["secondary_style"],
                width,
                height,
            )
            y_start, secondary_y = self._resolve_bilingual_block_positions(
                width,
                height,
                style,
                total_stack_h,
                params["secondary_style"],
                trans_h,
                swapped=params.get("position_swapped", False),
            )
        else:
            y_start, _ = self._resolve_bilingual_block_positions(width, height, style, total_stack_h)

        highlight_color = self._hex_to_rgb(params["karaoke_highlight_color"])
        active_marker = params["highlight_active_marker"]
        history_on = params["highlight_history_on"]
        use_color = "color" in active_marker
        use_box = "box" in active_marker
        dimmed_alpha = int(params["highlight_dimmed_opacity"] * 255)
        pr, pg, pb = self._hex_to_rgb(style.primary_color)
        dimmed_color = (int(pr * dimmed_alpha / 255), int(pg * dimmed_alpha / 255), int(pb * dimmed_alpha / 255))
        outline_color = self._hex_to_rgb(style.outline_color)
        thickness = style.outline_thickness
        base_color = self._hex_to_rgb(style.primary_color)

        if style.background_enabled:
            overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            pad = 4
            bg_color = self._hex_to_rgb(style.background_color)
            opacity = int(style.background_opacity * 255)
            line_y = y_start
            for line_words, _, line_h in lines:
                tmp_x = (width - sum(m["w"] for m in line_words) - space_w * max(0, len(line_words) - 1)) // 2
                for metric in line_words:
                    overlay_draw.rounded_rectangle(
                        [tmp_x - pad, line_y - 2, tmp_x + metric["w"] + pad, line_y + metric["h"] + 2],
                        radius=4,
                        fill=(*bg_color, opacity),
                    )
                    tmp_x += metric["w"] + space_w
                line_y += line_h + line_gap
            img = Image.alpha_composite(img, overlay)
            draw = ImageDraw.Draw(img)

        if use_box:
            highlight_overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            highlight_draw = ImageDraw.Draw(highlight_overlay)
            pad = 5
            line_y = y_start
            for line_words, line_w, line_h in lines:
                tmp_x = (width - line_w) // 2
                for metric in line_words:
                    is_active = current_time >= metric["start"] and current_time < metric["end"]
                    is_spoken = current_time >= metric["end"]
                    if is_active:
                        highlight_draw.rounded_rectangle(
                            [tmp_x - pad, line_y - 3, tmp_x + metric["w"] + pad, line_y + metric["h"] + 3],
                            radius=5,
                            fill=(*highlight_color, 180),
                        )
                    elif is_spoken and history_on:
                        highlight_draw.rounded_rectangle(
                            [tmp_x - pad, line_y - 3, tmp_x + metric["w"] + pad, line_y + metric["h"] + 3],
                            radius=5,
                            fill=(*highlight_color, 90),
                        )
                    tmp_x += metric["w"] + space_w
                line_y += line_h + line_gap
            img = Image.alpha_composite(img, highlight_overlay)
            draw = ImageDraw.Draw(img)

        neighbors = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
        fake_italic = getattr(font, "_fake_italic", False)
        if fake_italic:
            text_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(text_layer)

        line_y = y_start
        if getattr(style, "glow_enabled", False):
            glow_line_y = y_start
            for line_words, line_w, line_h in lines:
                line_text = " ".join(metric["text"] for metric in line_words)
                line_x = (width - line_w) // 2
                img = self._apply_glow(img, style, font, line_text, line_x, glow_line_y)
                glow_line_y += line_h + line_gap
            draw = ImageDraw.Draw(img)
        for line_words, line_w, line_h in lines:
            cur_x = (width - line_w) // 2
            for metric in line_words:
                active = current_time >= metric["start"] and current_time < metric["end"]
                spoken = current_time >= metric["end"]
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
                        active_thickness = thickness + 1
                        for dx, dy in neighbors:
                            self._fb_text(draw, (cur_x + dx * active_thickness, line_y + dy * active_thickness), metric["text"], font, outline_color)
                    else:
                        for dx, dy in neighbors:
                            self._fb_text(draw, (cur_x + dx * thickness, line_y + dy * thickness), metric["text"], font, outline_color)
                self._fb_text(draw, (cur_x, line_y), metric["text"], font, color)
                cur_x += metric["w"] + space_w
            line_y += line_h + line_gap

        if fake_italic:
            text_layer = self._shear_italic(text_layer, y_start + total_stack_h // 2)
            img = Image.alpha_composite(img, text_layer)

        img = self._draw_bilingual_translation(
            img,
            sub,
            params,
            primary_bottom_y=y_start + total_stack_h,
            absolute_y=secondary_y,
        )
        return img if orig_mode == "RGBA" else img.convert(orig_mode)

    def _draw_karaoke_bounce(self, img: Image.Image, sub, params: dict) -> Image.Image:
        orig_mode = img.mode
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        img = img.copy()
        draw = ImageDraw.Draw(img)
        width, height = img.size
        current_time = params["preview_time"]

        style = params["style"]
        words = self._get_karaoke_words(sub)
        if not words:
            result = self._draw_subtitle(img, sub, params)
            return result if orig_mode == "RGBA" else result.convert(orig_mode)

        min_chars = params.get("bounce_min_chars", 3)
        merged = []
        index = 0
        while index < len(words):
            group = words[index]
            while len(group["word"].strip()) < min_chars and index + 1 < len(words):
                index += 1
                group = {
                    "word": group["word"] + " " + words[index]["word"],
                    "start": group["start"],
                    "end": words[index]["end"],
                }
            merged.append(group)
            index += 1
        words = merged

        current_word = None
        current_idx = -1
        for index, word_entry in enumerate(words):
            if word_entry["start"] <= current_time <= word_entry["end"]:
                current_word = word_entry
                current_idx = index
                break
        if current_word is None:
            for index, word_entry in enumerate(words):
                if current_time < word_entry["start"]:
                    current_word = word_entry
                    current_idx = index
                    break
            if current_word is None:
                if words and current_time <= float(getattr(sub, "end", 0.0)):
                    current_word = words[-1]
                    current_idx = len(words) - 1
                else:
                    return img if orig_mode == "RGBA" else img.convert(orig_mode)

        word_text = current_word["word"].strip()
        if not word_text:
            return img if orig_mode == "RGBA" else img.convert(orig_mode)

        large_size = int(style.font_size * height / 1080)
        large_font = self._get_font(style, height, size_override=large_size, sample_text=word_text)
        max_width = max(1, int(width * max(0, min(100, int(getattr(style, "text_width_percent", 90)))) / 100))

        popup_lines = []
        current_line = ""
        for token in word_text.split():
            test_line = token if not current_line else f"{current_line} {token}"
            bbox = draw.textbbox((0, 0), test_line, font=large_font)
            if (bbox[2] - bbox[0]) <= max_width or not current_line:
                current_line = test_line
            else:
                line_bbox = draw.textbbox((0, 0), current_line, font=large_font)
                popup_lines.append((current_line, line_bbox[2] - line_bbox[0], line_bbox[3] - line_bbox[1]))
                current_line = token
        if current_line:
            line_bbox = draw.textbbox((0, 0), current_line, font=large_font)
            popup_lines.append((current_line, line_bbox[2] - line_bbox[0], line_bbox[3] - line_bbox[1]))
        if not popup_lines:
            return img if orig_mode == "RGBA" else img.convert(orig_mode)

        block_h = sum(line_h for _, _, line_h in popup_lines) + (len(popup_lines) - 1) * 2
        secondary_y = None
        if params.get("bilingual") and getattr(sub, "translated_text", ""):
            trans_draw = ImageDraw.Draw(Image.new("RGBA", img.size, (0, 0, 0, 0)))
            _, _, _, trans_h = self._prepare_text_block(
                trans_draw,
                sub.translated_text,
                params["secondary_style"],
                width,
                height,
            )
            y, secondary_y = self._resolve_bilingual_block_positions(
                width,
                height,
                style,
                block_h,
                params["secondary_style"],
                trans_h,
                swapped=params.get("position_swapped", False),
            )
        else:
            y, _ = self._resolve_bilingual_block_positions(width, height, style, block_h)
        neighbors = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
        outline_color = self._hex_to_rgb(style.outline_color)
        thickness = style.outline_thickness
        text_color = self._hex_to_rgb(style.primary_color)
        fake_italic = getattr(large_font, "_fake_italic", False)
        if getattr(style, "glow_enabled", False):
            glow_line_y = y
            for line_text, line_w, line_h in popup_lines:
                line_x = (width - line_w) // 2
                img = self._apply_glow(img, style, large_font, line_text, line_x, glow_line_y)
                glow_line_y += line_h + 2
            draw = ImageDraw.Draw(img)
        if fake_italic:
            popup_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
            popup_draw = ImageDraw.Draw(popup_layer)
        else:
            popup_draw = draw

        line_y = y
        for line_text, line_w, line_h in popup_lines:
            x = (width - line_w) // 2
            if thickness > 0:
                for dx, dy in neighbors:
                    self._fb_text(popup_draw, (x + dx * thickness, line_y + dy * thickness), line_text, large_font, outline_color)
            self._fb_text(popup_draw, (x, line_y), line_text, large_font, text_color)
            line_y += line_h + 2
        if fake_italic:
            popup_layer = self._shear_italic(popup_layer, y + block_h // 2)
            img = Image.alpha_composite(img, popup_layer)
            draw = ImageDraw.Draw(img)

        small_size = max(12, int(style.font_size * height / 1080 * 0.7))
        small_font = self._get_font(style, height, size_override=small_size, sample_text=word_text)
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
            prev_bbox = draw.textbbox((0, 0), prev_word, font=small_font)
            prev_w = prev_bbox[2] - prev_bbox[0]
            prev_h = prev_bbox[3] - prev_bbox[1]
            prev_x = (width - prev_w) // 2
            trail_y -= prev_h + 4
            self._fb_text(draw, (prev_x, trail_y), prev_word, small_font, dimmed)

        img = self._draw_bilingual_translation(
            img,
            sub,
            params,
            primary_bottom_y=y + block_h,
            absolute_y=secondary_y,
        )
        return img if orig_mode == "RGBA" else img.convert(orig_mode)

    def _draw_karaoke_sweep(self, img: Image.Image, sub, params: dict) -> Image.Image:
        import math
        from types import SimpleNamespace

        words = self._get_karaoke_words(sub)
        if not words:
            return self._draw_subtitle(img, sub, params)

        current_time = params["preview_time"]
        visible = [word for word in words if word["start"] <= current_time]
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
        if history_dim <= 0.0:
            newest_sub = SimpleNamespace(
                original_text=newest["word"],
                translated_text=getattr(sub, "translated_text", None),
                style_override=getattr(sub, "style_override", None),
            )
            rendered = self._draw_subtitle(base.copy(), newest_sub, params).convert("RGBA")
            if entry_alpha >= 1.0:
                return rendered if orig_mode == "RGBA" else rendered.convert(orig_mode)
            result = Image.blend(base, rendered, entry_alpha)
            return result if orig_mode == "RGBA" else result.convert(orig_mode)

        full_text = " ".join(word["word"] for word in visible)
        measure_draw = ImageDraw.Draw(base)
        font, lines, _, block_h = self._prepare_text_block(measure_draw, full_text, style, canvas_w, canvas_h)
        secondary_y = None
        if params.get("bilingual") and getattr(sub, "translated_text", ""):
            trans_draw = ImageDraw.Draw(Image.new("RGBA", base.size, (0, 0, 0, 0)))
            _, _, _, trans_h = self._prepare_text_block(
                trans_draw,
                sub.translated_text,
                params["secondary_style"],
                canvas_w,
                canvas_h,
            )
            y_start, secondary_y = self._resolve_bilingual_block_positions(
                canvas_w,
                canvas_h,
                style,
                block_h,
                params["secondary_style"],
                trans_h,
                swapped=params.get("position_swapped", False),
            )
        else:
            y_start, _ = self._resolve_bilingual_block_positions(canvas_w, canvas_h, style, block_h)

        new_word = newest["word"].strip()
        outline = self._hex_to_rgb(style.outline_color)
        fill = self._hex_to_rgb(style.primary_color)
        thickness = style.outline_thickness
        neighbors = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
        glow_enabled = getattr(style, "glow_enabled", False)
        glow_color = self._hex_to_rgb(getattr(style, "glow_color", "#FFFFFF"))
        glow_radius = max(8, getattr(style, "glow_radius", 8))
        shadow_enabled = getattr(style, "shadow_enabled", False)
        shadow_color = self._hex_to_rgb(getattr(style, "shadow_color", "#000000"))
        shadow_sx = getattr(style, "shadow_offset_x", 2)
        shadow_sy = getattr(style, "shadow_offset_y", 2)
        shadow_blur = getattr(style, "shadow_blur", 0)
        fake_bold = getattr(font, "_fake_bold", False)

        def _fb_seg(draw, xy, text, font_obj, color):
            draw.text(xy, text, font=font_obj, fill=color)
            if fake_bold:
                draw.text((xy[0] + 1, xy[1]), text, font=font_obj, fill=color)

        text_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))

        def draw_seg(text, x, y, seg_alpha):
            alpha = int(max(0, min(1.0, seg_alpha)) * 255)
            if alpha == 0:
                return
            if shadow_enabled:
                shadow_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
                shadow_draw = ImageDraw.Draw(shadow_layer)
                _fb_seg(shadow_draw, (x + shadow_sx, y + shadow_sy), text, font, (*shadow_color, int(alpha * 220 / 255)))
                if shadow_blur > 0:
                    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(shadow_blur))
                text_layer.alpha_composite(shadow_layer)
            if glow_enabled:
                text_mask = Image.new("L", base.size, 0)
                glow_draw = ImageDraw.Draw(text_mask)
                glow_draw.text((x, y), text, font=font, fill=255)
                if fake_bold:
                    glow_draw.text((x + 1, y), text, font=font, fill=255)
                fill_blur = max(3, glow_radius // 2)
                filled_mask = text_mask.filter(ImageFilter.GaussianBlur(fill_blur))
                filled_mask = filled_mask.point(lambda p: 255 if p > 20 else 0)
                outer_alpha = ImageChops.subtract(text_mask.filter(ImageFilter.GaussianBlur(glow_radius)), filled_mask)
                outer_alpha = outer_alpha.point(lambda p: min(255, int(p * 2 * seg_alpha)))
                glow_layer = Image.merge("RGBA", (
                    Image.new("L", base.size, glow_color[0]),
                    Image.new("L", base.size, glow_color[1]),
                    Image.new("L", base.size, glow_color[2]),
                    outer_alpha,
                ))
                text_layer.alpha_composite(glow_layer)
            text_draw = ImageDraw.Draw(text_layer)
            if thickness > 0:
                for dx, dy in neighbors:
                    _fb_seg(text_draw, (x + dx * thickness, y + dy * thickness), text, font, (*outline, alpha))
            _fb_seg(text_draw, (x, y), text, font, (*fill, alpha))

        current_y = y_start
        for line_idx, (line_text, line_w, line_h) in enumerate(lines):
            line_x = (canvas_w - line_w) // 2
            is_last = line_idx == len(lines) - 1
            if not is_last:
                draw_seg(line_text, line_x, current_y, history_dim)
            else:
                if new_word and line_text.endswith(new_word):
                    prefix = line_text[:len(line_text) - len(new_word)].rstrip()
                    if prefix:
                        draw_seg(prefix, line_x, current_y, history_dim)
                        prefix_adv = measure_draw.textbbox((0, 0), prefix + " ", font=font)[2] - measure_draw.textbbox((0, 0), prefix + " ", font=font)[0]
                        new_x = line_x + prefix_adv
                    else:
                        new_x = line_x
                    draw_seg(new_word, new_x, current_y, entry_alpha)
                else:
                    draw_seg(line_text, line_x, current_y, history_dim)
            current_y += line_h + 2

        if getattr(font, "_fake_italic", False):
            text_layer = self._shear_italic(text_layer, y_start + block_h // 2)
        result = Image.alpha_composite(base, text_layer)
        result = self._draw_bilingual_translation(
            result,
            sub,
            params,
            primary_bottom_y=y_start + block_h,
            absolute_y=secondary_y,
        )
        return result if orig_mode == "RGBA" else result.convert(orig_mode)

    def _get_karaoke_words(self, sub) -> list[dict]:
        if getattr(sub, "words", None):
            return [{"word": w.word, "start": float(w.start), "end": float(w.end)} for w in sub.words]

        text = (getattr(sub, "original_text", "") or "").strip()
        tokens = text.split()
        if not tokens:
            return []

        start = float(getattr(sub, "start", 0.0))
        end = float(getattr(sub, "end", start + 0.001))
        duration = max(0.001, end - start)
        step = duration / max(1, len(tokens))
        fallback = []
        for index, token in enumerate(tokens):
            w_start = start + index * step
            w_end = end if index == len(tokens) - 1 else min(end, w_start + step)
            fallback.append({"word": token, "start": w_start, "end": w_end})
        return fallback

    @staticmethod
    def _tokenize_for_wrap(text: str) -> list[tuple[str, bool]]:
        import unicodedata

        def _is_cjk(ch: str) -> bool:
            return unicodedata.category(ch).startswith("Lo")

        tokens = []
        for index, word in enumerate(text.split()):
            needs_space = index > 0
            if any(_is_cjk(ch) for ch in word):
                buffer = ""
                for ch in word:
                    if _is_cjk(ch):
                        if buffer:
                            tokens.append((buffer, needs_space))
                            needs_space = False
                            buffer = ""
                        tokens.append((ch, needs_space))
                        needs_space = False
                    else:
                        buffer += ch
                if buffer:
                    tokens.append((buffer, needs_space))
            else:
                tokens.append((word, needs_space))
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
                    line_bbox = draw.textbbox((0, 0), current_line, font=font)
                    lines.append((current_line, line_bbox[2] - line_bbox[0], line_bbox[3] - line_bbox[1]))
                current_line = token_text
        if current_line:
            line_bbox = draw.textbbox((0, 0), current_line, font=font)
            lines.append((current_line, line_bbox[2] - line_bbox[0], line_bbox[3] - line_bbox[1]))

        block_h = sum(line[2] for line in lines) + (len(lines) - 1) * 2
        block_w = max(line[1] for line in lines) if lines else 0
        return font, lines, block_w, block_h

    def _draw_safe_width_guide(self, img: Image.Image, style: SubtitleStyle, alpha: float = 1.0) -> Image.Image:
        width_pct = max(0, min(100, int(getattr(style, "text_width_percent", 90))))
        if width_pct >= 100:
            return img

        width, height = img.size
        safe_w = max(1, int(width * width_pct / 100))
        left = max(0, (width - safe_w) // 2)
        right = min(width, left + safe_w)
        orig_mode = img.mode
        alpha = max(0.0, min(1.0, float(alpha)))

        if orig_mode == "RGBA":
            import numpy as np

            arr = np.array(img)
            yy, xx = np.ogrid[:height, :width]
            checker = ((xx + yy) % 3 != 0)
            if alpha < 1.0:
                checker = checker & (((xx * 7 + yy * 13) % 100) < int(alpha * 100))
            if left > 0:
                mask = checker[:, :left]
                arr[:height, :left, 0] = np.where(mask, 0, arr[:height, :left, 0])
                arr[:height, :left, 1] = np.where(mask, 0, arr[:height, :left, 1])
                arr[:height, :left, 2] = np.where(mask, 0, arr[:height, :left, 2])
                arr[:height, :left, 3] = np.where(mask, 255, arr[:height, :left, 3])
            if right < width:
                mask = checker[:, :width - right]
                arr[:height, right:, 0] = np.where(mask, 0, arr[:height, right:, 0])
                arr[:height, right:, 1] = np.where(mask, 0, arr[:height, right:, 1])
                arr[:height, right:, 2] = np.where(mask, 0, arr[:height, right:, 2])
                arr[:height, right:, 3] = np.where(mask, 255, arr[:height, right:, 3])
            if left > 0:
                x0, x1 = max(0, left - 1), min(width, left + 1)
                arr[:, x0:x1, 0] = 255
                arr[:, x0:x1, 1] = 255
                arr[:, x0:x1, 2] = 255
                arr[:, x0:x1, 3] = 255
            if right < width:
                x0, x1 = max(0, right - 1), min(width, right + 1)
                arr[:, x0:x1, 0] = 255
                arr[:, x0:x1, 1] = 255
                arr[:, x0:x1, 2] = 255
                arr[:, x0:x1, 3] = 255
            return Image.fromarray(arr, "RGBA")

        base = img.convert("RGBA")
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        shadow_alpha = int(35 * alpha)
        line_alpha = int(95 * alpha)
        if left > 0:
            draw.rectangle([0, 0, left, height], fill=(0, 0, 0, shadow_alpha))
            draw.line([(left, 0), (left, height)], fill=(255, 255, 255, line_alpha), width=2)
        if right < width:
            draw.rectangle([right, 0, width, height], fill=(0, 0, 0, shadow_alpha))
            draw.line([(right, 0), (right, height)], fill=(255, 255, 255, line_alpha), width=2)
        result = Image.alpha_composite(base, overlay)
        return result.convert(orig_mode)

    def _hex_to_rgb(self, hex_color: str) -> tuple[int, int, int]:
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
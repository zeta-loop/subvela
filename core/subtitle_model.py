from dataclasses import dataclass, field, fields
import difflib


@dataclass
class WordEntry:
    word: str
    start: float
    end: float


@dataclass
class SubtitleAnimation:
    karaoke_mode: str = "off"
    animation_style: str = "none"
    translation_animation_style: str = "none"
    transition_duration: float = 0.30
    karaoke_highlight_color: str = "#FFFF00"
    highlight_dimmed_opacity: float = 0.5
    bounce_trail_count: int = 3
    bounce_min_chars: int = 3
    sweep_entry_style: str = "instant"
    sweep_history_dim: float = 1.0
    highlight_active_marker: str = "color"
    highlight_history_on: bool = False

    def to_dict(self) -> dict:
        return {
            "karaoke_mode": self.karaoke_mode,
            "animation_style": self.animation_style,
            "translation_animation_style": self.translation_animation_style,
            "transition_duration": self.transition_duration,
            "karaoke_highlight_color": self.karaoke_highlight_color,
            "highlight_dimmed_opacity": self.highlight_dimmed_opacity,
            "bounce_trail_count": self.bounce_trail_count,
            "bounce_min_chars": self.bounce_min_chars,
            "sweep_entry_style": self.sweep_entry_style,
            "sweep_history_dim": self.sweep_history_dim,
            "highlight_active_marker": self.highlight_active_marker,
            "highlight_history_on": self.highlight_history_on,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SubtitleAnimation":
        valid_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


@dataclass
class SubtitleEntry:
    index: int
    start: float  # seconds
    end: float    # seconds
    original_text: str = ""
    translated_text: str = ""
    words: list[WordEntry] = field(default_factory=list)
    style_override: "SubtitleStyle | None" = None
    primary_style_override: "SubtitleStyle | None" = None
    secondary_style_override: "SubtitleStyle | None" = None
    animation_override: SubtitleAnimation | None = None

    def duration(self) -> float:
        return self.end - self.start


@dataclass
class SubtitleStyle:
    font_family: str = "Arial"
    font_size: int = 48
    primary_color: str = "#FFFFFF"
    outline_color: str = "#000000"
    outline_thickness: int = 2
    bold: bool = False
    italic: bool = False
    background_enabled: bool = False
    background_color: str = "#000000"
    background_opacity: float = 0.5
    position: str = "bottom"  # "top", "center", "bottom"
    position_offset: int = 0   # vertical offset % of image height, -50..+50
    position_y_percent: int = 85  # absolute vertical position 0..100 (bottom baseline)
    shadow_enabled: bool = False
    shadow_color: str = "#000000"
    shadow_blur: int = 0        # 0 = hard shadow; >0 = Gaussian blur radius
    shadow_offset_x: int = 2
    shadow_offset_y: int = 2
    glow_enabled: bool = False
    glow_color: str = "#FFFFFF"
    glow_radius: int = 5        # Gaussian blur radius for glow
    text_width_percent: int = 90  # 0..100 usable width for subtitle wrapping

    def to_dict(self) -> dict:
        return {
            "font_family": self.font_family,
            "font_size": self.font_size,
            "primary_color": self.primary_color,
            "outline_color": self.outline_color,
            "outline_thickness": self.outline_thickness,
            "bold": self.bold,
            "italic": self.italic,
            "background_enabled": self.background_enabled,
            "background_color": self.background_color,
            "background_opacity": self.background_opacity,
            "position": self.position,
            "position_offset": self.position_offset,
            "position_y_percent": self.position_y_percent,
            "shadow_enabled": self.shadow_enabled,
            "shadow_color": self.shadow_color,
            "shadow_blur": self.shadow_blur,
            "shadow_offset_x": self.shadow_offset_x,
            "shadow_offset_y": self.shadow_offset_y,
            "glow_enabled": self.glow_enabled,
            "glow_color": self.glow_color,
            "glow_radius": self.glow_radius,
            "text_width_percent": self.text_width_percent,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SubtitleStyle":
        valid_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in d.items() if k in valid_fields}
        return cls(**filtered)


def _ratio_distribute(tokens: list[str], t_start: float, t_end: float) -> list[WordEntry]:
    """Distribute a time range across tokens proportionally by character length."""
    if not tokens:
        return []
    total_chars = sum(len(t) for t in tokens) or 1
    duration = max(0.0, t_end - t_start)
    result = []
    cur = t_start
    for tok in tokens:
        span = duration * (len(tok) / total_chars)
        result.append(WordEntry(word=tok, start=round(cur, 3), end=round(cur + span, 3)))
        cur += span
    return result


def remap_word_timestamps(
    old_words: list[WordEntry],
    new_text: str,
    sub_start: float,
    sub_end: float,
) -> list[WordEntry]:
    """
    Remap word timestamps after a subtitle text edit.

    Strategy:
    - Use SequenceMatcher to align new tokens to old tokens.
    - Equal blocks: new word inherits the matched old word's timestamps directly.
    - Replace/insert blocks: the old words' combined time range is redistributed
      across the new words by character-length ratio.
    - Delete blocks: old words dropped, no new words emitted.
    - Fallback: if fewer than 30% of old characters were matched, the alignment
      is too ambiguous — redistribute the whole subtitle span by ratio instead.
    """
    new_tokens = new_text.split()
    if not new_tokens:
        return []
    if not old_words:
        return _ratio_distribute(new_tokens, sub_start, sub_end)

    old_tokens = [w.word.strip() for w in old_words]

    # Case-insensitive matching so "Julie" == "julie"
    matcher = difflib.SequenceMatcher(
        None,
        [t.lower() for t in old_tokens],
        [t.lower() for t in new_tokens],
        autojunk=False,
    )

    # Check match quality: fraction of original characters that found a match
    matched_chars = sum(
        sum(len(old_tokens[i1 + k]) for k in range(size))
        for i1, _, size in matcher.get_matching_blocks()
        if size > 0
    )
    total_old_chars = sum(len(t) for t in old_tokens) or 1
    if matched_chars / total_old_chars < 0.30:
        return _ratio_distribute(new_tokens, sub_start, sub_end)

    result: list[WordEntry] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        old_slice = old_words[i1:i2]
        new_slice = new_tokens[j1:j2]

        if tag == "equal":
            for old_w, new_tok in zip(old_slice, new_slice):
                result.append(WordEntry(word=new_tok, start=old_w.start, end=old_w.end))

        elif tag == "replace":
            t_start = old_slice[0].start
            t_end = old_slice[-1].end
            result.extend(_ratio_distribute(new_slice, t_start, t_end))

        elif tag == "insert":
            # No old words consumed — carve time from the gap around this position.
            if result:
                t_start = result[-1].end
            else:
                t_start = sub_start
            # Next old word's start is the right boundary (i1 == i2 for insert)
            t_end = old_words[i1].start if i1 < len(old_words) else sub_end
            # If gap is zero or negative, borrow a sliver from surrounding words
            if t_end <= t_start:
                t_end = t_start + 0.05 * len(new_slice)
            result.extend(_ratio_distribute(new_slice, t_start, t_end))

        # tag == "delete": old words removed, nothing added to result

    return result

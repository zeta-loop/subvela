import copy
import math
import os
import shutil
import subprocess
import tempfile
import threading
from collections import deque
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image

from core.subtitle_model import SubtitleAnimation
from core.subtitle_renderer import SubtitleOverlayRenderer, build_render_params
from core.paths import get_ffmpeg, get_ffprobe


QUALITY_PRESETS = {
    "High quality": {"crf": "18", "preset": "slow"},
    "Balanced": {"crf": "23", "preset": "medium"},
    "Faster export": {"crf": "28", "preset": "fast"},
}

OVERLAY_PROGRESS_WEIGHT = 0.80

ENCODER_PRESETS = {
    "None (CPU)": {"codec": "libx264", "kind": "cpu"},
    "NVIDIA GPU": {"codec": "h264_nvenc", "kind": "nvidia"},
    "AMD GPU": {"codec": "h264_amf", "kind": "amd"},
    "Apple Silicon / Mac": {"codec": "h264_videotoolbox", "kind": "videotoolbox"},
}

HW_ENCODER_QUALITY = {
    "High quality": {"cq": "18", "nvenc_preset": "p5", "bitrate": "12M", "maxrate": "18M", "bufsize": "24M"},
    "Balanced": {"cq": "23", "nvenc_preset": "p4", "bitrate": "8M", "maxrate": "12M", "bufsize": "16M"},
    "Faster export": {"cq": "28", "nvenc_preset": "p3", "bitrate": "5M", "maxrate": "8M", "bufsize": "10M"},
}


@dataclass
class _BurnRenderState:
    video_path: str
    video_info: dict
    subtitles: list
    primary_style: object
    secondary_style: object
    bilingual: bool
    position_swapped: bool
    karaoke_mode: str
    animation_style: str
    translation_animation_style: str
    transition_duration: float
    karaoke_highlight_color: str
    highlight_dimmed_opacity: float
    bounce_trail_count: int
    bounce_min_chars: int
    sweep_entry_style: str
    sweep_history_dim: float
    highlight_active_marker: str
    highlight_history_on: bool
    _active_width_style_key: str = "primary"

    def get_primary_style_for_subtitle(self, sub):
        if sub is None:
            return self.primary_style
        override = getattr(sub, "primary_style_override", None)
        if override is not None:
            return override
        legacy_override = getattr(sub, "style_override", None)
        if legacy_override is not None:
            return legacy_override
        return self.primary_style

    def get_secondary_style_for_subtitle(self, sub):
        if sub is None:
            return self.secondary_style
        override = getattr(sub, "secondary_style_override", None)
        if override is not None:
            return override
        return self.secondary_style

    def get_style_for_subtitle(self, sub):
        return self.get_primary_style_for_subtitle(sub)

    def get_animation_settings_for_subtitle(self, sub=None):
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
        override = getattr(sub, "animation_override", None) if sub is not None else None
        if override is not None:
            for key, value in override.to_dict().items():
                setattr(settings, key, value)
        return settings


class _OverlayAssetWriter:
    def __init__(self, state: _BurnRenderState, output_dir: str, width: int, height: int,
                 progress_callback=None, total_frames: int = 0):
        self.state = state
        self.output_dir = output_dir
        self.width = width
        self.height = height
        self.renderer = SubtitleOverlayRenderer(video_info=state.video_info)
        self.progress_callback = progress_callback
        self.total_frames = max(0, total_frames)
        self.rendered_frames = 0
        self.frame_index = 0
        self.transparent_path = os.path.join(output_dir, "transparent.png")
        Image.new("RGBA", (width, height), (0, 0, 0, 0)).save(self.transparent_path)

    def render_frame(self, subtitle, sample_time: float, label: str) -> str:
        self.frame_index += 1
        params = build_render_params(
            self.state,
            sample_time,
            subtitle,
            self.width,
            self.height,
            is_playing=True,
            safe_area_alpha=0.0,
        )
        image = self.renderer.render_overlay(self.width, self.height, subtitle, params)
        filename = f"frame_{self.frame_index:06d}_{label}.png"
        path = os.path.join(self.output_dir, filename)
        image.save(path)
        self.rendered_frames += 1
        if self.progress_callback and self.total_frames > 0:
            self.progress_callback(min(self.rendered_frames / self.total_frames, 1.0))
        return path


def check_ffmpeg() -> bool:
    try:
        subprocess.run([get_ffmpeg(), "-version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def burn_subtitles(state, output_path: str,
                   quality_preset: str = "Balanced",
                   video_encoder: str = "None (CPU)",
                   include_translations: bool = True,
                   on_progress=None, on_complete=None, on_error=None):
    snapshot = _snapshot_state(state, include_translations)
    thread = threading.Thread(
        target=_burn_worker,
        args=(snapshot, output_path, quality_preset, video_encoder, on_progress, on_complete, on_error),
        daemon=True,
    )
    thread.start()
    return thread


def _snapshot_state(state, include_translations: bool) -> _BurnRenderState:
    return _BurnRenderState(
        video_path=state.video_path,
        video_info=copy.deepcopy(state.video_info),
        subtitles=copy.deepcopy(state.subtitles),
        primary_style=copy.deepcopy(state.primary_style),
        secondary_style=copy.deepcopy(state.secondary_style),
        bilingual=bool(state.bilingual and include_translations),
        position_swapped=bool(getattr(state, "position_swapped", False)),
        karaoke_mode=getattr(state, "karaoke_mode", "off"),
        animation_style=getattr(state, "animation_style", "none"),
        translation_animation_style=getattr(state, "translation_animation_style", "none"),
        transition_duration=float(getattr(state, "transition_duration", 0.30)),
        karaoke_highlight_color=getattr(state, "karaoke_highlight_color", "#FFFF00"),
        highlight_dimmed_opacity=float(getattr(state, "highlight_dimmed_opacity", 0.5)),
        bounce_trail_count=int(getattr(state, "bounce_trail_count", 3)),
        bounce_min_chars=int(getattr(state, "bounce_min_chars", 3)),
        sweep_entry_style=getattr(state, "sweep_entry_style", "instant"),
        sweep_history_dim=float(getattr(state, "sweep_history_dim", 1.0)),
        highlight_active_marker=getattr(state, "highlight_active_marker", "color"),
        highlight_history_on=bool(getattr(state, "highlight_history_on", False)),
    )


def _burn_worker(state: _BurnRenderState, output_path: str, quality_preset: str,
                 video_encoder: str,
                 on_progress, on_complete, on_error):
    temp_dir = None
    try:
        duration = float(state.video_info.get("duration") or _get_duration(state.video_path) or 0.0)
        width, height = _get_dimensions(state)
        fps = _get_fps(state)

        temp_dir = tempfile.mkdtemp(prefix="subtitle_overlay_")
        _emit_progress(on_progress, 0.0, "Rendering subtitle overlays... 0%")
        schedule_path = _build_overlay_schedule(
            state, temp_dir, width, height, fps, duration,
            on_render_progress=lambda ratio: _emit_progress(
                on_progress,
                _map_overlay_progress(ratio),
                f"Rendering subtitle overlays... {int(_map_overlay_progress(ratio) * 100)}%",
            ),
        )
        _emit_progress(on_progress, OVERLAY_PROGRESS_WEIGHT, f"Encoding video... {int(OVERLAY_PROGRESS_WEIGHT * 100)}%")

        selected_encoder = video_encoder if video_encoder in ENCODER_PRESETS else "None (CPU)"
        available, message = check_encoder_available(selected_encoder)
        if not available:
            if on_error:
                on_error(message)
            return

        returncode, stderr = _run_ffmpeg_command(
            _build_ffmpeg_command(state, schedule_path, output_path, selected_encoder, quality_preset),
            duration,
            on_progress,
        )

        if returncode == 0:
            if on_complete:
                on_complete(output_path)
        else:
            if on_error:
                on_error(_build_ffmpeg_error_message(selected_encoder, returncode, stderr))
    except Exception as exc:
        if on_error:
            on_error(str(exc))
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


def check_encoder_available(video_encoder: str) -> tuple[bool, str]:
    selected_encoder = video_encoder if video_encoder in ENCODER_PRESETS else "None (CPU)"
    encoder = ENCODER_PRESETS[selected_encoder]

    if encoder["kind"] == "cpu":
        if check_ffmpeg():
            return True, ""
        return False, "FFmpeg executable not found. Please ensure FFmpeg is installed and in your PATH."

    return _probe_hardware_encoder(selected_encoder, encoder["codec"])


@lru_cache(maxsize=None)
def _probe_hardware_encoder(label: str, codec: str) -> tuple[bool, str]:
    cmd = [
        get_ffmpeg(), "-v", "error",
        "-f", "lavfi",
        "-i", "color=c=black:s=128x128:d=0.1:r=1",
        "-frames:v", "1",
        "-an",
        "-c:v", codec,
        "-f", "null",
        "-",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except FileNotFoundError:
        return False, "FFmpeg executable not found. Please ensure FFmpeg is installed and in your PATH."
    except subprocess.TimeoutExpired:
        return False, f"{label} check timed out. The hardware encoder could not be verified."

    if result.returncode == 0:
        return True, ""

    stderr = (result.stderr or result.stdout or "").strip()
    normalized = stderr.lower()
    if "unknown encoder" in normalized or "encoder not found" in normalized:
        return False, f"{label} encoder is not available in this FFmpeg build."
    if any(token in normalized for token in [
        "no device",
        "cannot load",
        "no capable devices found",
        "device creation failed",
        "unsupported device",
        "not available",
    ]):
        return False, f"{label} not found on this system."
    return False, f"{label} is unavailable on this system."


def _build_ffmpeg_error_message(video_encoder: str, returncode: int, stderr: str) -> str:
    if video_encoder != "None (CPU)":
        available, message = check_encoder_available(video_encoder)
        if not available:
            return message
    return f"FFmpeg error (code {returncode}): {stderr[:700]}"


def _build_overlay_schedule(state: _BurnRenderState, temp_dir: str,
                            width: int, height: int, fps: float, duration: float,
                            on_render_progress=None) -> str:
    total_frames = _estimate_overlay_render_count(state, fps, duration)
    writer = _OverlayAssetWriter(state, temp_dir, width, height, on_render_progress, total_frames)
    entries = []
    current_time = 0.0

    subtitles = sorted(state.subtitles, key=lambda sub: (float(sub.start), float(sub.end)))
    for subtitle in subtitles:
        start = max(0.0, float(subtitle.start))
        end = float(subtitle.end)
        if duration > 0:
            end = min(duration, end)
        if end <= start:
            continue

        if start > current_time + 1e-6:
            entries.append((writer.transparent_path, start - current_time))

        entries.extend(_build_subtitle_entries(writer, subtitle, fps))
        current_time = max(current_time, end)

    total_duration = duration if duration > 0 else current_time
    if total_duration > current_time + 1e-6:
        entries.append((writer.transparent_path, total_duration - current_time))
    if not entries:
        entries.append((writer.transparent_path, max(total_duration, 0.05)))

    schedule_path = os.path.join(temp_dir, "schedule.txt")
    with open(schedule_path, "w", encoding="utf-8") as handle:
        for path, seg_duration in entries:
            if seg_duration <= 1e-6:
                continue
            normalized = path.replace("\\", "/").replace("'", "'\\''")
            handle.write(f"file '{normalized}'\n")
            handle.write(f"duration {seg_duration:.6f}\n")
        last_path = entries[-1][0].replace("\\", "/").replace("'", "'\\''")
        handle.write(f"file '{last_path}'\n")
    return schedule_path


def _build_subtitle_entries(writer: _OverlayAssetWriter, subtitle, fps: float):
    anim = writer.state.get_animation_settings_for_subtitle(subtitle)
    start = max(0.0, float(subtitle.start))
    end = max(start, float(subtitle.end))

    if anim.karaoke_mode != "off" or anim.animation_style in {"fade", "typewriter"} or anim.translation_animation_style in {"fade", "typewriter"}:
        return _sample_interval(writer, subtitle, start, end, fps, "full")

    if anim.animation_style in {"pop", "slide_up"} or anim.translation_animation_style in {"pop", "slide_up"}:
        burst_end = min(end, start + max(1.0 / fps, anim.transition_duration))
        entries = _sample_interval(writer, subtitle, start, burst_end, fps, "burst")
        if end > burst_end + 1e-6:
            hold_path = writer.render_frame(subtitle, _segment_sample_time(burst_end, end), "hold")
            entries.append((hold_path, end - burst_end))
        return entries

    hold_path = writer.render_frame(subtitle, _segment_sample_time(start, end), "static")
    return [(hold_path, end - start)]


def _sample_interval(writer: _OverlayAssetWriter, subtitle, start: float, end: float,
                     fps: float, label: str):
    entries = []
    frame_step = max(1.0 / max(fps, 1.0), 1 / 120)
    frame_index = 0
    t = start
    while t < end - 1e-6:
        next_t = min(end, t + frame_step)
        sample_time = _segment_sample_time(t, next_t)
        frame_path = writer.render_frame(subtitle, sample_time, f"{label}_{frame_index:04d}")
        entries.append((frame_path, next_t - t))
        t = next_t
        frame_index += 1
    return entries


def _segment_sample_time(start: float, end: float) -> float:
    duration = max(0.0, end - start)
    if duration <= 0.0:
        return start
    return start + duration * 0.5 - min(0.0005, duration * 0.1)


def _estimate_overlay_render_count(state: _BurnRenderState, fps: float, duration: float) -> int:
    total = 0
    subtitles = sorted(state.subtitles, key=lambda sub: (float(sub.start), float(sub.end)))
    for subtitle in subtitles:
        start = max(0.0, float(subtitle.start))
        end = float(subtitle.end)
        if duration > 0:
            end = min(duration, end)
        if end <= start:
            continue
        total += _count_subtitle_render_frames(state, subtitle, start, end, fps)
    return max(total, 1)


def _count_subtitle_render_frames(state: _BurnRenderState, subtitle, start: float, end: float, fps: float) -> int:
    anim = state.get_animation_settings_for_subtitle(subtitle)
    if anim.karaoke_mode != "off" or anim.animation_style in {"fade", "typewriter"} or anim.translation_animation_style in {"fade", "typewriter"}:
        return _count_sample_interval_frames(start, end, fps)

    if anim.animation_style in {"pop", "slide_up"} or anim.translation_animation_style in {"pop", "slide_up"}:
        burst_end = min(end, start + max(1.0 / fps, anim.transition_duration))
        total = _count_sample_interval_frames(start, burst_end, fps)
        if end > burst_end + 1e-6:
            total += 1
        return total

    return 1


def _count_sample_interval_frames(start: float, end: float, fps: float) -> int:
    frame_step = max(1.0 / max(fps, 1.0), 1 / 120)
    duration = max(0.0, end - start)
    if duration <= 1e-6:
        return 0
    return max(1, math.ceil(duration / frame_step))


def _map_overlay_progress(ratio: float) -> float:
    return max(0.0, min(OVERLAY_PROGRESS_WEIGHT * ratio, OVERLAY_PROGRESS_WEIGHT))


def _map_encode_progress(ratio: float) -> float:
    return OVERLAY_PROGRESS_WEIGHT + max(0.0, min(ratio, 1.0)) * (1.0 - OVERLAY_PROGRESS_WEIGHT)


def _emit_progress(on_progress, value: float, status: str | None = None):
    if not on_progress:
        return
    try:
        on_progress(value, status)
    except TypeError:
        on_progress(value)


def _build_ffmpeg_command(state: _BurnRenderState, schedule_path: str, output_path: str,
                          video_encoder: str, quality_preset: str) -> list[str]:
    encoder_args = _get_encoder_args(video_encoder, quality_preset)
    return [
        get_ffmpeg(), "-y",
        "-i", state.video_path,
        "-f", "concat",
        "-safe", "0",
        "-i", schedule_path,
        "-filter_complex", "[0:v]format=rgb24[bg];[1:v]format=rgba[ov];[bg][ov]overlay=0:0:format=rgb:shortest=1[v]",
        "-map", "[v]",
        "-map", "0:a?",
        *encoder_args,
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-c:a", "copy",
        "-progress", "pipe:1",
        output_path,
    ]


def _get_encoder_args(video_encoder: str, quality_preset: str) -> list[str]:
    encoder = ENCODER_PRESETS.get(video_encoder, ENCODER_PRESETS["None (CPU)"])
    cpu_preset = QUALITY_PRESETS.get(quality_preset, QUALITY_PRESETS["Balanced"])
    hw_preset = HW_ENCODER_QUALITY.get(quality_preset, HW_ENCODER_QUALITY["Balanced"])

    if encoder["kind"] == "cpu":
        return ["-c:v", "libx264", "-crf", cpu_preset["crf"], "-preset", cpu_preset["preset"]]
    if encoder["kind"] == "nvidia":
        return [
            "-c:v", encoder["codec"],
            "-preset", hw_preset["nvenc_preset"],
            "-rc", "vbr",
            "-cq", hw_preset["cq"],
            "-b:v", "0",
        ]
    if encoder["kind"] == "amd":
        quality = {"High quality": "quality", "Balanced": "balanced", "Faster export": "speed"}.get(quality_preset, "balanced")
        return [
            "-c:v", encoder["codec"],
            "-quality", quality,
            "-b:v", hw_preset["bitrate"],
            "-maxrate", hw_preset["maxrate"],
            "-bufsize", hw_preset["bufsize"],
        ]
    return [
        "-c:v", encoder["codec"],
        "-b:v", hw_preset["bitrate"],
        "-maxrate", hw_preset["maxrate"],
    ]


def _run_ffmpeg_command(cmd: list[str], duration: float, on_progress):
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except FileNotFoundError:
        return 127, "FFmpeg executable not found. Please ensure FFmpeg is installed and in your PATH."

    log_tail = deque(maxlen=60)
    for line in process.stdout:
        line = line.strip()
        if line:
            log_tail.append(line)
        if line.startswith("out_time_us="):
            try:
                us = int(line.split("=", 1)[1])
                if duration > 0:
                    overall = _map_encode_progress(min(us / (duration * 1_000_000), 1.0))
                    _emit_progress(on_progress, overall, f"Encoding video... {int(overall * 100)}%")
            except ValueError:
                pass

    process.wait()
    stderr = "\n".join(log_tail) if log_tail else "No FFmpeg output captured."
    return process.returncode, stderr


def _get_dimensions(state: _BurnRenderState) -> tuple[int, int]:
    width = int(state.video_info.get("width") or 0)
    height = int(state.video_info.get("height") or 0)
    if width > 0 and height > 0:
        return width, height
    try:
        result = subprocess.run(
            [
                get_ffprobe(), "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0:s=x",
                state.video_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        width_str, height_str = result.stdout.strip().split("x", 1)
        return int(width_str), int(height_str)
    except Exception:
        return 1920, 1080


def _get_fps(state: _BurnRenderState) -> float:
    fps = float(state.video_info.get("fps") or 0)
    if fps > 0:
        return fps
    try:
        result = subprocess.run(
            [
                get_ffprobe(), "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate",
                "-of", "default=noprint_wrappers=1:nokey=1",
                state.video_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        value = result.stdout.strip()
        if not value:
            return 30.0
        if "/" in value:
            num, den = value.split("/", 1)
            return float(num) / max(float(den), 1.0)
        return float(value)
    except Exception:
        return 30.0


def _get_duration(video_path: str) -> float:
    try:
        result = subprocess.run(
            [
                get_ffprobe(), "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", video_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0

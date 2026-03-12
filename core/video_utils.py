import cv2
import os
import subprocess
from PIL import Image
from core.paths import get_ffmpeg


def get_video_info(path: str) -> dict | None:
    if not os.path.isfile(path):
        return None
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return None
    try:
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 0
        return {
            "path": path,
            "filename": os.path.basename(path),
            "width": width,
            "height": height,
            "fps": fps,
            "frame_count": frame_count,
            "duration": duration,
        }
    finally:
        cap.release()


def extract_frame(path: str, time_seconds: float) -> Image.Image | None:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return None
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, time_seconds * 1000)
        ret, frame = cap.read()
        if not ret:
            return None
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(frame_rgb)
    finally:
        cap.release()


def format_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def extract_audio(video_path: str, output_path: str, format: str = "wav") -> str:
    """Extract audio from video using FFmpeg. Returns output path."""
    cmd = [
        get_ffmpeg(), "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le" if format == "wav" else "libmp3lame",
        "-ar", "16000", "-ac", "1",
        output_path,
    ]
    try:
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        result = subprocess.run(cmd, capture_output=True, text=True, startupinfo=startupinfo)
    except FileNotFoundError:
        raise RuntimeError("FFmpeg executable not found. Please ensure FFmpeg is installed and in your PATH.")

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg audio extraction failed: {result.stderr[:200]}")
    return output_path


def format_duration(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    parts = []
    if h > 0:
        parts.append(f"{h}h")
    if m > 0:
        parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)

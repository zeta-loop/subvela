import sys
import os
import re

# Ensure project root / frozen base is on path
if getattr(sys, "frozen", False):
    _project_root = sys._MEIPASS
else:
    _project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _project_root)

# Add project root to PATH so Windows can find libmpv-2.dll and ffmpeg.exe
os.environ["PATH"] = _project_root + os.pathsep + os.environ.get("PATH", "")

# Keep CPU math backends conservative in the packaged app so local translation
# does not over-allocate worker memory on mid-range Windows machines.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("MKL_DYNAMIC", "FALSE")

# Workaround: Python 3.13 platform._wmi_query() can hang indefinitely when
# the Windows WMI service is deadlocked/slow.  customtkinter → darkdetect
# triggers this on import via platform.release().  Bypass WMI so the
# platform module falls through to its fast sys.getwindowsversion() path.
import platform as _platform
_platform._wmi_query = lambda *a, **k: (_ for _ in ()).throw(OSError("WMI disabled"))

from app.app import SubtitleGeneratorApp


# ── Dev-mode auto-load (python main.py --dev) ──────────────────────────
DEV_VIDEO = os.getenv("SUBVELA_DEV_VIDEO", "").strip()
DEV_SRT = os.getenv("SUBVELA_DEV_SRT", "").strip()


def _parse_srt(path: str):
    """Minimal SRT parser → list of SubtitleEntry."""
    from core.subtitle_model import SubtitleEntry

    def _ts(s):
        h, m, sec = s.replace(",", ".").split(":")
        return int(h) * 3600 + int(m) * 60 + float(sec)

    text = open(path, encoding="utf-8-sig").read()
    entries = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        m = re.match(r"(\d[\d:,. ]+)\s*-->\s*(\d[\d:,. ]+)", lines[1])
        if not m:
            continue
        text_lines = lines[2:]
        original = text_lines[0] if text_lines else ""
        translated = text_lines[1] if len(text_lines) > 1 else ""
        entries.append(SubtitleEntry(
            index=len(entries) + 1,
            start=_ts(m.group(1).strip()),
            end=_ts(m.group(2).strip()),
            original_text=original,
            translated_text=translated,
        ))
    return entries


def _dev_autoload(app):
    """Load test video + SRT so you skip the manual import/transcribe steps."""
    from core.video_utils import get_video_info

    if not DEV_VIDEO or not DEV_SRT:
        print("[dev] Set SUBVELA_DEV_VIDEO and SUBVELA_DEV_SRT to enable --dev auto-load")
        return

    info = get_video_info(DEV_VIDEO)
    if info is None:
        print("[dev] Failed to load video:", DEV_VIDEO)
        return

    app.app_state.set_video(DEV_VIDEO, info)
    # Update the VideoPanel UI
    panel = app.panels[0]  # VideoPanel
    panel.drop_text.configure(text=f"Loaded: {info['filename']}")
    panel.drop_icon.configure(image=panel._check_icon)
    panel.info_labels["Filename"].configure(text=info["filename"])
    from core.video_utils import format_duration
    panel.info_labels["Duration"].configure(text=format_duration(info["duration"]))
    panel.info_labels["Resolution"].configure(text=f"{info['width']}x{info['height']}")
    panel.info_labels["FPS"].configure(text=f"{info['fps']:.1f}")
    panel.info_frame.grid()

    subs = _parse_srt(DEV_SRT)
    app.app_state.bilingual = True
    app.app_state.set_subtitles(subs)
    print(f"[dev] Loaded {len(subs)} subtitles from SRT (bilingual)")

    # Jump to Style panel (step 2)
    app.app_state.set_step(2)
    print("[dev] Auto-loaded video + SRT, jumped to Style panel")
# ── End dev-mode ────────────────────────────────────────────────────────


def main():
    app = SubtitleGeneratorApp()
    if "--dev" in sys.argv:
        app.after(300, lambda: _dev_autoload(app))
    app.mainloop()


if __name__ == "__main__":
    main()

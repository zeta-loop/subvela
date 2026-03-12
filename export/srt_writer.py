def format_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(entries, output_path: str, bilingual: bool = False):
    lines = []
    for entry in entries:
        lines.append(str(entry.index))
        lines.append(f"{format_srt_time(entry.start)} --> {format_srt_time(entry.end)}")

        text = entry.original_text

        if bilingual and entry.translated_text:
            lines.append(text)
            lines.append(entry.translated_text)
        else:
            lines.append(text)
        lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

"""Render styled Advanced SubStation Alpha (.ass) for burning text overlays.

Kept dependency-free and pure (style dict + events → string) so it's easy to
test and reuse for both the burned export and the downloadable sidecar.
"""
from __future__ import annotations

DEFAULT_STYLE = {
    "font_name": "Arial",
    "font_size": 48,
    "primary_color": "#FFFFFF",
    "outline_color": "#000000",
    "outline": 2.0,
    "shadow": 0.0,
    "bold": False,
    "italic": False,
    "alignment": 2,      # numpad layout: 2 = bottom-center, 8 = top-center, 5 = middle
    "margin_l": 40,
    "margin_r": 40,
    "margin_v": 40,
}


def _ass_color(hex_color: str, alpha: int = 0) -> str:
    """#RRGGBB → ASS &HAABBGGRR."""
    h = (hex_color or "#FFFFFF").lstrip("#")
    if len(h) != 6:
        h = "FFFFFF"
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def _ass_time(t: float) -> str:
    t = max(0.0, float(t))
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    cs = int(round((t - int(t)) * 100))
    if cs >= 100:
        s += 1
        cs -= 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape(text: str) -> str:
    return (text or "").replace("\\", "").replace("{", "(").replace("}", ")") \
        .replace("\r\n", "\\N").replace("\n", "\\N").strip()


def build_ass(tracks: list[dict], play_res_x: int = 1280, play_res_y: int = 720) -> str:
    """tracks: [{name, style: dict, events: [{start_s, end_s, text}]}].
    Each track becomes one [V4+] Style; its events reference it."""
    styles, events = [], []
    for i, tr in enumerate(tracks):
        st = {**DEFAULT_STYLE, **(tr.get("style") or {})}
        name = f"ov{i}"
        bold = -1 if st.get("bold") else 0
        italic = -1 if st.get("italic") else 0
        styles.append(
            f"Style: {name},{st['font_name']},{st['font_size']},"
            f"{_ass_color(st['primary_color'])},{_ass_color(st['primary_color'])},"
            f"{_ass_color(st['outline_color'])},&H64000000,"
            f"{bold},{italic},0,0,100,100,0,0,1,"
            f"{st['outline']},{st['shadow']},{st['alignment']},"
            f"{st['margin_l']},{st['margin_r']},{st['margin_v']},1")
        for ev in tr.get("events", []):
            if not (ev.get("text") or "").strip():
                continue
            events.append(
                f"Dialogue: 0,{_ass_time(ev['start_s'])},{_ass_time(ev['end_s'])},"
                f"{name},,0,0,0,,{_escape(ev['text'])}")
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {play_res_x}",
        f"PlayResY: {play_res_y}",
        "ScaledBorderAndShadow: yes",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
        *styles,
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        *events,
        "",
    ]
    return "\n".join(lines)

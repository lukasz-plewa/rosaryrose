"""PNG renderer for the rose assignment table.

The visual style closely mirrors the original ODS spreadsheet screenshots
the project replaces. The note text under the table is intentionally in
Polish - the PNG is meant to be sent to Polish-speaking rose members.
"""
from __future__ import annotations
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from .rotation import (RoseConfig, MysteryPeriod, mystery_for,
                       label_for_period, POLISH_MONTHS)

# Colour palette derived from the original spreadsheet.
COLOR_BG = (255, 255, 255)
COLOR_LP_HEADER = (220, 230, 220)
COLOR_NAME_BG = (180, 200, 170)
COLOR_NAME_CELL = (212, 226, 197)
COLOR_MYSTERY_HEADER = (210, 220, 240)
COLOR_RADOSNA = (255, 240, 215)            # accent for I Radosna (intro prayer)
COLOR_MYSTERY_CELL = (245, 245, 240)
COLOR_GRID = (40, 40, 40)
COLOR_TEXT = (0, 0, 0)
COLOR_NOTE_BG = (255, 235, 215)


@dataclass
class TableStyle:
    lp_col_width: int = 60
    name_col_width: int = 280
    mystery_col_width: int = 150
    row_height: int = 44
    header_height: int = 64
    note_padding: int = 14
    border_width: int = 2
    inner_border_width: int = 1


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _draw_centered(draw, box: Tuple[int, int, int, int],
                   text: str, font, fill=COLOR_TEXT) -> None:
    x0, y0, x1, y1 = box
    lines = text.split("\n")
    asc, desc = font.getmetrics()
    line_h = asc + desc
    cy = (y0 + y1) // 2 - (line_h * len(lines)) // 2
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        cx = (x0 + x1) // 2 - tw // 2
        draw.text((cx, cy + i * line_h), line, font=font, fill=fill)


def render_table(cfg: RoseConfig, periods: List[MysteryPeriod],
                 include_note: bool = True,
                 style: Optional[TableStyle] = None) -> bytes:
    """Renders the table to PNG bytes (as bytes, not a file, for HTTP responses)."""
    style = style or TableStyle()
    n = len(periods)

    title_lines = []
    if cfg.name:
        title_lines.append(cfg.name)
        if cfg.subtitle:
            title_lines.append(cfg.subtitle)
    title_h = 28 * len(title_lines) + 16 if title_lines else 0

    total_width = (style.lp_col_width + style.name_col_width
                   + n * style.mystery_col_width + 2 * style.border_width)
    table_h = style.header_height + 20 * style.row_height + 2 * style.border_width

    font_title = _font(22, bold=True)
    font_header = _font(15, bold=True)
    font_lp = _font(15)
    font_name = _font(17, bold=True)
    font_mystery = _font(14)
    font_note = _font(13)

    # Polish notes printed under the table - this is user-facing artifact.
    note_text_1 = "Uwaga: Zmiana tajemnicy następuje dzień po spotkaniu OZM każdego miesiąca."
    if cfg.excluded_months:
        names = ", ".join(POLISH_MONTHS[m].lower() for m in cfg.excluded_months)
        note_text_1 += f" W wakacje ({names}) nie zmieniamy tajemnicy."
    note_text_2 = ("Osoba, która odmawia I tajemnicę Radosną w danym miesiącu odmawia "
                   "również modlitwę wstępną: Wierzę w Boga / Ojcze nasz / "
                   "3 × Zdrowaś Maryjo / Chwała Ojcu.")

    note_h = 0
    if include_note:
        # Dry-run wrap to compute the required height.
        tmp = Image.new("RGB", (10, 10), COLOR_BG)
        td = ImageDraw.Draw(tmp)
        max_w = total_width - style.lp_col_width - 2 * style.note_padding

        def count_lines(text: str) -> int:
            words = text.split(" ")
            line = ""
            n_lines = 0
            for w in words:
                trial = (line + " " + w).strip()
                if td.textbbox((0, 0), trial, font=font_note)[2] > max_w:
                    n_lines += 1; line = w
                else:
                    line = trial
            if line: n_lines += 1
            return n_lines

        note_h = (count_lines(note_text_1) + count_lines(note_text_2)) * 22 + 8 + 2 * style.note_padding + 12

    total_height = title_h + table_h + note_h + 20
    img = Image.new("RGB", (total_width + 40, total_height), COLOR_BG)
    draw = ImageDraw.Draw(img)
    ox, oy = 20, 10

    if title_lines:
        ly = oy + 4
        for line in title_lines:
            bbox = draw.textbbox((0, 0), line, font=font_title)
            tw = bbox[2] - bbox[0]
            tx = ox + max(0, (total_width - tw) // 2)
            draw.text((tx, ly), line, font=font_title, fill=COLOR_TEXT)
            ly += 28
        oy += title_h

    table_x0, table_y0 = ox, oy
    table_x1 = table_x0 + total_width
    table_y1 = table_y0 + table_h
    lp_x0 = table_x0
    name_x0 = lp_x0 + style.lp_col_width
    myst_x0 = name_x0 + style.name_col_width
    header_y1 = table_y0 + style.header_height

    draw.rectangle([lp_x0, table_y0, name_x0, header_y1], fill=COLOR_LP_HEADER)
    draw.rectangle([name_x0, table_y0, myst_x0, header_y1], fill=COLOR_NAME_BG)
    _draw_centered(draw, (name_x0, table_y0, myst_x0, header_y1), "Nazwisko Imię", font_header)

    for i, p in enumerate(periods):
        cx0 = myst_x0 + i * style.mystery_col_width
        cx1 = cx0 + style.mystery_col_width
        draw.rectangle([cx0, table_y0, cx1, header_y1], fill=COLOR_MYSTERY_HEADER)
        _draw_centered(draw, (cx0, table_y0, cx1, header_y1),
                       label_for_period(p, cfg.excluded_months), font_header)

    for row in range(20):
        pos = row + 1
        ry0 = header_y1 + row * style.row_height
        ry1 = ry0 + style.row_height
        draw.rectangle([lp_x0, ry0, name_x0, ry1], fill=COLOR_NAME_CELL)
        _draw_centered(draw, (lp_x0, ry0, name_x0, ry1), str(pos), font_lp)

        person = cfg.people[row] if row < len(cfg.people) else ""
        draw.rectangle([name_x0, ry0, myst_x0, ry1], fill=COLOR_NAME_CELL)
        if person:
            asc, desc = font_name.getmetrics()
            ty = (ry0 + ry1) // 2 - (asc + desc) // 2
            draw.text((name_x0 + 14, ty), person, font=font_name, fill=COLOR_TEXT)

        for i, p in enumerate(periods):
            cx0 = myst_x0 + i * style.mystery_col_width
            cx1 = cx0 + style.mystery_col_width
            m = mystery_for(pos, p.cycle_index)
            cell_bg = COLOR_RADOSNA if m == "I Radosna" else COLOR_MYSTERY_CELL
            draw.rectangle([cx0, ry0, cx1, ry1], fill=cell_bg)
            _draw_centered(draw, (cx0, ry0, cx1, ry1), m, font_mystery)

    # Grid lines on top
    for w in range(style.border_width):
        draw.rectangle([table_x0 + w, table_y0 + w, table_x1 - w - 1, table_y1 - w - 1], outline=COLOR_GRID)
    draw.line([(table_x0, header_y1), (table_x1, header_y1)], fill=COLOR_GRID, width=style.border_width)
    draw.line([(name_x0, table_y0), (name_x0, table_y1)], fill=COLOR_GRID, width=style.inner_border_width)
    draw.line([(myst_x0, table_y0), (myst_x0, table_y1)], fill=COLOR_GRID, width=style.border_width)
    for i in range(1, n):
        x = myst_x0 + i * style.mystery_col_width
        draw.line([(x, table_y0), (x, table_y1)], fill=COLOR_GRID, width=style.inner_border_width)
    for r in range(1, 20):
        y = header_y1 + r * style.row_height
        draw.line([(table_x0, y), (table_x1, y)], fill=COLOR_GRID, width=style.inner_border_width)

    if include_note:
        note_y0 = table_y1 + 16
        note_x0 = name_x0
        note_x1 = table_x1
        draw.rectangle([note_x0, note_y0, note_x1, note_y0 + note_h - 16],
                       fill=COLOR_NOTE_BG, outline=COLOR_GRID)
        max_w = note_x1 - note_x0 - 2 * style.note_padding

        def draw_wrapped(text: str, y_start: int) -> int:
            words = text.split(" ")
            line = ""
            y = y_start
            for w in words:
                trial = (line + " " + w).strip()
                if draw.textbbox((0, 0), trial, font=font_note)[2] > max_w:
                    draw.text((note_x0 + style.note_padding, y), line, font=font_note, fill=COLOR_TEXT)
                    y += 22; line = w
                else:
                    line = trial
            if line:
                draw.text((note_x0 + style.note_padding, y), line, font=font_note, fill=COLOR_TEXT)
                y += 22
            return y

        ny = draw_wrapped(note_text_1, note_y0 + style.note_padding)
        draw_wrapped(note_text_2, ny + 8)

    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()

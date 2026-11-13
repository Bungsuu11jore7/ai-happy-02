#!/usr/bin/env python3
"""ai-happy-02 entry: "A Note from Your Future Self".

A program that draws one joyful image, pixel by pixel, with the Python
standard library only, and writes it to /output/entry.png.

The idea (a fresh, specific reason to be happy, not a stock smiley or a
generic sunny scene): a letter has arrived on warm cream paper, sealed
with red wax, from the one person who knows exactly how your story ends
-- your future self. It says the hard days pass, the good ones stay, and
to keep going. A personal artifact that speaks straight to the viewer,
with clean readable type, one warm mood, readable at small size.

Deterministic: every shape is drawn from fixed coordinates with integer
math; the speckles come from a fixed-seed LCG; the PNG encoder is pure
stdlib (zlib + struct), so two runs write byte-identical files.
"""

import math
import os
import struct
import zlib

W = 1024
H = 1024

# ---------------------------------------------------------------- palette
PAPER_TOP = (255, 248, 234)     # warm cream paper
PAPER_BOTTOM = (255, 227, 179)
GLOW = (255, 214, 130)          # low sun warming the top-right corner
INK = (92, 58, 33)              # deep warm brown, body text
TITLE = (140, 47, 47)           # deep red, the headline
BORDER = (139, 94, 52)          # frame rules
HEART_RED = (214, 69, 69)
GOLD = (212, 175, 55)
SEAL = (166, 44, 44)            # wax seal
CREAM = (255, 246, 229)
SPECKLE = (232, 200, 155)


# ------------------------------------------------------------------ font
# 5x7 uppercase bitmap font. '#' is a set pixel, '.' is empty.
FONT = {
    'A': (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    'B': ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    'D': ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    'E': ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    'F': ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    'G': (".####", "#....", "#....", "#.###", "#...#", "#...#", ".###."),
    'H': ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    'I': ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"),
    'K': ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    'L': ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    'M': ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    'N': ("#...#", "##..#", "##..#", "#.#.#", "#..##", "#..##", "#...#"),
    'O': (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    'P': ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    'R': ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    'S': (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    'T': ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    'U': ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    'V': ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    'W': ("#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"),
    'Y': ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    ',': (".....", ".....", ".....", ".....", ".....", ".##..", ".#..."),
    '.': (".....", ".....", ".....", ".....", ".....", ".##..", ".##.."),
    '!': ("..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."),
    ' ': (".....", ".....", ".....", ".....", ".....", ".....", "....."),
}

HEART = (
    ".##.##.",
    "#######",
    "#######",
    ".#####.",
    "..###..",
    "...#...",
)


class Canvas:
    """An RGB canvas backed by one bytearray; shapes clip to the edges."""

    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.px = bytearray(w * h * 3)

    def fill_rect(self, x, y, w, h, color):
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.w, x + w)
        y1 = min(self.h, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(color) * (x1 - x0)
        for yy in range(y0, y1):
            o = (yy * self.w + x0) * 3
            self.px[o:o + len(row)] = row

    def set_px(self, x, y, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            o = (y * self.w + x) * 3
            self.px[o:o + 3] = bytes(color)

    def hline(self, x0, x1, y, color):
        if x1 > x0:
            self.fill_rect(x0, y, x1 - x0, 1, color)

    def disc(self, cx, cy, r, color, alpha=None, bg_row=None):
        """Filled circle. With alpha, blend over the row's background."""
        for dy in range(-r, r + 1):
            yy = cy + dy
            if yy < 0 or yy >= self.h:
                continue
            half = math.isqrt(r * r - dy * dy)
            if alpha is None:
                self.fill_rect(cx - half, yy, 2 * half + 1, 1, color)
            else:
                bg = bg_row[yy]
                blended = tuple(
                    round(bg[i] + (color[i] - bg[i]) * alpha) for i in range(3)
                )
                self.fill_rect(cx - half, yy, 2 * half + 1, 1, blended)

    def diamond(self, cx, cy, r, color):
        """Four-point sparkle."""
        for dy in range(-r, r + 1):
            half = r - abs(dy)
            self.hline(cx - half, cx + half + 1, cy + dy, color)

    def heart(self, cx, cy, scale, color):
        rows = len(HEART)
        cols = len(HEART[0])
        x0 = cx - (cols * scale) // 2
        y0 = cy - (rows * scale) // 2
        for r, line in enumerate(HEART):
            for c, bit in enumerate(line):
                if bit == '#':
                    self.fill_rect(x0 + c * scale, y0 + r * scale,
                                   scale, scale, color)


def text_width(s, scale):
    return len(s) * 6 * scale - scale


def draw_text(cv, s, cx, y, scale, color):
    x = cx - text_width(s, scale) // 2
    for ch in s:
        glyph = FONT.get(ch)
        if glyph:
            for r, line in enumerate(glyph):
                for c, bit in enumerate(line):
                    if bit == '#':
                        cv.fill_rect(x + c * scale, y + r * scale,
                                     scale, scale, color)
        x += 6 * scale


def png_bytes(rgb, w, h):
    raw = b''.join(b'\x00' + bytes(rgb[y * w * 3:(y + 1) * w * 3])
                   for y in range(h))

    def chunk(tag, data):
        return (struct.pack('>I', len(data)) + tag + data +
                struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff))

    ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) +
            chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def main():
    cv = Canvas(W, H)

    # --- paper: warm vertical gradient, one row at a time ---------------
    row_colors = []
    for y in range(H):
        t = y / (H - 1)
        row_colors.append(tuple(
            round(PAPER_TOP[i] + (PAPER_BOTTOM[i] - PAPER_TOP[i]) * t)
            for i in range(3)))
    for y in range(H):
        o = y * W * 3
        cv.px[o:o + W * 3] = bytes(row_colors[y]) * W

    # --- low sun glow, top-right corner ---------------------------------
    cv.disc(860, 140, 260, GLOW, alpha=0.14, bg_row=row_colors)
    cv.disc(860, 140, 190, GLOW, alpha=0.17, bg_row=row_colors)
    cv.disc(860, 140, 120, GLOW, alpha=0.21, bg_row=row_colors)

    # --- paper speckles, fixed-seed LCG (deterministic) -----------------
    state = 12345
    for _ in range(700):
        state = (state * 1103515245 + 12345) & 0x7fffffff
        x = 70 + state % 884
        state = (state * 1103515245 + 12345) & 0x7fffffff
        y = 70 + state % 884
        cv.set_px(x, y, SPECKLE)

    # --- double frame ----------------------------------------------------
    cv.fill_rect(36, 36, 952, 5, BORDER)
    cv.fill_rect(36, 983, 952, 5, BORDER)
    cv.fill_rect(36, 36, 5, 952, BORDER)
    cv.fill_rect(983, 36, 5, 952, BORDER)
    cv.fill_rect(54, 54, 916, 2, BORDER)
    cv.fill_rect(54, 968, 916, 2, BORDER)
    cv.fill_rect(54, 54, 2, 916, BORDER)
    cv.fill_rect(968, 54, 2, 916, BORDER)

    # --- hearts on the inner frame's corners -----------------------------
    for hx, hy in ((54, 54), (970, 54), (54, 970), (970, 970)):
        cv.heart(hx, hy, 3, HEART_RED)

    # --- sparkles ---------------------------------------------------------
    cv.diamond(150, 180, 10, GOLD)
    cv.diamond(900, 300, 8, GOLD)
    cv.diamond(120, 760, 8, GOLD)

    # --- wax seal with a heart, bottom-right ------------------------------
    cv.disc(858, 872, 54, GOLD)
    cv.disc(858, 872, 48, SEAL)
    cv.heart(858, 872, 3, CREAM)

    # --- the letter -------------------------------------------------------
    draw_text(cv, "A NOTE FROM", 512, 150, 4, INK)
    draw_text(cv, "YOUR FUTURE SELF", 512, 208, 8, TITLE)
    cv.hline(330, 470, 296, BORDER)
    cv.hline(554, 694, 296, BORDER)
    cv.heart(512, 297, 2, HEART_RED)
    body = (
        "DEAR YOU,",
        "IT ALL WORKS OUT.",
        "THE HARD DAYS PASS,",
        "THE GOOD ONES STAY.",
        "KEEP GOING!",
    )
    y = 352
    for line in body:
        draw_text(cv, line, 512, y, 5, INK)
        y += 62
    draw_text(cv, "LOVE, FUTURE YOU", 512, 690, 5, TITLE)
    draw_text(cv, "P.S. IT GETS BETTER.", 512, 782, 4, INK)

    data = png_bytes(cv.px, W, H)
    out = '/output/entry.png' if os.path.isdir('/output') else 'entry.png'
    with open(out, 'wb') as f:
        f.write(data)
    print(f"wrote {out}: {len(data)} bytes")


if __name__ == '__main__':
    main()

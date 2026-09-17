"""Byg søgbar PDF med LINJEFORANKRET usynligt tekstlag.

DocTR-ordbokse grupperes til linjeslots i y-rækkefølge; OCR-tekstens ord
fordeles brøkvist på slotsene med ægte font-metrik. Hvert ord lægges
usynligt (render_mode=3) præcis én gang: ingen overlap (overlap taber tegn
ved udtræk) og ingen overløb (enkeltord skaleres til slotbredden; sider
uden detektionsbokse får skaleret fallback der ALTID rummer alle ord).

Brug (fra repo-roden):
  python -m bookpipe.searchable_pdf <txtmappe> <jpgmappe> <ud.pdf> [p1,p2..]
  uden sidetal = alle sider. Med sidetal (fx 4,21,123) = prototype.
Verificer bagefter med bookpipe.verify_pdf — den fanger stille tab.
"""
import glob
import os
import sys

import numpy as np
import pymupdf
from PIL import Image

from doctr.io import DocumentFile
from doctr.models import detection_predictor

PAGE_W = 595.0
_DET = None


def get_det():
    global _DET
    if _DET is None:
        print("Indlæser DocTR-detektor ...")
        _DET = detection_predictor("db_resnet50", pretrained=True)
    return _DET


def detect_lines(jpg):
    """DocTR-ordbokse -> linjeslots [[x0,y0,x1,y1], ...] i y-rækkefølge."""
    W, H = Image.open(jpg).size
    res = get_det()(DocumentFile.from_images([jpg]))
    pg = res[0] if isinstance(res, list) else res.pages[0]
    arr = pg["words"] if isinstance(pg, dict) else []
    boxes = np.array([[x0 * W, y0 * H, x1 * W, y1 * H]
                      for x0, y0, x1, y1, s in arr if s >= 0.3])
    if len(boxes) == 0:
        return [], W, H
    hs = np.median(boxes[:, 3] - boxes[:, 1])
    yc = (boxes[:, 1] + boxes[:, 3]) / 2
    order = np.argsort(yc)
    lines, cur, cur_yc = [], None, None
    for i in order:
        x0, y0, x1, y1 = boxes[i]
        if cur is None or yc[i] - cur_yc > 0.8 * hs:
            cur = [x0, y0, x1, y1]
            cur_yc = yc[i]
            lines.append(cur)
        else:
            cur[0] = min(cur[0], x0)
            cur[1] = min(cur[1], y0)
            cur[2] = max(cur[2], x1)
            cur[3] = max(cur[3], y1)
            cur_yc = min(cur_yc, yc[i])
    lines.sort(key=lambda b: (b[1] + b[3]) / 2)
    return lines, W, H


SANITIZE = str.maketrans({
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u2018": "'", "\u2019": "'",
    "\u2013": "-", "\u2014": "-", "\u2026": "...", "\u00a0": " ",
    "\u2070": "0", "\u00b9": "1", "\u00b2": "2", "\u00b3": "3",
    "\u2074": "4", "\u2075": "5", "\u2076": "6", "\u2077": "7",
    "\u2078": "8", "\u2079": "9",
})


def sanitize(word):
    w = word.translate(SANITIZE)
    try:
        w.encode("latin-1")
        return w
    except UnicodeEncodeError:
        print(f"    advarsel uerstatteligt tegn i {word!r}")
        return w.encode("latin-1", "replace").decode("latin-1")


def place_fit(page, words, box, s):
    """Læg en ordgruppe i én slotboks, skaleret til boksbredden.
    Højde = slot (ingen vertikal overlap), ingen horisontal overlap.
    Glyffer kan blive små ved meget tekst — de er fortsat søgbare."""
    font = pymupdf.Font("helv")
    x0, y0, x1, y1 = [c * s for c in box]
    h = max(y1 - y0, 2.0)
    fs = h * 0.85
    base = y1 - 0.12 * h
    widths = [font.text_length(w, fontsize=fs) for w in words]
    sp = font.text_length(" ", fontsize=fs)
    total = sum(widths) + sp * (len(words) - 1)
    if total > (x1 - x0) > 0:
        fs *= (x1 - x0) / total
    x = x0
    for w in words:
        page.insert_text((x, base), w, fontsize=fs, render_mode=3)
        x += font.text_length(w, fontsize=fs) + font.text_length(
            " ", fontsize=fs)


def place_grouped(page, mlines, lines, s):
    """Fordel Mistrals linjer brøkvist på detekterede slots; flere linjer pr.
    slot flettes med mellemrum (samme slot bruges kun én gang: ingen overlap).
    Returnerer antal placerede ord."""
    groups = {}
    M, K = len(mlines), len(lines)
    for i, line in enumerate(mlines):
        bi = round(i * (K - 1) / (M - 1)) if M > 1 else 0
        groups.setdefault(bi, []).append(line)
    n = 0
    for bi, lts in groups.items():
        words = [sanitize(w) for line in lts for w in line.split()]
        place_fit(page, words, lines[bi], s)
        n += len(words)
    return n


def place_top(page, mlines, H, s):
    """Fallback til boksløse (blank) sider: stablet tekst øverst.
    Skalerer til at ALTID rumme alle ord (fast step klippede halen af
    lange sider lydløst — set på side 52 hvor sidste fodnote forsvandt):
    laget er usynligt, så små glyffer er acceptable, de er fortsat søgbare."""
    words = [sanitize(w) for line in mlines for w in line.split()]
    n = max(len(words), 1)
    step = min(7.0, (H * s - 20.0) / n)
    fs = step * 0.85
    y = 10.0
    for w in words:
        page.insert_text((10.0, y), w, fontsize=fs, render_mode=3)
        y += step


def main(argv):
    txtdir, jpgdir, out = argv[1], argv[2], argv[3]
    only = {int(x) for x in argv[4].split(",")} if len(argv) > 4 else None
    txts = sorted(glob.glob(os.path.join(txtdir, "*.txt")))
    doc = pymupdf.open()
    doc.set_metadata({"title": "bog-til-lydbog - søgbar OCR",
                      "creator": "bog-til-lydbog"})
    n_done, n_fallback, n_empty = 0, 0, 0
    for t in txts:
        stem = os.path.splitext(os.path.basename(t))[0]
        if only is not None and int(stem) not in only:
            continue
        jpg = os.path.join(jpgdir, stem + ".jpg")
        if not os.path.exists(jpg):
            print(f"  {stem}: intet billede, springer over")
            continue
        mlines = [line.strip() for line in
                  open(t, encoding="utf-8").read().splitlines()]
        mlines = [line for line in mlines if line]
        lines, W, H = detect_lines(jpg)
        s = PAGE_W / W
        page = doc.new_page(width=PAGE_W, height=H * s)
        page.insert_image(page.rect, filename=jpg)
        if not mlines:
            n_empty += 1
            continue
        if not lines:
            n_fallback += 1
            place_top(page, mlines, H, s)
            continue
        words = [sanitize(w) for line in mlines for w in line.split()]
        n = place_grouped(page, mlines, lines, s)
        n_done += 1
        print(f"  {stem}: {n}/{len(words)} ord -> {len(lines)} slots")
    doc.save(out, garbage=4, deflate=True)
    print(f"FÆRDIG: {out} ({os.path.getsize(out)/1e6:.1f} MB) "
          f"sider={len(doc)} linjefast={n_done} fallback={n_fallback} "
          f"tomme={n_empty}")


if __name__ == "__main__":
    main(sys.argv)

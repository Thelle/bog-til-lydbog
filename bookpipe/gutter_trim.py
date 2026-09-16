"""B2c: nabostrimler klippes ved PÅVIST strimlegrænse (aldrig blindt).
Fals: DocTR-ordbokse (db_resnet50, score >= 0.3) -> klynger -> smalle
(<12 % af bredden), frakoblede klynger (min. 2 bokse) fuldt inde i falsbåndet
(15 %) = nabostrimmel -> klip ved klyngens grænse + 15 px margin.
Krydsnings-garde: krydser én brødtekstboks snitlinjen, droppes fals-klippet.
Yderkant: mørk-pixel-projektion udefra (B3), klip max 8 %.
Antagelse: lige sidetal = venstresider (ScanTailor-opslagsrækkefølge).
Ret EVEN_LEFT = False hvis din bog starter med en højreside.
Brug: python -m bookpipe.gutter_trim <jpgmappe> <udmappe>
Kræver: doctr, torch (CPU ok), Pillow, numpy. Første kørsel henter modellen.
"""
import glob
import os
import sys

import numpy as np
from PIL import Image

from doctr.io import DocumentFile
from doctr.models import detection_predictor

EVEN_LEFT = True
SCORE_MIN = 0.3
BAND_OUTER = 0.12  # falsbånd (andel af bredde)
BAND_NARROW = 0.12  # strimmel maks-bredde (andel)
BAND_MARGIN = 15  # px luft ved strimlegrænse
BAND_CAP = 0.20  # sanity: klip aldrig over 20 % i falsen
PROJ_CAP = 0.08  # B3: klip max 8 % i yderkanten
GAP = 60  # klynge-tolerance px

_DET = None


def get_det():
    global _DET
    if _DET is None:
        print("Indlæser DocTR-detektor ...")
        _DET = detection_predictor("db_resnet50", pretrained=True)
    return _DET


def comps(boxes, gap=GAP):
    n = len(boxes)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i in range(n):
        for j in range(i + 1, n):
            a, b = boxes[i], boxes[j]
            dx = max(b[0] - a[2], a[0] - b[2])
            dy = max(b[1] - a[3], a[1] - b[3])
            if dx < gap and dy < gap:
                parent[find(i)] = find(j)
    out = {}
    for i in range(n):
        out.setdefault(find(i), []).append(i)
    return list(out.values())


def outer_proj_cut(im, left_side):
    """B3-projektion over mørke pixels. Returnerer behold-interval (a, b)."""
    g = np.array(im.convert("L"))
    W = im.size[0]
    dark = (g < 110).astype(float)
    prof = dark.mean(axis=0)
    k = np.ones(15) / 15
    sm = np.convolve(prof, k, mode="same")
    t = max(0.02, sm.max() * 0.15)
    cap = int(W * PROJ_CAP)
    if left_side:
        cut, run = 0, 0
        for x in range(W):
            run = run + 1 if sm[x] > t else 0
            if run >= 25:
                cut = max(0, x - 25 - 10)
                break
        return min(cut, cap), 0
    cut, run = W, 0
    for x in range(W - 1, -1, -1):
        run = run + 1 if sm[x] > t else 0
        if run >= 25:
            cut = min(W, x + 25 + 10)
            break
    return 0, max(cut, W - cap)


def detect_boxes(jpg):
    im = Image.open(jpg).convert("RGB")
    W, H = im.size
    res = get_det()(DocumentFile.from_images([jpg]))
    pg = res[0] if isinstance(res, list) else res.pages[0]
    arr = pg["words"] if isinstance(pg, dict) else []
    boxes = np.array([[x0 * W, y0 * H, x1 * W, y1 * H]
                      for x0, y0, x1, y1, s in arr if s >= SCORE_MIN])
    return im, boxes


def sliver_cut(boxes, W, left_page):
    """Returnerer (L, R, besked). Klipper kun ved påvist strimmelgrænse."""
    L, R = 0, W
    if len(boxes) < 3:
        return L, R, "for få bokse"
    cand = []
    for c in comps(boxes):
        if len(c) < 2:
            continue  # enkelt støjboks kan ikke udløse klip
        cb = boxes[c]
        cx0, cx1 = cb[:, 0].min(), cb[:, 2].max()
        if (cx1 - cx0) >= BAND_NARROW * W:
            continue
        if left_page and cx0 >= (1 - BAND_OUTER) * W - (BAND_OUTER - 0.12) * W:
            cand.append((cx0, cx1, c))
        elif not left_page and cx1 <= BAND_OUTER * W + (0.15 - BAND_OUTER) * W:
            cand.append((cx0, cx1, c))
    # Falsbånd: 15 % (venstre side: højre kant, højre side: venstre kant).
    cand = [(x0, x1, c) for x0, x1, c in cand
            if (left_page and x0 >= 0.85 * W) or
            (not left_page and x1 <= 0.15 * W)]
    if not cand:
        return L, R, "ingen"
    sliv_ids = set(c for _, _, c in cand for c in c)
    body = boxes[[i for i in range(len(boxes)) if i not in sliv_ids]]
    if left_page:
        rc = int(min(x0 for x0, _, _ in cand)) - BAND_MARGIN
        if len(body[(body[:, 0] < rc) & (body[:, 2] > rc)]):
            return L, R, f"ABORT: brødtekst krydser x={rc}"
        return L, max(rc, int(0.80 * W)), f"{len(cand)} strimmelklynge(r)"
    lc = int(max(x1 for _, x1, _ in cand)) + BAND_MARGIN
    if len(body[(body[:, 0] < lc) & (body[:, 2] > lc)]):
        return L, R, f"ABORT: brødtekst krydser x={lc}"
    return min(lc, int(0.20 * W)), R, f"{len(cand)} strimmelklynge(r)"


def trim_page(jpg, out):
    stem = os.path.splitext(os.path.basename(jpg))[0]
    left_page = (int(stem) % 2 == 0) == EVEN_LEFT
    im, boxes = detect_boxes(jpg)
    W, H = im.size
    L, R, gut = sliver_cut(boxes, W, left_page)
    mid = im.crop((L, 0, R, H))
    if left_page:
        oc, _ = outer_proj_cut(mid, True)
        L = L + oc
    else:
        _, oc = outer_proj_cut(mid, False)
        R = L + oc
    im.crop((int(L), 0, int(R), H)).save(out, quality=90)
    return f"{stem}: {len(boxes)} bokse, fals: {gut} -> x:[{int(L)},{int(R)}] af {W}"


def main(argv):
    indir, outdir = argv[1], argv[2]
    os.makedirs(outdir, exist_ok=True)
    jpgs = sorted(glob.glob(os.path.join(indir, "*.jpg")) +
                  glob.glob(os.path.join(indir, "*.JPG")))
    print(f"{len(jpgs)} sider -> {outdir}")
    for j in jpgs:
        out = os.path.join(outdir, os.path.splitext(os.path.basename(j))[0] + ".jpg")
        print(trim_page(j, out), flush=True)
    print("FAERDIG")


if __name__ == "__main__":
    main(sys.argv)

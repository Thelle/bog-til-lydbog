"""
PaddleOCR-baseret HQ-OCR — KØRER I ET SEPARAT PYTHON-VENV.

PaddleOCR løser læserækkefølge/scramble ved roden på krumme bogsider, gengiver
æøå korrekt og er verbatim (ingen hallucination). paddlepaddle har ingen wheels
til Python 3.14 (som resten af pipelinen kører på), så OCR-trinnet isoleres i et
separat venv og kaldes via subprocess.

Kør:  <venv-python> bookpipe/paddle_ocr.py <bog.toml> [sideantal]

Konfiguration via miljøvariabler (defaults = "Config A"):
  OCR_DEWARP=auto|off     ScanTailor-dewarp (off => lad Paddle udrette i stedet)
  OCR_UNWARP=0|1          PaddleOCR doc-unwarping
  OCR_MKLDNN=0|1          oneDNN-acceleration (kræver paddle-version uden PIR-bug, fx 3.2.2)
  OCR_LIMIT=960           text_det_limit_side_len (højere = mere opløsning)
  OCR_PAGES_SUBDIR=pages_hq   output-undermappe

"Config B" (komplet, anbefalet): OCR_DEWARP=off OCR_UNWARP=1 OCR_MKLDNN=1
  OCR_LIMIT=3000 OCR_PAGES_SUBDIR=pages_hq_B   (køres i paddle 3.2.2-venv)
"""
import os
import sys
import glob
import shutil
import subprocess
import time
import tomllib

OCR_DEWARP = os.environ.get("OCR_DEWARP", "auto")
OCR_UNWARP = os.environ.get("OCR_UNWARP", "0") == "1"
OCR_MKLDNN = os.environ.get("OCR_MKLDNN", "0") == "1"
OCR_LIMIT = int(os.environ.get("OCR_LIMIT", "960"))
OCR_PAGES_SUBDIR = os.environ.get("OCR_PAGES_SUBDIR", "pages_hq")

if not OCR_MKLDNN:
    os.environ.setdefault("FLAGS_use_mkldnn", "0")   # undgå paddle oneDNN PIR-bug
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

import numpy as np
from PIL import Image

SCANTAILOR = os.environ.get("SCANTAILOR_CLI", r"C:\Program Files\Scan Tailor\scantailor-cli.exe")
WHITE_PT = int(os.environ.get("OCR_WHITE_POINT", "165"))


def _workdir(output_dir):
    suffix = "" if OCR_DEWARP != "off" else "_nodewarp"
    return os.path.join(os.environ.get("TEMP", "."), "st_" + os.path.basename(output_dir) + suffix)


def scantailor_tifs(cfg):
    """Genbrug ScanTailor-TIFF'er hvis de findes i workdir; ellers kør ScanTailor."""
    wd = _workdir(cfg["output_dir"])
    st_in, st_out = os.path.join(wd, "in"), os.path.join(wd, "out")
    tifs = sorted(glob.glob(os.path.join(st_out, "*.tif")))
    if tifs:
        print(f"  genbruger {len(tifs)} cachede ScanTailor-TIFF'er (dewarp={OCR_DEWARP})")
        return tifs
    for d in (st_in, st_out):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)
    photos = sorted(glob.glob(os.path.join(cfg["source_photos"], cfg.get("source_glob", "*.JPG"))))
    for i, p in enumerate(photos):
        shutil.copy(p, os.path.join(st_in, f"{i:03d}.jpg"))
    imgs = sorted(glob.glob(os.path.join(st_in, "*.jpg")))
    layout = "2" if cfg.get("split_spreads", True) else "1"
    cmd = [SCANTAILOR, f"--layout={layout}", "--deskew=auto", f"--dewarping={OCR_DEWARP}",
           "--content-detection=normal", "--color-mode=color_grayscale",
           "--despeckle=normal", "--start-filter=1", "--end-filter=6"] + imgs + [st_out]
    print(f"  ScanTailor: {len(imgs)} fotos -> split+deskew (dewarp={OCR_DEWARP}, grayscale)...")
    subprocess.run(cmd, capture_output=True, text=True)
    return sorted(glob.glob(os.path.join(st_out, "*.tif")))


def whitepoint(im, wp=WHITE_PT):
    lut = [min(255, int(i * 255 / wp)) if i < wp else 255 for i in range(256)]
    return im.convert("L").point(lut)


def _boxes_xyxy(res):
    b = res.get("rec_boxes")
    if b is not None and len(b) > 0:
        return [[float(v) for v in box[:4]] for box in b]
    polys = res.get("rec_polys") or res.get("dt_polys") or []
    out = []
    for p in polys:
        xs = [pt[0] for pt in p]; ys = [pt[1] for pt in p]
        out.append([min(xs), min(ys), max(xs), max(ys)])
    return out


def strip_filter(items, W):
    """Fjern nabosidens kant-strimmel via brødtekstsøjlens grænser."""
    wide = [b for _t, b in items if (b[2] - b[0]) > 0.40 * W]
    if len(wide) < 3:
        return items
    main_l = min(b[0] for b in wide)
    main_r = max(b[2] for b in wide)
    gap = 0.03 * W
    return [(t, b) for t, b in items
            if not (b[0] > main_r + gap or b[2] < main_l - gap)]


def run(cfg_path, limit=None):
    with open(cfg_path, "rb") as f:
        cfg = tomllib.load(f)
    name = cfg.get("name", os.path.basename(cfg_path))
    print(f"[{name}] PaddleOCR (dewarp={OCR_DEWARP} unwarp={OCR_UNWARP} "
          f"mkldnn={OCR_MKLDNN} limit={OCR_LIMIT} -> {OCR_PAGES_SUBDIR})")
    tifs = scantailor_tifs(cfg)
    if limit:
        tifs = tifs[:limit]
    from paddleocr import PaddleOCR
    ocr = PaddleOCR(lang="da", use_doc_orientation_classify=False,
                    use_doc_unwarping=OCR_UNWARP, use_textline_orientation=False,
                    enable_mkldnn=OCR_MKLDNN, text_det_limit_side_len=OCR_LIMIT,
                    text_det_limit_type="max")
    pages_dir = os.path.join(cfg["output_dir"], OCR_PAGES_SUBDIR)
    os.makedirs(pages_dir, exist_ok=True)
    print(f"[{name}] OCR af {len(tifs)} sider...")
    t0 = time.time()
    for i, tif in enumerate(tifs):
        g = whitepoint(Image.open(tif))
        res = ocr.predict(input=np.array(g.convert("RGB")))[0]
        texts = res["rec_texts"]
        boxes = _boxes_xyxy(res)
        items = list(zip(texts, boxes)) if len(boxes) == len(texts) else [(t, [0, 0, g.size[0], 0]) for t in texts]
        items = strip_filter(items, g.size[0])
        page = "\n".join(t for t, _b in items)
        with open(os.path.join(pages_dir, f"{i:03d}.txt"), "w", encoding="utf-8") as fh:
            fh.write(page)
        if (i + 1) % 20 == 0 or i + 1 == len(tifs):
            el = time.time() - t0
            print(f"  {i+1}/{len(tifs)} ({el:.0f}s, {el/(i+1):.1f}s/side)")
    print(f"[{name}] Færdig: {len(tifs)} sider -> {pages_dir}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("brug: paddle_ocr.py <bog.toml> [sideantal]")
    run(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else None)

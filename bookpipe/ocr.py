"""
Høj-kvalitets tekst-OCR fra bogfotos.

Trin pr. dobbeltopslag-foto:
  1. Split i venstre/højre enkelt-side (ved midtpunkt).
Trin pr. enkelt-side:
  2. Hvid padding (så kant-tekst ikke tabes ved dewarp-remap).
  3. page-dewarp (-x 0) retter bogryggens krumning — den egentlige rodårsag
     til volapyk, ikke billedkvaliteten. -x 0 undgår venstrekant-beskæring.
  4. Tesseract --psm 3, dan+eng.
Sider hvor dewarp ikke kan fitte tekstlinjer (figurer/kort/titelsider) falder
tilbage til bilateral filter + adaptiv threshold. Output: pages_hq/NNN.txt.

Rører IKKE nogen søgbar PDF — dette er en separat, langsommere tekst-OCR til TTS.
"""
import os
import sys
import glob
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor

from PIL import Image, ImageOps
import cv2
import numpy as np

TESS = os.environ.get("TESSERACT_EXE", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
TESSDATA = os.environ.get("TESSDATA_PREFIX", r"C:\Program Files\Tesseract-OCR\tessdata")
PAD = 120


def split_spreads(cfg):
    """Split dobbeltopslag-fotos til enkelt-sider (venstre + højre halvdel)."""
    os.makedirs(cfg.tmp_dir, exist_ok=True)
    files = sorted(glob.glob(os.path.join(cfg.source_photos, cfg.source_glob)))
    print(f"Splitter {len(files)} dobbeltopslag...")
    page = 0
    for f in files:
        img = Image.open(f)
        w, h = img.size
        mid = w // 2
        img.crop((0, 0, mid, h)).save(os.path.join(cfg.tmp_dir, f"{page:03d}.jpg"), quality=95)
        page += 1
        img.crop((mid, 0, w, h)).save(os.path.join(cfg.tmp_dir, f"{page:03d}.jpg"), quality=95)
        page += 1
    print(f"  {page} enkelt-sider -> {cfg.tmp_dir}")
    return page


def _fallback_preprocess(img_path, out_png):
    """Dewarp fejlede: gråtone + bilateral filter + adaptiv threshold."""
    g = ImageOps.grayscale(Image.open(img_path))
    arr = np.array(g)
    arr = cv2.bilateralFilter(arr, 9, 75, 75)
    arr = cv2.adaptiveThreshold(arr, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY, 31, 15)
    Image.fromarray(arr).save(out_png)


def _process_page(args):
    pi, src_jpg, tmpp, pages_hq = args
    os.environ["TESSDATA_PREFIX"] = TESSDATA
    # 1. Hvid padding
    img = Image.open(src_jpg).convert("RGB")
    padded = ImageOps.expand(img, border=PAD, fill=(255, 255, 255))
    ascii_in = os.path.join(tmpp, f"p{pi:03d}.jpg")
    padded.save(ascii_in, quality=95)
    # 2. page-dewarp (-x 0)
    subprocess.run([sys.executable, "-m", "page_dewarp", "-x", "0", "-o", tmpp, ascii_in],
                   capture_output=True, text=True)
    thresh = os.path.join(tmpp, f"p{pi:03d}_thresh.png")
    if os.path.exists(thresh):
        status = "dewarp"
    else:
        thresh = os.path.join(tmpp, f"p{pi:03d}_fallback.png")
        _fallback_preprocess(ascii_in, thresh)
        status = "fallback"
    # 3. Tesseract
    base = os.path.join(tmpp, f"p{pi:03d}_ocr")
    subprocess.run([TESS, thresh, base, "-l", "dan+eng", "--psm", "3", "txt"],
                   capture_output=True)
    with open(base + ".txt", encoding="utf-8", errors="replace") as f:
        text = f.read()
    with open(os.path.join(pages_hq, f"{pi:03d}.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    return pi, status


def run_ocr(cfg, workers=4):
    """Kør HQ-OCR på alle splittede sider -> pages_hq/NNN.txt."""
    tmpp = os.path.join(os.environ.get("TEMP", "."), "hq_ocr_" + os.path.basename(cfg.output_dir))
    os.makedirs(cfg.pages_dir, exist_ok=True)
    os.makedirs(tmpp, exist_ok=True)
    files = sorted(glob.glob(os.path.join(cfg.tmp_dir, "*.jpg")))
    tasks = [(i, f, tmpp, cfg.pages_dir) for i, f in enumerate(files)]
    print(f"[{cfg.name}] HQ-OCR af {len(tasks)} sider med {workers} workers...")
    t0 = time.time()
    done = fb = 0
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for pi, status in ex.map(_process_page, tasks):
            done += 1
            fb += status == "fallback"
            if done % 20 == 0 or done == len(tasks):
                print(f"  {done}/{len(tasks)} sider ({time.time()-t0:.0f}s, {fb} fallback)")
    print(f"[{cfg.name}] Færdig: {done} sider, {fb} fallback, {time.time()-t0:.0f}s")

"""Mistral OCR pr. side (ScanTailor-billede -> .txt). Resume + parallel.
Brug: python -m bookpipe.mistral_ocr <billedmappe> <udmappe> [workers]
Miljø: MISTRAL_API_KEY i ~/ocr_project/.env (nøglen logges aldrig, kun længde).
  MISTRAL_MAX_SIDE (standard 2000): længste billedside før upload.
Koster API-kald pr. side; eksisterende .txt springes over (resume).
"""
import base64
import glob
import io
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path.home() / "ocr_project" / ".env")
API_KEY = os.getenv("MISTRAL_API_KEY", "")
if not API_KEY:
    sys.exit("FEJL: MISTRAL_API_KEY ikke fundet i ~/ocr_project/.env.")
print(f"Noegle indlaest (laengde {len(API_KEY)}), vaerdi vises aldrig.")

try:
    from mistralai.client.sdk import Mistral
except ImportError:
    try:
        from mistralai.client import Mistral
    except ImportError:
        from mistralai import Mistral
from PIL import Image

MAX_SIDE = int(os.getenv("MISTRAL_MAX_SIDE", "2000"))
CLIENT = Mistral(api_key=API_KEY)
T0 = time.time()


def one(args):
    tif, outdir = args
    out = os.path.join(outdir, Path(tif).stem + ".txt")
    if os.path.exists(out):
        return f"SKIP {Path(tif).name}"
    im = Image.open(tif).convert("RGB")
    if max(im.size) > MAX_SIDE:
        im.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    raw = buf.getvalue()
    try:
        res = CLIENT.ocr.process(
            model="mistral-ocr-latest",
            document={"type": "image_url",
                      "image_url": f"data:image/jpeg;base64,{base64.b64encode(raw).decode()}"},
        )
    except Exception as e:
        return f"FEJL {Path(tif).name}: {e}"
    md = "\n\n".join((p.markdown or "") for p in (res.pages or []))
    Path(out).write_text(md, encoding="utf-8")
    return f"OK {Path(tif).name}: {len(md)} tegn ({time.time()-T0:.0f}s)"


def main(argv):
    indir, outdir = argv[1], argv[2]
    workers = int(argv[3]) if len(argv) > 3 else 6
    os.makedirs(outdir, exist_ok=True)
    exts = ("*.tif", "*.tiff", "*.jpg", "*.JPG", "*.png")
    tifs = sorted(f for e in exts for f in glob.glob(os.path.join(indir, e)))
    print(f"{len(tifs)} sider, {workers} workers, maxside {MAX_SIDE} -> {outdir}")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for line in ex.map(one, [(t, outdir) for t in tifs]):
            print(line, flush=True)
    print("FAERDIG")


if __name__ == "__main__":
    main(sys.argv)

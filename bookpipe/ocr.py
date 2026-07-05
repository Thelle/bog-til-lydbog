"""
Høj-kvalitets tekst-OCR fra bogfotos — ScanTailor Advanced + EasyOCR.

Flow (tre trin, hver løser ét konkret problem vi har målt os frem til):

  1. scantailor-cli: originale opslag -> indholds-bevidst SIDEOPDELING (layout=2),
     DESKEW + DEWARP + despeckle. Udsender grå-skala side-TIFFs (color_grayscale),
     som bevarer diakritika (æøå) og § langt bedre end 1-bit black_and_white.

  2. HVIDPUNKT-KLIP: telefonfotos har ingen ren hvid baggrund — hele siden er
     ~200 grå, og den svage SPEJLVENDTE TEKST fra bagsiden (gennemslag) står
     tydeligt. Uden dette læser OCR gennemslaget som støj-tokens midt i linjerne
     ("NE", "A b", "SYES") = det der lignede scramble. Klip alt lysere end WHITE_PT
     til hvidt; den mørke rigtige tekst overlever.

  3. EasyOCR (paragraph): slår Tesseract på netop denne opgave. Tesseracts
     rækkebaserede layout-analyse scrambler når en linjes højre halvdel "drypper"
     nær bogryggen (fx "servitutforpligtet udfører" flækkes). EasyOCR detekterer
     tekst-regioner enkeltvis og læser dem i rigtig rækkefølge. Bonus: den holder
     de grå §-citatbokse som separate blokke der starter med "§ NN." — clean.py
     kan droppe dem rent. Pris: ~40 s/side (CPU) mod Tesseracts ~0,7 s.

Rører ingen søgbar PDF. ScanTailor skal være installeret (se README).
"""
import os
import sys
import glob
import shutil
import subprocess
import time

from PIL import Image

SCANTAILOR = os.environ.get("SCANTAILOR_CLI", r"C:\Program Files\Scan Tailor\scantailor-cli.exe")
WHITE_PT = int(os.environ.get("OCR_WHITE_POINT", "165"))   # hvidpunkt-klip (0-255)


def _workdir(cfg):
    return os.path.join(os.environ.get("TEMP", "."), "st_" + os.path.basename(cfg.output_dir))


def run_scantailor(cfg):
    """Kør scantailor-cli (split + deskew + dewarp) på alle originalfotos.
    Kopierer først til ASCII-navne (ScanTailor bryder sig ikke om æ/ø-stier) med
    nul-polstrede numre, så output-TIFFs sorterer i korrekt siderækkefølge.
    Returnerer listen af side-TIFFs i rækkefølge."""
    wd = _workdir(cfg)
    st_in, st_out = os.path.join(wd, "in"), os.path.join(wd, "out")
    for d in (st_in, st_out):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)

    photos = sorted(glob.glob(os.path.join(cfg.source_photos, cfg.source_glob)))
    for i, p in enumerate(photos):
        shutil.copy(p, os.path.join(st_in, f"{i:03d}.jpg"))
    imgs = sorted(glob.glob(os.path.join(st_in, "*.jpg")))

    layout = "2" if cfg.split_spreads else "1"
    cmd = [SCANTAILOR, f"--layout={layout}", "--deskew=auto", "--dewarping=auto",
           "--content-detection=normal", "--color-mode=color_grayscale",
           "--despeckle=normal", "--start-filter=1", "--end-filter=6"] + imgs + [st_out]
    print(f"[{cfg.name}] ScanTailor: {len(imgs)} fotos -> split+deskew+dewarp "
          f"(grayscale, kan tage nogle minutter)...")
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    tifs = sorted(glob.glob(os.path.join(st_out, "*.tif")))
    print(f"  {len(tifs)} sider produceret ({time.time()-t0:.0f}s)")
    if not tifs:
        print("  STDERR:", (proc.stderr or "")[-800:])
    return tifs


def _whitepoint(im, wp=WHITE_PT):
    """Klip baggrund/gennemslag: pixels lysere end wp -> hvid, resten strækkes."""
    lut = [min(255, int(i * 255 / wp)) if i < wp else 255 for i in range(256)]
    return im.convert("L").point(lut)


def _page_text(reader, tif):
    """OCR én side: whitepoint-klip -> EasyOCR paragraph -> afsnit sorteret
    top->bund, ét afsnit pr. linje (bevarer §-bokse som droppbare blokke)."""
    import numpy as np
    img = np.array(_whitepoint(Image.open(tif)).convert("RGB"))
    res = reader.readtext(img, detail=1, paragraph=True)
    paras = sorted(res, key=lambda z: min(p[1] for p in z[0]))
    return "\n".join(txt for _box, txt in paras)


def run_ocr(cfg, workers=None):
    """ScanTailor -> whitepoint -> EasyOCR -> pages_hq/NNN.txt for hele bogen."""
    tifs = run_scantailor(cfg)
    if not tifs:
        print("Ingen sider fra ScanTailor — afbryder.")
        return
    os.makedirs(cfg.pages_dir, exist_ok=True)

    import easyocr
    print(f"[{cfg.name}] Indlæser EasyOCR (da+en, CPU)...")
    reader = easyocr.Reader(["da", "en"], gpu=False, verbose=False)
    print(f"[{cfg.name}] EasyOCR af {len(tifs)} sider (~40 s/side)...")
    t0 = time.time()
    for i, tif in enumerate(tifs):
        text = _page_text(reader, tif)
        with open(os.path.join(cfg.pages_dir, f"{i:03d}.txt"), "w", encoding="utf-8") as f:
            f.write(text)
        if (i + 1) % 10 == 0 or i + 1 == len(tifs):
            el = time.time() - t0
            eta = el / (i + 1) * (len(tifs) - i - 1)
            print(f"  {i+1}/{len(tifs)} sider ({el:.0f}s, ETA {eta:.0f}s)")
    print(f"[{cfg.name}] Færdig: {len(tifs)} sider -> {cfg.pages_dir}")

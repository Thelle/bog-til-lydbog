"""Uafhængig verificering af søgbar PDF (hører til searchable_pdf).

Vogter tre defekter:
1. TABT TEKST: hver ikke-tomme kilde-txt skal give et ikke-tomt lag; hvert
   ord (efter SAMME sanitize som searchable_pdf — laget kan kun holde
   latin-1) skal have >=1 søgetræf.
2. POSITIONER: probe-ord skal ramme inden for det vertikale bånd hvor ordet
   faktisk står (linjeforankret lag, ikke én flowed blok fra toppen).
3. TOM KILDE: tom txt + lag med tekst = fejl (falsk søgbarhed).

Brug (fra repo-roden):
  python -m bookpipe.verify_pdf <pdf> <txtmappe> [--sample N]
Exit 0 = grøn, 1 = rød (printer alle overtrædelser). --sample N tjekker
alle lags hurtige egenskaber + fuld ordsøgning på N seedede sider.
Kør altid fra en /tmp-kopi af PDF'en (Windows-mount er ~100x langsommere)
og søg kun unikke ord (se tillægget i README).

PROBER kalibreres pr. bog/tekstversion (se README trin 6): vælg 5 særprægede
ord, mål deres y (andel af sidehøjden) og saet bånd med margin. Et for rule,
der fejler, betyder enten forkert placering ELLER foreldet probe — afgør med
renderet kontrolbillede (se README) før du retter PDF'en.
"""
import glob
import os
import random
import sys

BASE = os.path.dirname(os.path.abspath(__file__))

# (sideindeks, ord, (min_y, maks_y) som andel af sidehøjden).
# Eksempel (Vejjura-bogen, B2c-tekster) — erstattes pr. bog:
#   (123, "Vejdirektoratet", (0.45, 0.65)),
PROBES = []


def main(argv):
    rest = list(argv[1:])
    pdf, txtdir, sample = None, None, None
    while rest:
        a = rest.pop(0)
        if a == "--sample":
            sample = int(rest.pop(0))
        elif pdf is None:
            pdf = a
        else:
            txtdir = a
    if pdf is None or txtdir is None:
        sys.exit("Brug: python -m bookpipe.verify_pdf <pdf> <txtmappe> "
                 "[--sample N]")

    import pymupdf
    from bookpipe.searchable_pdf import SANITIZE

    def latin1(word):
        try:
            word.encode("latin-1")
            return word
        except UnicodeEncodeError:
            return word.encode("latin-1", "replace").decode("latin-1")

    def toks(text):
        out = []
        for w in text.split():
            w = latin1(w.translate(SANITIZE))
            out.extend(s for s in w.split() if s)
        return out

    fails = []
    doc = pymupdf.open(pdf)
    txts = sorted(glob.glob(os.path.join(txtdir, "*.txt")))
    assert len(txts) == len(doc), \
        f"antal mismatch: {len(txts)} txt vs {len(doc)} sider"

    idx = [int(os.path.splitext(os.path.basename(t))[0]) for t in txts]
    full = idx if sample is None else sorted(random.Random(7).sample(idx,
                                                                     sample))
    for t in txts:
        i = int(os.path.splitext(os.path.basename(t))[0])
        src = open(t, encoding="utf-8").read()
        pg = doc[i]
        if not toks(src):
            if pg.get_text().strip():
                fails.append(f"{i:03d}: tom kilde men lag med tekst")
            continue
        if not pg.get_text().strip():
            fails.append(f"{i:03d}: TOMT lag for {len(src)} tegn kilde "
                         "(overflow-tab!)")
            continue
        if i not in full:
            continue
        sw = toks(src)
        # Unikke ord: samme søgning gentaget for hver forekomst er spild.
        miss = [w for w in set(sw) if not pg.search_for(w)]
        if miss:
            fails.append(f"{i:03d}: {len(miss)}/{len(sw)} ord usøgbare "
                         f"(fx {miss[:4]})")

    for i, word, (lo, hi) in PROBES:
        pg = doc[i]
        hits = pg.search_for(word)
        if not hits:
            fails.append(f"{i:03d}: {word!r} slet ikke fundet")
            continue
        ys = [h.y0 / pg.rect.height for h in hits]
        if not any(lo < y < hi for y in ys):
            fails.append(f"{i:03d}: {word!r} ramt ved "
                         f"y={[round(y, 2) for y in ys][:3]} "
                         f"(krav {lo}-{hi})")

    if fails:
        print("ROED:")
        print("\n".join(f"  {f}" for f in fails))
        sys.exit(1)
    mode = f"stikprøve {sample} sider" if sample else \
        f"alle {len(doc)} sider"
    print(f"GROEN: {mode}, ingen tomme lag, alle ord søgbare, "
          f"{len(PROBES)} positionsprober ok")


if __name__ == "__main__":
    main(sys.argv)

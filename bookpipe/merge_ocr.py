"""
Kombinér Config A (pages_hq, dewarp+no-unwarp) og Config B (pages_hq_B,
no-dewarp+unwarp) på SIDE-NIVEAU.

B er primær (komplet krop på de fleste sider, rigtig rækkefølge, fodnoter
naturligt væk). MEN på nogle sider fejler B katastrofalt (dropper det meste).
Linje-for-linje-fletning blev droppet: A og B er uenige om for mange linjer
(forskellig linjeopdeling + små OCR-forskelle), så fletning blandede garblede
dubletter ind. I stedet vælges pr. side: brug B, medmindre B er markant kortere
end A (=> B fejlede) => brug A. Hver side stammer fra ÉN config => internt
konsistent, ingen garblede dubletter. Fodnoter fjernes senere i clean.py.

A-filer hedder fysisk sidetal (fx 004.txt), B-filer 0-baseret indeks (000.txt);
offset (default 4) mapper B-indeks i -> A-fil (i+offset).

Kør (Python 3.14, ingen paddle):  python bookpipe/merge_ocr.py <bog.toml> [offset]
"""
import os
import re
import sys
import glob
import shutil
import difflib
import tomllib

B_FAIL_RATIO = float(os.environ.get("MERGE_B_FAIL_RATIO", "0.75"))  # B < ratio*A => brug A


def _dedup(lines):
    """Fjern lange (>15 tegn) linjer der er ~identiske (>0.92) med en tidligere
    linje på siden — rydder OCR-doblede linjer. Prosa gentager ikke lange linjer."""
    def norm(s):
        return re.sub(r"\s+", "", s.lower())
    out, onorm = [], []
    for l in lines:
        n = norm(l)
        if len(l) > 15 and any(difflib.SequenceMatcher(None, n, o).ratio() > 0.92 for o in onorm):
            continue
        out.append(l)
        onorm.append(n)
    return out


def run(cfg_path, offset=4):
    with open(cfg_path, "rb") as f:
        cfg = tomllib.load(f)
    out = cfg["output_dir"]
    dirA = os.path.join(out, "pages_hq")
    dirB = os.path.join(out, "pages_hq_B")
    bak = os.path.join(out, "pages_hq_A_backup")
    bfiles = sorted(glob.glob(os.path.join(dirB, "*.txt")))
    if not bfiles:
        sys.exit(f"ingen Config B-sider i {dirB}")
    if not os.path.isdir(bak):
        shutil.copytree(dirA, bak)
        print(f"  A sikret i {bak}")
    used_A = []
    for i, bf in enumerate(bfiles):
        B = [l for l in open(bf, encoding="utf-8").read().splitlines()]
        af = os.path.join(bak, f"{i + offset:03d}.txt")
        A = [l for l in open(af, encoding="utf-8").read().splitlines()] if os.path.exists(af) else []
        nA = len([l for l in A if l.strip()])
        nB = len([l for l in B if l.strip()])
        if nA > 0 and nB < B_FAIL_RATIO * nA:      # B fejlede på siden -> brug A
            chosen = A
            used_A.append(i + offset)
        else:
            chosen = B
        chosen = _dedup([l for l in chosen if l.strip()])
        with open(os.path.join(dirA, f"{i + offset:03d}.txt"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(chosen))
    print(f"[{cfg.get('name', cfg_path)}] {len(bfiles)} sider: "
          f"{len(bfiles) - len(used_A)} fra B, {len(used_A)} fra A (B fejlede). "
          f"A-sider: {used_A}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("brug: merge_ocr.py <bog.toml> [offset]")
    run(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 4)

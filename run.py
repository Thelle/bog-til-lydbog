"""
CLI til bog-til-lydbog pipelinen.

  python run.py ocr    <bog>          # split dobbeltopslag + HQ-OCR -> pages_hq/
  python run.py detect <bog>          # vis kapitel-opdeling (kontrollér grænser)
  python run.py txt    <bog> [nr]     # skriv renset tekst (alle kapitler, eller ét)
  python run.py sample <bog> <nr>     # tekst + MP3 for ét kapitel
  python run.py all    <bog>          # tekst + MP3 for alle kapitler

<bog> = navnet på en config i books/ (uden .toml), fx 'servitutretten_evald',
eller en sti til en .toml-fil.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")  # undgå cp1252-fejl på Windows-konsol

from bookpipe import config, ocr, chapters

BOOKS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "books")


def load_book(name):
    path = name if name.endswith(".toml") else os.path.join(BOOKS_DIR, name + ".toml")
    if not os.path.exists(path):
        sys.exit(f"Config ikke fundet: {path}\nTilgængelige: "
                 + ", ".join(sorted(f[:-5] for f in os.listdir(BOOKS_DIR) if f.endswith(".toml"))))
    return config.load(path)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, book = sys.argv[1], sys.argv[2]
    cfg = load_book(book)

    if cmd == "ocr":
        if cfg.split_spreads:
            existing = os.path.join(cfg.tmp_dir)
            import glob
            if not glob.glob(os.path.join(existing, "*.jpg")):
                ocr.split_spreads(cfg)
        ocr.run_ocr(cfg)
        return

    pages, known, chs = chapters.prepare(cfg)

    if cmd == "detect":
        print(f"[{cfg.name}] fundet {len(chs)} kapitler (body_end={cfg.body_end}):\n")
        for num, title, sp, ep, body in chs:
            print(f"  Kap {num:2d}  sider {sp:3d}-{ep-1:3d}  "
                  f"({ep-sp:2d} sider, {len(body):6d} tegn)  {title}")

    elif cmd == "txt":
        want = int(sys.argv[3]) if len(sys.argv) > 3 else None
        for num, title, sp, ep, body in chs:
            if want is not None and num != want:
                continue
            path, n = chapters.write_text(cfg, num, title, body, known)
            print(f"  Kap {num:2d}: {n:,} tegn -> {path}")

    elif cmd == "sample":
        want = int(sys.argv[3])
        for num, title, sp, ep, body in chs:
            if num == want:
                print(f"Genererer prøve: Kapitel {num} — {title}")
                t, m, n = chapters.write_chapter(cfg, num, title, body, known)
                print(f"  TXT: {t}\n  MP3: {m}\n  Renset tekst: {n:,} tegn")
                break

    elif cmd == "all":
        for num, title, sp, ep, body in chs:
            print(f"Kap {num:2d}: {title} ...")
            chapters.write_chapter(cfg, num, title, body, known)
        print("Færdig — alle kapitler skrevet.")

    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()

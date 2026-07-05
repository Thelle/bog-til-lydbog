"""
Opdel OCR'ede sider i kapitler, rens og skriv tekst (+ evt. MP3).

To detektionsmåder (sat i bogens config):
  detect = "manual"  -> hardcodede kapitelgrænser i config (robust når OCR-støj
                        gør automatisk detektion upålidelig).
  detect = "kapitel" -> find VERSAL "KAPITEL N" i sideteksten; titler fra config.

`body_end` klipper det sidste kapitel ved brødtekstens slutning, så
register/litteratur/stikord bagerst i bogen ikke læses op.
"""
import os
import re
import glob

from .clean import clean_for_tts
from .dictionary import build_known
from .tts import synth


def _apply_pronounce(text, rules):
    """Regex-substitutioner der KUN bruges til oplæsning (fx udtale-hints), så
    den gemte tekstfil forbliver korrekt. Fx 'vejret' -> 'vej-ret' så TTS siger
    en ret til en vej og ikke vejr-fænomenet."""
    for r in rules:
        text = re.sub(r["pattern"], r["repl"], text)
    return text


def load_pages(cfg):
    pages = []
    for f in sorted(glob.glob(os.path.join(cfg.pages_dir, "*.txt"))):
        with open(f, encoding="utf-8", errors="replace") as fh:
            pages.append(fh.read())
    return pages


def _starts_manual(cfg, pages):
    starts = [(c["num"], c["page"]) for c in cfg.chapters if c["page"] < len(pages)]
    titles = {c["num"]: c["title"] for c in cfg.chapters}
    return starts, titles


def _starts_kapitel(cfg, pages):
    """Find kapitelstarter via case-sensitiv 'KAPITEL N' i sideteksten."""
    starts, seen = [], set()
    for pi, t in enumerate(pages):
        if "KAPITEL" not in t:
            continue
        m = re.search(r"KAPITEL\s*(\d+)", t) or re.search(r"KAPITEL\s*\n\s*(\d+)", t)
        num = int(m.group(1)) if m else None
        if num and num not in seen:
            seen.add(num)
            starts.append((num, pi))
    return starts, dict(cfg.titles)


def find_chapter_starts(cfg, pages):
    if cfg.detect == "kapitel":
        return _starts_kapitel(cfg, pages)
    return _starts_manual(cfg, pages)


def build_chapters(cfg, pages, starts, titles):
    end = cfg.body_end if cfg.body_end is not None else len(pages)
    chapters = []
    for i, (num, sp) in enumerate(starts):
        ep = starts[i + 1][1] if i + 1 < len(starts) else end
        body = "\n".join(pages[sp:ep])
        chapters.append((num, titles.get(num, f"Kapitel {num}"), sp, ep, body))
    return chapters


def safe_name(s):
    s = re.sub(r'[\\/:*?"<>|]', "", s)
    return re.sub(r"\s+", "_", s.strip())[:90]


def write_text(cfg, num, title, body, known):
    """Skriv kun renset tekst (ingen MP3). Returnér (sti, tegn)."""
    os.makedirs(cfg.txt_dir, exist_ok=True)
    cleaned = clean_for_tts(body, known)
    path = os.path.join(cfg.txt_dir, f"Kapitel_{num:02d}_{safe_name(title)}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(cleaned)
    return path, len(cleaned)


def write_chapter(cfg, num, title, body, known):
    """Skriv renset tekst + generér MP3."""
    os.makedirs(cfg.mp3_dir, exist_ok=True)
    txt_path, n = write_text(cfg, num, title, body, known)
    mp3_path = os.path.join(cfg.mp3_dir, f"Kapitel_{num:02d}_{safe_name(title)}.mp3")
    spoken = _apply_pronounce(open(txt_path, encoding="utf-8").read(), cfg.tts_pronounce)
    synth(spoken, mp3_path, cfg.voice)
    return txt_path, mp3_path, n


def prepare(cfg):
    """Indlæs sider, byg ordbog + kapitler. Returnér (pages, known, chapters)."""
    pages = load_pages(cfg)
    known = build_known(pages)
    starts, titles = find_chapter_starts(cfg, pages)
    chapters = build_chapters(cfg, pages, starts, titles)
    return pages, known, chapters

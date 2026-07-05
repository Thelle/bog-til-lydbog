"""
Kvalitetstjek — flag de sider der mest sandsynligt har OCR-problemer, så en
menneske- eller LLM-gennemgang kan fokusere dér i stedet for at læse alt.

Heuristikken kan ikke selv forstå tekst, men den kan pege på de mistænkelige
sider ud fra billige signaler. Meningen er feedback-loopet:

    ocr -> qc (ranger mistænkelige sider) -> læs/ret de værste -> gentag

Score pr. side (0 = ren, 1 = slem) vægter fire signaler der hver især fanger en
type fejl vi har set:
  - junk:  andel lange ord der ikke er rigtige ord (tegn-volapyk, afkortede ord)
  - wq:    lav gennemsnitlig ordkvalitet (spredt OCR-støj)
  - frag:  andel linjer der ligner strimmel-/scramble-fragmenter
  - split: tæthed af ' - ' midt i linjer (dryppende linjer / orddeling)
Ingen af dem fanger 'scramblet-men-ægte' rækkefølge alene — derfor er sidste led
en menneske/LLM-læsning af de top-flagede sider.
"""
import re
from .clean import (_word_quality, _is_strip_fragment, is_garbage,
                    _clean_line, _strip_trailing_garbage_words)
from .dictionary import is_real_word, has_dictionary


def score_page(text, known):
    """Returnér (score 0-1, dict med delsignaler) for én sides tekst."""
    lines = [l for l in text.split("\n") if l.strip()]
    if not lines:
        return 0.0, {}
    toks = text.split()
    longw = [w for w in (re.sub(r"[^a-zA-ZæøåÆØÅ]", "", t).lower() for t in toks)
             if len(w) >= 4]
    junk = (sum(1 for w in longw if not is_real_word(w, known)) / len(longw)
            if longw and has_dictionary(known) else 0.0)
    wq = sum(_word_quality(t) for t in toks) / len(toks) if toks else 1.0
    frag = sum(1 for l in lines
               if _is_strip_fragment(l, known) or is_garbage(l)) / len(lines)
    splits = len(re.findall(r"\S+ - \S+|\S+- ", text))
    split = min(splits / max(len(text) / 1000, 1) / 6, 1.0)   # normaliseret 0-1
    score = 0.40 * junk + 0.30 * (1 - wq) + 0.20 * frag + 0.10 * split
    return score, {"junk": junk, "wq": wq, "frag": frag, "split": split}


def rank_pages(pages, known, top=20, include=None):
    """Ranger sider efter mistænkeligheds-score, værst først. `include` = sæt af
    sideindekser der skal vurderes (typisk kun sider der faktisk er i lyden —
    register/indholdsfortegnelse uden for body_end er irrelevante)."""
    scored = []
    for i, p in enumerate(pages):
        if include is not None and i not in include:
            continue
        s, parts = score_page(p, known)
        scored.append((s, i, parts, p))
    scored.sort(key=lambda z: -z[0])
    return scored[:top]


def snippet(text, n=140):
    """Kort, komprimeret uddrag til rapporten."""
    return re.sub(r"\s+", " ", text).strip()[:n]

"""
Rens rå OCR-tekst til oplæsning (TTS).

Fjerner: indbindings-pipes, scanningskant-artefakter, sidehoveder, sidetal,
fodnoter, indholdsfortegnelse-punktledere, dom-/lovregisterlinjer, VERSAL-
støjfragmenter og selvstændige volapyk-linjer (via ordbog). Samler til sidst
brudte linjer til flydende afsnit (reflow).

Alle funktioner er porteret 1:1 fra de oprindelige per-bog-scripts, så output
er identisk. Ordbogen (`known`) sendes ind udefra.
"""
import re
from .dictionary import is_real_word, has_dictionary


def _word_quality(w):
    """Score 0.0-1.0: hvor sandsynligt er dette et rigtigt dansk ord?"""
    clean = re.sub(r"[^a-zA-ZæøåÆØÅ]", "", w)
    if not clean:
        return 0.1
    if len(clean) <= 1:
        return 0.2
    has_vowel = any(c.lower() in "aeiouyæøå" for c in clean)
    if not has_vowel:
        return 0.15
    all_upper = all(c.isupper() for c in clean)
    if all_upper and len(clean) >= 2:
        return 0.25
    mixed_weird = (clean[0].isupper() and len(clean) <= 3
                   and any(c.isupper() for c in clean[1:]))
    if mixed_weird:
        return 0.3
    if len(clean) <= 3 and not has_vowel:
        return 0.2
    return 1.0


def _clean_line(s):
    """Rens én linje: fjern leading/trailing OCR-artefakter."""
    # Leading pipes fra indbinding — strip alt op til sidste | i de første 12 tegn
    if "|" in s[:12]:
        pipe_pos = s[:12].rfind("|")
        s = s[pipe_pos + 1:].strip()
    s = re.sub(r"^[\!\[\]\{\}'\"]+\s*", "", s)
    s = re.sub(r"^[>~=]\s+", "", s)
    # Leading enkelt-tegns margin-maerker fra dewarp-kant (. * : _ ” osv.)
    s = re.sub(r"^[.\*:;_”“’‘·•]{1,2}\s+", "", s)
    # Leading: korte garbage-tokens (1-3 tegn) fra modsatte sides gennemskin
    m = re.match(r"^(\S{1,3})\s+(.{10,})$", s.strip())
    if m:
        prefix = m.group(1)
        rest = m.group(2)
        if prefix not in ("§", "jf.", "nr.", "ca.", "DL", "fx.", "og", "at", "af",
                          "en", "et", "de", "er", "i", "om", "se", "så", "to"):
            if not re.match(r"^\d+\.", prefix):
                if _word_quality(prefix) < 0.5:
                    s = rest
    # Trailing: scanningskant
    s = re.sub(r"\s+[=\-;:|~!]+\s*$", "", s)
    s = re.sub(r"\s+[S=\-]{3,}[\sS=\-]*$", "", s)
    s = re.sub(r"\s+[a-zA-ZÆØÅ]\s*$", "", s)
    s = re.sub(r"\s+\d\s*$", "", s)
    s = re.sub(r"\s+[A-ZÆØÅ]{2,5}\s*$", "", s)
    s = re.sub(r"\s+(?:[A-ZÆØÅ]{2,}\s*)+$", "", s)
    return s.strip()


def _strip_trailing_garbage_words(s):
    """Strip trailing ord der scorer lavt (OCR-artefakter i højre margin)."""
    words = s.split()
    while len(words) > 2:
        if _word_quality(words[-1]) < 0.5:
            words.pop()
        else:
            break
    return " ".join(words)


def is_garbage(line):
    """Detektér OCR-volapyk med ordkvalitets-scoring."""
    s = line.strip()
    if not s or len(s) < 3:
        return True
    toks = s.split()
    if not toks:
        return True
    if len(s) < 8 and len(toks) <= 2:
        if sum(1 for c in s if c.isalpha()) < 4:
            return True
    if len(toks) >= 3:
        if sum(1 for t in toks if len(t) == 1) / len(toks) > 0.30:
            return True
    if len(toks) >= 3:
        if sum(1 for t in toks if len(t) <= 2) / len(toks) > 0.45:
            return True
    if len(toks) >= 3:
        avg = sum(_word_quality(t) for t in toks) / len(toks)
        if avg < 0.6:
            return True
    if len(s) < 20:
        alpha = [c for c in s if c.isalpha()]
        vowels = sum(1 for c in s.lower() if c in "aeiouyæøå")
        if len(alpha) >= 3 and vowels / max(len(alpha), 1) < 0.15:
            return True
    alpha_count = sum(1 for c in s if c.isalpha())
    if len(s) >= 5 and alpha_count / len(s) < 0.35:
        return True
    return False


def _is_running_header(line, seen_headers):
    """Gentagne sidehoveder. Nøgle = sektionsnummer (undgår OCR-variation i titel)."""
    m = re.match(r"^(\d+\.\d+(?:\.\d+)*)\s+[A-ZÆØÅ]", line)
    if m:
        key = m.group(1)
        if key in seen_headers:
            return True
        seen_headers.add(key)
    return False


def _is_footnote(line):
    """Fodnoter: '1. Forordning om...', '6. Gadejorden rummede...'"""
    return bool(re.match(r"^\d{1,2}\.\s+[A-ZÆØÅ]", line) and len(line) < 200)


def _has_heavy_corruption(line):
    """Linjer med tung OCR-korruption: mange garbage-fragmenter i ellers reel tekst."""
    toks = line.split()
    if len(toks) < 5:
        return False
    bad = sum(1 for t in toks if _word_quality(t) < 0.5)
    return bad / len(toks) > 0.3


def _is_register_line(s):
    """Ren register-/domslinje: 'KFE 1975.147 50,65', 'U 1960.220 VLD 228'.
    Kun korte, talstunge linjer med citations-kode + årstal — inline body-
    citationer ('jf. U 2003.2078 HD vedr. ...') er lange og rammes ikke."""
    if len(s) > 45:
        return False
    if not re.match(r"^[A-ZÆØÅ]{1,5}\.?\s+\d{4}[.,]\d", s):
        return False
    digits = sum(c.isdigit() for c in s)
    return digits / max(len(s), 1) > 0.20


def _is_caps_fragment(s):
    """Kort linje der kun er 1-3 rene VERSAL-fragmenter uden tal ('PEDE',
    'TEEN ESTHER,'). Rigtige overskrifter er title case."""
    toks = s.split()
    if not (1 <= len(toks) <= 3) or len(s) > 25:
        return False
    if any(c.isdigit() for c in s):
        return False
    if len(re.sub(r"[^A-Za-zÆØÅæøå]", "", s)) < 3:
        return False
    for t in toks:
        letters = re.sub(r"[^A-Za-zÆØÅæøå]", "", t)
        if not letters or not letters.isupper():
            return False
    return True


def _is_repeated_token(s):
    """Linje der kun er samme korte token gentaget ('dei dei')."""
    core = [re.sub(r"[^a-zA-ZæøåÆØÅ]", "", t).lower() for t in s.split()]
    core = [c for c in core if c]
    return len(core) >= 2 and len(set(core)) == 1 and len(core[0]) <= 4


def _is_nonword_line(s, known):
    """Kort linje uden ét eneste solidt rigtigt ord = OCR-volapyk
    ('tdi eta lla eh', 'Sea Calli wearer cia da', 'Blithe', 'ahaaith tended')."""
    if len(s) > 50:
        return False
    if not has_dictionary(known):        # ingen ordbog -> spring over (fjern ikke alt)
        return False
    toks = [re.sub(r"[^a-zA-ZæøåÆØÅ]", "", t).lower() for t in s.split()]
    toks = [t for t in toks if t]
    if not toks:
        return False
    return not any(is_real_word(t, known) for t in toks)


def clean_for_tts(text, known=frozenset()):
    """Orkestrér al rensning + reflow. `known` er korpus-ordbogen (build_known)."""
    seen_headers = set()
    out = []
    for ln in text.split("\n"):
        s = _clean_line(ln)
        s = _strip_trailing_garbage_words(s)
        if not s:
            continue
        if re.fullmatch(r"\d{1,4}", s):
            continue
        if re.fullmatch(r"KAPITEL\s*\d*", s):          # versal kapitel-rest
            continue
        if s.lower() == "indholdsfortegnelse":
            continue
        if re.match(r"^\d{1,4}\s+Kapitel\s+\d+\.", s):  # løbende sidehoved "16 Kapitel 1. ..."
            continue
        if re.match(r"^Kapitel\s+\d+\.\s+\D.*$", s) and len(s) < 70:  # "Kapitel 1. Om ..."
            continue
        if _is_running_header(s, seen_headers):
            continue
        if re.search(r"\.{4,}", s):                   # indholdsfortegnelse punkt-ledere
            continue
        if _is_register_line(s):                       # dom-/lovregisterlinje
            continue
        if _is_caps_fragment(s):                       # VERSAL-støjfragment
            continue
        if _is_repeated_token(s):                      # 'dei dei'
            continue
        if _is_nonword_line(s, known):                 # 'tdi eta lla eh' (ordbog)
            continue
        if is_garbage(s):
            continue
        if _is_footnote(s):
            continue
        if _has_heavy_corruption(s):
            continue
        out.append(s)

    joined = "\n".join(out)
    joined = re.sub(r"(\w)-\n(\w)", r"\1\2", joined)   # saml orddeling ved linjeskift
    reflowed = []
    for ln in joined.split("\n"):
        if (reflowed and reflowed[-1]
                and not re.search(r"[.:!?»]$", reflowed[-1])
                and not re.match(r"^\d+(\.\d+)*\.?\s", ln)
                and ln[:1].islower()):
            reflowed[-1] += " " + ln
        else:
            reflowed.append(ln)
    return "\n".join(reflowed).strip()

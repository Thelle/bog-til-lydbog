"""
Ordbog til at skelne rigtige danske ord fra OCR-volapyk.

Hybrid: wordfreq (gængs dansk) + bogens eget korpus. Korpusset er nødvendigt
fordi domæneord som 'servitut' scorer 0.00 i wordfreq; wordfreq fanger til
gengæld engelsk enkelt-token-volapyk som 'blithe' der aldrig ses i bogen.
"""
import re
from collections import Counter

try:
    from wordfreq import zipf_frequency as _zipf_raw

    def zipf_da(w):
        return _zipf_raw(w, "da")
except Exception:  # wordfreq ikke installeret -> kun korpus bruges
    def zipf_da(w):
        return 0.0


def build_known(pages, min_count=3):
    """Ord der optræder >= min_count gange i hele bogen = 'rigtige' ord
    (domæneord, forfatternavne mm. der mangler i wordfreq)."""
    c = Counter()
    for p in pages:
        for tok in p.split():
            w = re.sub(r"[^a-zA-ZæøåÆØÅ]", "", tok).lower()
            if len(w) >= 2:
                c[w] += 1
    return {w for w, n in c.items() if n >= min_count}


def is_real_word(w, known):
    """Solidt rigtigt ord: mindst 4 bogstaver og enten hyppigt i bogen
    eller et gængs dansk ord (wordfreq zipf >= 2.5)."""
    if len(w) < 4:
        return False
    return w in known or zipf_da(w) >= 2.5


def has_dictionary(known):
    """Er der overhovedet en ordbog at arbejde med? (guard mod at fjerne alt)."""
    return bool(known) or zipf_da("kommune") >= 1

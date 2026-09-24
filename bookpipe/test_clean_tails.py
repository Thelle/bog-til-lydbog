"""Regressionstest: clean_for_tts klipper ikke ægte haler ("klippede haler").

Haleklipperen _strip_trailing_garbage_words er fjernet — B2c fjerner
modstående-side strimler ved kilden, så linjernes haler røres ikke.
_is_strip_fragment er bevidst bevaret til qc-rangering (frag-signalet).
Kør fra repo-roden: python bookpipe/test_clean_tails.py (ingen framework).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bookpipe.clean import clean_for_tts
from bookpipe import qc

# Ægte hale ("fx" scorer lavt i _word_quality) skal overleve ordret —
# den gamle haleklipper fjernede den.
LINE = "Vintervedligeholdelse påhviler grundejeren fx"
out = clean_for_tts(LINE, frozenset())
assert out == LINE, f"hale klippet: {out!r}"
print(f"OK hale bevaret: {out!r}")

# qc's frag-signal (med _is_strip_fragment) skal stadig virke.
_, parts = qc.score_page(LINE, frozenset())
assert "frag" in parts, "qc frag-signal mangler"
print(f"OK qc frag-signal intakt: {parts}")

print("GRØN: haler bevares, qc frag-signal intakt")

"""Regressionstest for searchable_pdf.place_top: fallback-laget skal ALTID
rumme alle ord. Et fast step klippede lydløst halen af lange sider
(Vejjura side 52 tabte sidste fodnote: 117/132 ord i laget).
Kør fra repo-roden: python bookpipe/test_place_top.py (ingen framework).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymupdf

from bookpipe.searchable_pdf import place_top

PAGE_W = 595.0
H, s = 800.0, PAGE_W / 1547.0  # typisk sideformat


def check(nwords, label):
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=H * s)
    words = [f"ord{i}" for i in range(nwords)]
    place_top(page, [" ".join(words[i:i + 10]) for i in range(0, nwords, 10)],
              H, s)
    got = page.get_text().split()
    assert len(got) == nwords, f"{label}: {len(got)}/{nwords} ord i laget"
    assert set(got) == set(words), f"{label}: ord mangler i laget"
    for w in page.get_text("words"):
        assert w[3] <= page.rect.height + 1.0, \
            f"{label}: {w[4]!r} uden for siden (y1={w[3]:.1f})"
    print(f"OK {label}: {nwords} ord alle i laget")


check(30, "kort side")
check(132, "Vejjura side 52 (fodnoter)")
check(600, "meget lang side")
print("GRØN: place_top rummer alle ord")

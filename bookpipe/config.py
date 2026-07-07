"""
Indlæs per-bog konfiguration fra en TOML-fil i books/.

Hver bog beskrives af en lille config i stedet for et kopieret script.
Se books/*.toml for eksempler og README for feltbeskrivelser.
"""
import os
import tomllib
from dataclasses import dataclass, field


@dataclass
class BookConfig:
    name: str
    output_dir: str
    voice: str = "da-DK-JeppeNeural"
    # OCR-kilde
    source_photos: str = ""
    source_glob: str = "*.JPG"
    split_spreads: bool = True              # to-side-opslag (ScanTailor layout=2)
    # Kapitler
    detect: str = "manual"                 # "manual" eller "kapitel"
    body_end: int | None = None            # sidste brødtekstside+1 (klip register væk)
    chapters: list = field(default_factory=list)   # manual: [{num, page, title}, ...]
    titles: dict = field(default_factory=dict)     # kapitel: {nr: titel}
    tts_pronounce: list = field(default_factory=list)  # [{pattern, repl}, ...] kun MP3

    @property
    def pages_dir(self):
        return os.path.join(self.output_dir, os.environ.get("BOOKPIPE_PAGES_SUBDIR", "pages_hq"))

    @property
    def txt_dir(self):
        return os.path.join(self.output_dir, os.environ.get("BOOKPIPE_TXT_SUBDIR", "tekst"))

    @property
    def mp3_dir(self):
        return os.path.join(self.output_dir, "mp3")

    @property
    def tmp_dir(self):
        return os.path.join(self.output_dir, "tmp_pages")


def load(path):
    with open(path, "rb") as f:
        data = tomllib.load(f)
    titles = {int(k): v for k, v in data.get("titles", {}).items()}
    return BookConfig(
        name=data["name"],
        output_dir=data["output_dir"],
        voice=data.get("voice", "da-DK-JeppeNeural"),
        source_photos=data.get("source_photos", ""),
        source_glob=data.get("source_glob", "*.JPG"),
        split_spreads=data.get("split_spreads", True),
        detect=data.get("detect", "manual"),
        body_end=data.get("body_end"),
        chapters=data.get("chapters", []),
        titles=titles,
        tts_pronounce=data.get("tts_pronounce", []),
    )

# bog-til-lydbog

Lav en dansk **lydbog** (og ren tekst) ud af **telefonfotos** af en fysisk bog.
Pipelinen splitter dobbeltopslag, kører høj-kvalitets OCR med udretning af
bogryggens krumning, renser teksten for OCR-støj og register/indeks, og
genererer én MP3 pr. kapitel med Microsofts danske neurale stemme.

Kogebog + kode så man ikke starter forfra hver gang der tages billeder af en bog.

---

## Den vigtigste indsigt

> **Rodårsagen til dårlig OCR er som regel IKKE billedkvaliteten — det er bogryggens
> krumning**, der bøjer tekstlinjerne nær falsen og laver volapyk. Telefonfotos af
> en opslået bog er typisk skarpe nok; problemet er geometrien.

Derfor **dewarp** (udretning) frem for at jage bedre kontrast/OCR-engine. Og det
meste af den "svingende kvalitet" man hører i lyden er slet ikke OCR-fejl, men
**register-/indekssider læst højt** — dem klipper vi fra.

---

## Forudsætninger

**1. Tesseract OCR** (med dansk sprogdata)
- Windows: installér fra <https://github.com/UB-Mannheim/tesseract/wiki>, vælg
  sprog **Danish** under install. Standardsti: `C:\Program Files\Tesseract-OCR\`.
- Tjek: `tesseract --version` og at `tessdata\dan.traineddata` findes.
- Andre stier? Sæt miljøvariabler `TESSERACT_EXE` og `TESSDATA_PREFIX`.

**2. Python 3.11+** (testet på 3.14 — `tomllib` er indbygget).

```bash
pip install -r requirements.txt
```

`page-dewarp` trækker `opencv-python` + `matplotlib` med. `wordfreq` bundter den
danske ordliste lokalt (ingen net nødvendig efter install). `edge-tts` bruger
Microsofts gratis online-stemme (kræver internet ved MP3-generering).

---

## Hurtig start

```bash
# 1. Fotografér bogen (se tips nedenfor) til én mappe.
# 2. Opret en config i books/ (kopiér en eksisterende .toml og ret felterne).
# 3. Kør:
python run.py ocr    servitutretten_evald      # split + OCR -> pages_hq/  (langsomt)
python run.py detect servitutretten_evald      # kontrollér kapitel-opdelingen
python run.py txt    servitutretten_evald      # skriv renset tekst (hurtigt, ingen MP3)
python run.py all    servitutretten_evald      # tekst + MP3 for alle kapitler
```

`<bog>` er navnet på config-filen i `books/` uden `.toml`.

---

## Workflow trin for trin

### 1. Fotografér
- Ét **dobbeltopslag** (venstre + højre side) pr. foto, i rækkefølge.
- Så fladt som muligt — pres bogen ned, undgå kraftig krumning ved ryggen.
- Jævn belysning, skarpt fokus, hele opslaget i billedet med lidt margin.
- Konsistent rækkefølge = siderne kommer i rigtig orden automatisk.

### 2. OCR  ·  `python run.py ocr <bog>`
Splitter hvert foto i to sider **ved den detekterede bogryg** (ikke blindt ved
midten — se nedenfor), padder med hvid kant, udretter med `page-dewarp -x 0`, og
OCR'er med Tesseract `--psm 3`. Resultat: `pages_hq/000.txt`, `001.txt`, …
Tager ~15 s/side (4 workers). Rører ingen søgbar PDF.

> **Indholds-bevidst split:** bogen ligger sjældent præcist centreret i billedet,
> så et blindt midtpunkt-split (`w/2`) skærer tekst af den bredeste side (målt:
> en stor del af siderne var ramt). Pipelinen finder i stedet bogryggen som det
> tekst-tyndeste gab mellem de to tekstblokke og splitter dér. Slå fra med
> `split_at_gutter = false` i config, hvis en bog altid er perfekt centreret.

Sider hvor dewarp ikke kan fitte tekstlinjer (figurer/kort/titelsider) falder
tilbage til bilateral filter + adaptiv threshold — de beholder lidt dårligere
diakritik, men det er en lille brøkdel.

### 3. Find kapitelgrænser  ·  `python run.py detect <bog>`
Se afsnittet **Kapitelgrænser og body_end** nedenfor. Juster config og kør
`detect` igen indtil opdelingen ser rigtig ud.

### 4. Tekst og lyd  ·  `python run.py txt <bog>` / `all <bog>`
`txt` skriver kun renset tekst (hurtigt — brug det til at inspicere kvaliteten).
`all` skriver tekst **og** genererer MP3 pr. kapitel. `sample <bog> <nr>` laver
ét enkelt kapitel med lyd.

---

## Tilføj en ny bog

Kopiér en `.toml` i `books/` og ret felterne:

| Felt | Betydning |
|---|---|
| `name` | Vises i output. |
| `output_dir` | Hvor `pages_hq/`, `tekst/`, `mp3/` lægges. Brug **enkelt-quotes** (literal sti, så `\` ikke tolkes). |
| `source_photos` | Mappe med dobbeltopslag-fotos. |
| `source_glob` | Filmønster, fx `"*.JPG"`. |
| `split_spreads` | `true` hvis fotos er dobbeltopslag (næsten altid). |
| `voice` | edge-tts stemme, standard `da-DK-JeppeNeural`. |
| `detect` | `"manual"` (grænser i config) eller `"kapitel"` (find "KAPITEL N"). |
| `body_end` | Sidste brødtekstside + 1. Klipper register/indeks væk. |
| `[[chapters]]` | Kun ved `manual`: `num`, `page` (sideindeks), `title` pr. kapitel. |
| `[titles]` | Kun ved `kapitel`: `nr = "titel"`. |

### Kapitelgrænser og body_end (den manuelle del)

Automatisk detektion er upålidelig på støjet OCR, så grænserne sættes i hånden:

1. Kør `python run.py detect <bog>` — den viser sideintervaller og tegn/kapitel.
2. Åbn `pages_hq/NNN.txt` omkring en formodet grænse og find den side hvor kapitlet
   faktisk starter. Sæt `page` (manual) eller lad `kapitel`-detektion klare det.
3. **body_end:** bladr i de sidste sider og find hvor brødteksten slutter og
   register/litteratur/stikord begynder (typisk linjer som `KFE 1975.147 50,65`
   eller en `Litteratur`/`Domsregister`/`Stikordsregister`-overskrift). Sæt
   `body_end` til den *første* registerside — så læses den og alt efter ikke op.

En nem måde at finde de værste sider: se hvilke `pages_hq`-sider der har flest
ikke-ord-linjer (registre scorer lavt), eller kig blot på de sidste 20 sider.

---

## Hvorfor sådan (beslutninger vi ikke skal genopfinde)

- **Indholds-bevidst split** (find bogryggen pr. foto) frem for blindt midtpunkt.
  Bogen ligger skævt i mange fotos, og midtpunkt-split skar tekst af den bredeste
  side — en overraskende hyppig kilde til "svingende kvalitet". Ryggen findes som
  det tekst-tyndeste gab (projektions-profil), ikke den mørkeste kolonne (som
  fejlagtigt fanger tætte tekstkolonner).
- **Dewarp + Tesseract slår EasyOCR** til denne opgave. EasyOCR gav perfekte
  diakritika men **scramblede læserækkefølgen** i de krumme rygområder og læste
  danske citationstegn `» «` som `m`/`s`/`v`/`<`. Læserækkefølge er afgørende for
  en lydbog, så dewarp+Tesseract vandt.
- **`-x 0` i page-dewarp** undgår at venstre tekstkant beskæres.
- **Hvid padding før dewarp** så kant-tekst ikke remappes ud af billedet.
- **Registertrim (`body_end`)** fjerner det der lyder værst i lyden: sider med
  domsregistre, litteraturlister og stikordsregister læst op som en strøm af tal.
- **Ordbogsfilter** (`wordfreq` + bogens eget korpus) fjerner selvstændige
  volapyk-linjer (`tdi eta lla eh`, `Blithe`). Korpusset er nødvendigt fordi
  domæneord som `servitut` mangler i wordfreq; wordfreq fanger til gengæld
  engelsk enkelt-token-volapyk. Holdt **konservativt** (fjern kun linjer helt
  uden et rigtigt ord), så rigtige korte billedtekster/overskrifter bevares.
- **PDF vs. TTS-tekst er adskilt.** En søgbar OCR-PDF kan laves med lettere
  behandling; denne pipeline er den langsommere, høj-kvalitets tekst til oplæsning.

## Kendte begrænsninger

- Få 2-token-fragmenter med ét tilfældigt rigtigt ord (`Fyre`, `TRIO Error`)
  overlever — at fange dem ville risikere rigtige stednavns-billedtekster.
- På fallback-sider smelter kort volapyk nogle gange sammen med rigtig tekst
  (`im ikk taal tans, bal tilladelse...`); det kræver sætnings-niveau korrektion
  at fjerne sikkert.

---

## Fejlfinding

| Symptom | Årsag / løsning |
|---|---|
| `UnicodeEncodeError ... charmap` | Windows cp1252-konsol. `run.py` sætter selv UTF-8; kald ellers med `PYTHONIOENCODING=utf-8`. |
| `cv2.imread ... can't open` på æ/ø-stier | OpenCV kan ikke Unicode-stier — pipelinen indlæser derfor via PIL. |
| Kapitler starter forkert | Juster `page`/`body_end` i config, kør `detect` igen. |
| Mange fallback-sider | Bogen er meget krum, eller siderne er mest figurer. Prøv fladere fotos. |
| Ingen MP3 / netværksfejl | edge-tts kræver internet; der er indbygget retry (5 forsøg). |

---

## Filstruktur

```
bog-til-lydbog/
  run.py                 # CLI
  requirements.txt
  README.md              # denne kogebog
  bookpipe/
    ocr.py               # split + dewarp + Tesseract -> pages_hq/
    clean.py             # al tekstrensning + reflow
    dictionary.py        # wordfreq + korpus-ordbog (volapyk-filter)
    chapters.py          # detektion, opdeling, skrivning af tekst/MP3
    tts.py               # edge-tts med retry
    config.py            # indlæs per-bog .toml
  books/
    private_faellesveje_ramhoej.toml
    servitutretten_evald.toml
```

Output (`pages_hq/`, `tekst/`, `mp3/`, `tmp_pages/`) lægges i hver bogs
`output_dir` — **uden for** repoet.

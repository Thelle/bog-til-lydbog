# bog-til-lydbog

Lav en dansk **lydbog** (og ren tekst) ud af **telefonfotos** af en fysisk bog.
Pipelinen splitter dobbeltopslag, kører høj-kvalitets OCR med udretning af
bogryggens krumning, renser teksten for OCR-støj og register/indeks, og
genererer én MP3 pr. kapitel med Microsofts danske neurale stemme.

Kogebog + kode så man ikke starter forfra hver gang der tages billeder af en bog.

---

## Den vigtigste indsigt

> **Det der lyder som "scramblet" OCR er sjældent uskarpe billeder — det er tre
> konkrete, målbare ting:** (1) bogryggens **krumning**, der får en linjes højre
> halvdel til at "dryppe" ned i næste linje; (2) **gennemslag** — den svage
> spejlvendte tekst fra bagsiden, som OCR læser som støj-tokens midt i teksten;
> og (3) **register-/indekssider læst højt**. Telefonfotos af en opslået bog er
> typisk skarpe nok; problemet er geometri, gennemslag og layout.

Derfor angriber pipelinen dem ét for ét: **dewarp** (ScanTailor) mod krumning,
**hvidpunkt-klip** mod gennemslag, **EasyOCR** mod dryp-scramble, og
**register-/§-boks-/fodnote-filtre** mod det der ikke skal læses højt.

---

## Forudsætninger

**1. ScanTailor Advanced** (split + deskew + dewarp)
- Det gennemtestede værktøj til efterbehandling af scannede bogsider. Klarer den
  indholds-bevidste sideopdeling, deskew og dewarp (bogryg-krumning) robust.
  Kører i **grayscale** (`color_grayscale`), ikke 1-bit — det bevarer diakritika
  (æøå) og § langt bedre.
- Windows: installér ScanTailor Advanced. Pipelinen bruger `scantailor-cli.exe`.
  Standardsti: `C:\Program Files\Scan Tailor\scantailor-cli.exe`.
- Anden sti? Sæt miljøvariabel `SCANTAILOR_CLI`.

**2. EasyOCR** (dansk + engelsk, via pip)
- Installeres med `pip install -r requirements.txt`. Første kørsel henter
  sprogmodellerne (kræver internet én gang).
- Kører på CPU (~40 s/side). Slår Tesseract på **læserækkefølge** ved krumme
  sider og holder §-citatbokse som separate blokke (se beslutninger nedenfor).

**3. Python 3.11+** (testet på 3.14 — `tomllib` er indbygget).

```bash
pip install -r requirements.txt
```

Pip-pakker: `easyocr` (OCR), `wordfreq` (dansk ordliste lokalt) og `edge-tts`
(Microsofts gratis online-stemme, kræver internet ved MP3-generering).
Sideopdeling/dewarp laver ScanTailor.

---

## Hurtig start

```bash
# 1. Fotografér bogen (se tips nedenfor) til én mappe.
# 2. Opret en config i books/ (kopiér en eksisterende .toml og ret felterne).
# 3. Kør:
python run.py ocr    servitutretten_evald      # split + OCR -> pages_hq/  (langsomt)
python run.py detect servitutretten_evald      # kontrollér kapitel-opdelingen
python run.py qc     servitutretten_evald 15   # ranger de 15 mest mistænkelige lyd-sider
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
Tre trin: (1) **ScanTailor** (`--layout=2 --deskew=auto --dewarping=auto
--color-mode=color_grayscale`) opdeler hvert opslag ved bogryggen, retter skævhed
og krumning, og udsender grå-skala sidebilleder; (2) **hvidpunkt-klip** klipper
den grå baggrund + gennemslag fra bagsiden til hvidt (styres af `OCR_WHITE_POINT`,
standard 165); (3) **EasyOCR** (paragraph-mode) OCR'er hver side i rigtig
læserækkefølge. Resultat: `pages_hq/000.txt`, `001.txt`, … Rører ingen søgbar PDF.

> **Hvorfor ScanTailor til opdelingen:** bogen ligger sjældent præcist centreret
> i billedet, så et blindt midtpunkt-split (`w/2`) skærer tekst af den bredeste
> side (målt: en stor del af siderne var ramt — en overraskende stor kilde til
> "svingende kvalitet"). ScanTailor finder bogryggen indholds-bevidst og
> deskewer/dewarper hver side. Sæt `split_spreads = false` i config for bøger
> fotograferet én side ad gangen (ScanTailor layout=1).

### 2b. Alternativ OCR: PaddleOCR (en mulig fremgangsmåde)
EasyOCR's paragraph-mode **scrambler læserækkefølgen** på stærkt krumme fotos
(højre ende af en linje falder ned i næste linje → "vejrettens oprin -
kerakteofra"). Ingen ordbog/heuristik kan rette rækkefølge-fejl. **PaddleOCR
(PP-OCRv6, `lang="da"`) løser det ved roden**: korrekt rækkefølge + korrekt æøå
+ verbatim (ikke generativ → ingen hallucination). Det er mere opsætning, men
kan være vejen når EasyOCR-resultatet svinger. Fremgangsmåden vi brugte til
begge nuværende bøger:

1. **Separat venv** (paddlepaddle har ingen wheels til Python 3.14): lav et
   Python 3.12-venv med `uv` og installér `paddlepaddle==3.2.2 paddleocr==3.7.0`
   (`numpy>=2,<3`). Vigtigt: **paddle 3.2.2** — 3.3.1 har en oneDNN/PIR-bug der
   gør CPU-inferens ~50x langsommere; 3.0.0 kan ikke loade v6-modellerne.
2. **OCR** (`bookpipe/paddle_ocr.py`, køres i det venv) er env-konfigurerbar.
   "Config B" (komplet — det vi endte med):
   `OCR_DEWARP=off OCR_UNWARP=1 OCR_MKLDNN=1 OCR_LIMIT=3000
   OCR_PAGES_SUBDIR=pages_hq_B`. Pointe: lad *kun* PaddleOCR udrette
   (`use_doc_unwarping`), ikke ScanTailor — dobbelt-udretning taber linjer.
3. **Merge** (`bookpipe/merge_ocr.py`, normal 3.14): PaddleOCR's detektion har
   ~95-99% recall, ikke 100%, og *hvilke* linjer den taber afhænger af
   forbehandling. Kør evt. en "Config A" (dewarp=on, unwarp=off → `pages_hq`)
   som fallback og flet på side-niveau: B primær (komplet krop), A hvor B fejlede.
4. **To tekstversioner:** `BOOKPIPE_KEEP_FOOTNOTES=1` +
   `BOOKPIPE_TXT_SUBDIR=tekst_med_fodnoter` giver en "med fodnoter"-kopi;
   standard fjerner fodnoter (til MP3). `BOOKPIPE_PAGES_SUBDIR` vælger kilde-mappe.

Dette trin erstatter `run.py ocr` ovenfor; resten (detect/txt/all) kører
uændret på `pages_hq/`. Bemærk også: hvis en bogs VERSAL-"KAPITEL N"-openere er
garblede, kan `detect="kapitel"` folde kapitler sammen — sæt da manuelle
kapitel-grænser i config'en (se `books/servitutretten_evald.toml`, hvor Kap 9/11
er sat manuelt af netop den grund).

### 2c. Nabostrimler: ydre projektion + fals-klip ved påvist grænse (B2c)
ScanTailor-sider indeholder ofte nabotekst to steder: **yderkanten**
(fotobaggrund/naboside) og **falsen** (søstersiden krummer ind i billedet).
Falsstrimlen er den værste — den kan vælte hele sidens layout-læsning
(målt: indholdsside hvor sidetallene blev læst som 36 løse tal-linjer og
punktlinjerne forsvandt; efter klip: korrekt TOC med punktlinjer).
Metoden der vandt på Vejjura-bogen (MistralOCR, 25 prøvesider):
1. **Yderkant:** mørk-pixel-projektion udefra, klip max 8 %. Falsen røres aldrig
   her — det fjerner ydre strimler uden nogensinde at ramme tekst (99,9 %
   bevaret på prøvesættet).
2. **Fals:** DocTR-orddetektion (`db_resnet50`, score ≥ 0,3 — 0,5 er for strengt
   til svage strimler), klyng bokse, og klip KUN ved påviste smalle (<12 % af
   bredden), frakoblede klynger fuldt inde i falsbåndet (15 %) + 15 px margin.
   **Krydsnings-garde:** hvis én brødtekstboks krydser snitlinjen, droppes
   fals-klippet på den side. 0 overtrædelser på 25 sider; eyeball bekræfter
   intakte TOC-tal og brødtekst.
3. **Dumpet alternativ:** blind beskæring til boks-union med faste caps klippede
   ægte tekst (TOC-side 8698→3215 tegn, afklippede sidetal) — aldrig klip blindt.

Målt effekt: ~6 % støjtegn fjernet (16/25 sider ramt, 100–500 tegn/side),
samme 29 TOC-opslag før/efter men læsbar layout. Falsstrimler for svage til
detektion overlever som reststøj.
**Advarsel (Mistral):** nær-blanke sider hallucineres ikke-deterministisk
(32–45k tegn på én blank side, forskelligt pr. kørsel). Spring sider med
0 detektionsbokse over ved re-OCR — ellers risikerer et re-run at *introducere*
hallucinationer på sider der er rene i dag.

### 2d. MistralOCR + B2c: modstående sider er løst ved kilden — spring haleklip over

B2c klipper nabostrimler ved kilden på billedniveau (afsnit 2c), og MistralOCR
læser kun den rene side. Der kommer derfor ikke længere tekst fra den
modstående side ind i sideteksten, og tekst-niveauets haleklippere i `clean.py`
(`_clean_line`s hale-regex + `_strip_trailing_garbage_words`) er forældede på
Mistral/B2c-kilder. De var skrevet til ScanTailor/EasyOCR-tiden, hvor
gennemskin og nabostrimler efterlod støj-tokens i linjernes haler — på rene
kilder klipper de i stedet ægte haler af ("klippede haler"). Samme mønster som
`_is_strip_fragment`, der allerede er fjernet af netop den grund: når strimlen
fjernes ved kilden, giver tekst-filteret kun falske positiver.

Workflow for Mistral/B2c-bøger: kør MistralOCR på de B2c-klippede sider og brug
sideteksten direkte — kør ikke EasyOCR-tidens hale-rensning på den.
Vejjura-bogens 12 B2c-kapiteltekster er verificeret uden afklippede haler.

### 3. Find kapitelgrænser  ·  `python run.py detect <bog>`
Se afsnittet **Kapitelgrænser og body_end** nedenfor. Juster config og kør
`detect` igen indtil opdelingen ser rigtig ud.

### 4. Kvalitetstjek  ·  `python run.py qc <bog> [N]`
Ranger de N mest mistænkelige **lyd-sider** (0 = ren, 1 = slem) ud fra fire
billige signaler: ordbogs-junk, gennemsnitlig ordkvalitet, fragment-andel og
tæthed af ' - '-dryp. Sider uden for `body_end`/kapitler (register, indhold)
tælles ikke med. Formålet er feedback-loopet **ocr → qc → læs de værste → ret
roden**: heuristikken kan ikke selv *forstå* teksten, men den peger på de sider
en menneske-/LLM-læsning skal fokusere på. To typiske fund: (1) få
near-total-loss-sider (OCR svigtede helt → re-OCR); (2) scramblede toppe/bunde
(løbende headere, fodnoter, dryppende linjer nær falsen).

### 5. Tekst og lyd  ·  `python run.py txt <bog>` / `all <bog>`
`txt` skriver kun renset tekst (hurtigt — brug det til at inspicere kvaliteten).
`all` skriver tekst **og** genererer MP3 pr. kapitel. `sample <bog> <nr>` laver
ét enkelt kapitel med lyd. Udtale-hints (`[[tts_pronounce]]` i config) bruges
**kun** til MP3 — fx `vejret` -> `vej-ret` så oplæsningen betyder "ret til en
vej", ikke vejr-fænomenet; tekstfilen forbliver korrekt dansk.

### 6. Søgbar PDF · Tesseract-lag (kun til søgning)

Resten af pipelinen (OCR til txt, lydbog og PDF uden OCR-lag) røres ikke
— **Tesseract bruges alene til søgelaget**, som ikke behøver være
perfekt. Hvert sidebillede køres med Tesseract dansk (`-l dan`) til hOCR,
og hvert ord lægges usynligt (`render_mode=3`) **i sin egen
geometri-tro boks**: fontsize = bokshøjde x 0,85, skaleret ned hvis
ordet er bredere end boksen. Ingen reflow, ingen mapping —
søgeudpegningen sidder dér hvor ordet står på billedet.

Forudsætning: `tesseract` + dansk sprogdata (Ubuntu:
`sudo apt install tesseract-ocr tesseract-ocr-dan`; Windows:
Tesseract-installeren + `dan.traineddata` i tessdata).

Fremgangsmåde (målt på Vejjura, 270 sider):
1. **Prototype først:** byg 2-3 repræsentative sider, åbn PDF'en og
   søg efter et særpræget ord (fx `byggelinje`) — udpegningen skal
   sidde på selve ordet. Sammenlign med samme sider i den gamle PDF.
2. **Fuld bygning til NYT filnavn** (overskriv aldrig) — ca. 2-3 s/side.
3. **Verificér uafhængigt:** søgeprober med y-bånd (hittet skal ramme
   dér hvor ordet faktisk står — fanger "stablede" ord på samme
   linje), optælling af tomme lag (kun reelt blanke sider må være
   tomme) og font-sundhed (ingen mikrofont i brødtekst).

Kontrakter og fælder:
- **Støjfilter:** spring bokse under 8 kildepixels over (målt: støj
  0-4 px, brødtekst 10 px+ på ~1400x2000-sider) — ellers ender
  fragmenter som søgbare enkeltbogstaver.
- **PSM-fallback med dansk-gate:** PSM 3-segmenteringen opgiver visse
  krumme sider helt ("Empty page!!"). Ved tom side prøves `--psm 6`,
  men resultatet lægges kun i laget hvis det ligner dansk (>= 20
  stopord) — ellers gætter PSM 6 løs på figursider og forurener
  søgningen. Regressionstest: `test_tesseract_layer.py` (7 tjek,
  kræver ikke tesseract-binaren).
- **Latin-1-sanitize** som før (samme tegn-map); uerstattelige tegn
  bliver `?`. Tesseract læser selvstændigt, så enkelte ord kan stå
  anderledes end i pipeline-teksten — laget er til søgning, ikke paritet.
- Den ældre DocTR-mapping-vej (`bookpipe/searchable_pdf.py`) er
  **forladt** til søgelag: se dumpede spor 6-8.

Målt (Vejjura_OCR_TESS_B2c.pdf): 270 sider, ~89.800 søgbare ord,
3 PSM-fallbacks, 7 tomme lag — alle forklarede (3 blanke, 2 figursider
afvist som støj, 2 kun-sidetal).
Arkivér det færdige resultat som tidsstemplede snapshots
`<YYYY-MM-DD_HH-MM>_<kilde>` (fx `2026-09-17_10-34_pages_B2c_txt`) — ét
sæt pr. kørsel, så historik aldrig overskrives og intet blandes
sammen; nyeste timestamp = bedste. Opdateringsscriptet opretter kun nyt
snapshot ved ændret indhold.
Sættet dækker sidetekster, kapiteltekster, MP3 og PDF med
søgelag.

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

- **ScanTailor til split + deskew + dewarp** frem for håndkodet billedbehandling.
  Bogen ligger skævt i mange fotos, og et blindt midtpunkt-split skar tekst af den
  bredeste side — en overraskende hyppig kilde til "svingende kvalitet". ScanTailor
  finder bogryggen indholds-bevidst og deskewer/dewarper robust. (En tidligere
  custom pipeline med projektions-profil-split + `page-dewarp` virkede, men
  ScanTailor er renere, mere komplet og mindre kode at vedligeholde.)
- **Grayscale, ikke 1-bit.** ScanTailors `black_and_white` laver tegnfejl på
  diakritika ("feellesvej", "$" for "§"). `color_grayscale` bevarer dem — men så
  følger den grå baggrund og **gennemslaget** med, hvilket løses i næste punkt.
- **Hvidpunkt-klip mod gennemslag.** Telefonfotos har ingen ren hvid baggrund
  (hele siden måler ~200 grå), og den svage spejlvendte tekst fra bagsiden bliver
  OCR'et som støj-tokens ("NE", "A b") midt i linjerne — det der lignede scramble.
  Et simpelt hvidpunkt-klip (lyst -> hvidt) fjerner det uden at røre den mørke tekst.
- **EasyOCR slår Tesseract** — efter grayscale+hvidpunkt. Tesseracts rækkebaserede
  layout-analyse flækker linjer hvis højresiden "drypper" nær ryggen
  ("servitutforpligtet udfører" bliver til to stumper). EasyOCR detekterer
  tekst-regioner enkeltvis og bevarer rækkefølgen. Dens svagheder (semikolon for
  komma, mistede `» «`) er **stumme i oplæsning**. Pris: ~40 s/side mod ~0,7 s.
  (§ læses som `$`, `og` som `0g`/`%g` — rettes i `clean.normalize_easyocr`.)
- **§-citatbokse droppes.** De grå, kursiverede lovtekst-bokse har lav kontrast og
  er svære at få i rækkefølge; de gengiver ordret lovtekst der også er dækket i
  brødteksten. EasyOCR holder dem som blokke der starter med "§ NN.", så
  `clean._is_statute_box` fjerner dem fra både tekst og lyd. (Billed-maskering blev
  fravalgt: hele siden er grå, så §-boksen kan ikke isoleres pålideligt på niveau.)
- **Registertrim (`body_end`)** fjerner det der lyder værst i lyden: sider med
  domsregistre, litteraturlister og stikordsregister læst op som en strøm af tal.
- **Ordbogsfilter** (`wordfreq` + bogens eget korpus) fjerner selvstændige
  volapyk-linjer (`tdi eta lla eh`, `Blithe`). Korpusset er nødvendigt fordi
  domæneord som `servitut` mangler i wordfreq; wordfreq fanger til gengæld
  engelsk enkelt-token-volapyk. Holdt **konservativt** (fjern kun linjer helt
  uden et rigtigt ord), så rigtige korte billedtekster/overskrifter bevares.
- **PDF vs. TTS-tekst er adskilt.** En søgbar OCR-PDF kan laves med lettere
  behandling; denne pipeline er den langsommere, høj-kvalitets tekst til oplæsning.
- **Søgelag med Tesseract-bokse, ikke mapping.** Søgning skal ramme
  præcist (fx `byggelinje`), men laget behøver ikke matche
  pipeline-teksten ordret — derfor læser Tesseract billederne
  selvstændigt til hOCR i stedet for at fordele andres ord. Se trin 6.

## Dumpede spor (læs før du genopfinder dem)

1. **Blind union-beskæring med faste caps (B2b).** Beskær til DocTR-boksenes
   union ± margin, max 12/14 %. Caps ramte på 18/20 sider og klippede ægte
   tekst (TOC-side 8698→3215 tegn, afklippede sidetal på eyeball). Læring:
   klip ALDRIG blindt — kun ved påvist strimlegrænse + krydsnings-garde
   (se 2c). En garde der aldrig slår til er stadig værd at have: 0 ABORTs på
   25 sider er selve sikkerhedsbeviset.
2. **DocTR-detektion på opslag-niveau.** For svag recall på nedskalerede
   dobbeltsider (en håndfuld bokse til to sider) — detektion skal køre pr.
   side i fuld opløsning.
3. **DocTR-score 0,5 til svage strimler.** Falsstrimlen på side 026 gav 0 bokse
   ved 0,5, men 41 ordbokse ved 0,3 (ordstore, over hele søjlehøjden = ægte
   tekst). Læring: tærsklen er recall-kritisk for svagt tryk — validér altid
   på den svageste side, og kræv ≥2 bokse pr. klynge mod støj.
4. **Overlap/tiling af opslag (spor A).** Afvist på data: strimlerne sidder i
   falsen + yderkanten, så overlap fjerner dem ikke — det fordobler kun
   OCR-regningen. Læring: bestem strimlens PLACERING med eyeball (tegn
   snitlinjer på siden) før du vælger metode.
5. **Paddle-detektion til split (B1).** Blokeret: paddle 3.3.1 har en
   oneDNN/PIR-bug (`ConvertPirAttribute`, ~50x langsommere CPU) + manglende
   libgomp. Læring: pin `paddle==3.2.2` (se 2b) og mål detektorens runtime på
   ÉN side før batch.
6. **Flowed usynlig tekst i søgbar PDF.** Hele sidens tekst i én
   `insert_textbox` giver søgetræf på tilfældige steder — og når teksten
   overstiger boksen (>~70 linjer v. 8 pt) skriver PyMuPDF INTET (returværdi
   negativ, scriptet ignorerede den): 83/270 sider uden tekstlag. Læring:
   tjek altid `insert_textbox`' returværdi, læg tekst pr. linje/ord på
   detekterede bokse, og assert at ingen ikke-tomme sider har tomt lag.
7. **Fast-step fallback i søgbart lag.** `place_top` med fast 7 pt-step
   stoppede ved sidebunden og tabte lydløst ~16 ord (Vejjura side 52:
   sidste fodnote "11. Falk …" usøgbar) mens builderen rapporterede succes
   — alle linjer var "behandlet", halen blev bare klippet af
   stop-betingelsen. Læring: fallback skal garantere ALLE ord (skaleret
   step efter ordantal) + uafhængig ord-for-ord-verificering bagefter, der
   tæller søgbarhed, ikke indsættelser (se trin 6).
8. **Brøkvis afsnits->slot-mapping (mikrofont + stabling).** Mistrals
   linjer er afsnit, ikke visuelle linjer; brøkvis fordeling (linje i ->
   slot round(i*(K-1)/(M-1))) stoppede hele afsnit ned i ÉN slot (målt
   side 61: 28-ords afsnit, fontsize ned til 1,8 pt) og stablede ord på
   samme linje (5 identiske y-hits) så søgeudpegningen sad ved siden
   af ordet. Læring: læg aldrig afsnits-ord i linje-slots via
   positionsbrøk — brug geometri-tro bokse (trin 6).
9. **Blind PSM 6-fallback i Tesseract-lag.** PSM 3 opgiver krumme sider
   helt ("Empty page!!" — side 150 med 83 reelle ord), men `--psm 6`
   gætter løs på figursider (94/276 ord fragment-støj på 052/112).
   Læring: fallback kun med dansk-gate (>= 20 stopord: 150 giver 43,
   figursider 9) — ellers forurenes søgningen med volapyk-hits.

## Kendte begrænsninger

- **Kapitel-åbningssider og fodnote-tunge sider** kan stadig scramble lidt: stor
  titel + indryk + fodnote-blok forvirrer læserækkefølgen. Det er få sider pr. bog
  og typisk i starten af et kapitel. Fodnoter filtreres desuden fra i `clean.py`.
- Få 2-token-fragmenter med ét tilfældigt rigtigt ord (`Fyre`, `TRIO Error`)
  overlever — at fange dem ville risikere rigtige stednavns-billedtekster.
- **§-citatbokse fjernes helt** (se beslutninger). Ønsker man lovteksten med,
  slå `clean._is_statute_box`-filteret fra — men forvent scramblet rækkefølge i
  de grå bokse.
- ScanTailors auto-mode rammer langt de fleste sider, men kan enkeltvis vælge en
  suboptimal split/content-boks (fx figur- eller titelsider). Kør bogen gennem
  ScanTailor **GUI'en** og ret dem visuelt, hvis en side ser forkert ud, og OCR
  derefter output-billederne.
- **Hastighed:** EasyOCR på CPU er ~40 s/side (≈3 t for en bog på ~250 sider).
  Kør OCR-trinnet natten over. Har du et CUDA-GPU, kan `gpu=True` i `ocr.py`
  sætte farten markant op.

---

## Fejlfinding

| Symptom | Årsag / løsning |
|---|---|
| `UnicodeEncodeError ... charmap` | Windows cp1252-konsol. `run.py` sætter selv UTF-8; kald ellers med `PYTHONIOENCODING=utf-8`. |
| ScanTailor finder ikke / 0 sider | Tjek stien til `scantailor-cli.exe` (sæt `SCANTAILOR_CLI`). Æ/ø i kildesti håndteres ved at kopiere til ASCII-navne først. |
| Sider opdelt/skæve forkert | Kør bogen i ScanTailor **GUI'en**, ret split/deskew visuelt, OCR så output. |
| Kapitler starter forkert | Juster `page`/`body_end` i config, kør `detect` igen. |
| Ingen MP3 / netværksfejl | edge-tts kræver internet; der er indbygget retry (5 forsøg). |

---

## Filstruktur

```
bog-til-lydbog/
  run.py                 # CLI
  requirements.txt
  README.md              # denne kogebog
  bookpipe/
    ocr.py               # ScanTailor (grayscale) + hvidpunkt + EasyOCR -> pages_hq/
    clean.py             # tekstrensning + reflow (§-boks-drop, de-hyphenering, strip-filter)
    dictionary.py        # wordfreq + korpus-ordbog (volapyk-filter)
    chapters.py          # detektion, opdeling, skrivning af tekst/MP3 (+ udtale-hints)
    qc.py                # kvalitetstjek: ranger mistænkelige sider (feedback-loop)
    searchable_pdf.py    # søgbar PDF: linjeforankret usynligt lag + fit-fallback
    verify_pdf.py        # uafhængig verificering: tomme lag, ordsøgning, prober
    test_place_top.py    # regressionstest: fallback rummer alle ord (ingen framework)
    tts.py               # edge-tts med retry
    config.py            # indlæs per-bog .toml
  books/
    private_faellesveje_ramhoej.toml
    servitutretten_evald.toml
```

Output (`pages_hq/`, `tekst/`, `mp3/`) lægges i hver bogs `output_dir` —
**uden for** repoet. ScanTailor/Tesseract-mellemfiler ligger i en temp-mappe.

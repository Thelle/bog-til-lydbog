# Dumpede spor (læs før du genopfinder dem)

Appendix til kogebogen (`README.md`). Hver vej nedenfor er prøvet på data og
dumpet af en målt grund — genbrug læringen i stedet for at gå sporet igen.

1. **Blind union-beskæring med faste caps (B2b).** Beskær til DocTR-boksenes
   union ± margin, max 12/14 %. Caps ramte på 18/20 sider og klippede ægte
   tekst (TOC-side 8698→3215 tegn, afklippede sidetal på eyeball). Læring:
   klip ALDRIG blindt — kun ved påvist strimlegrænse + krydsnings-garde
   (se README 2c). En garde der aldrig slår til er stadig værd at have:
   0 ABORTs på 25 sider er selve sikkerhedsbeviset.
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
   libgomp. Læring: pin `paddle==3.2.2` (se README 2b) og mål detektorens
   runtime på ÉN side før batch.
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
   tæller søgbarhed, ikke indsættelser (se README trin 6).
8. **Brøkvis afsnits->slot-mapping (mikrofont + stabling).** Mistrals
   linjer er afsnit, ikke visuelle linjer; brøkvis fordeling (linje i ->
   slot round(i*(K-1)/(M-1))) stoppede hele afsnit ned i ÉN slot (målt
   side 61: 28-ords afsnit, fontsize ned til 1,8 pt) og stablede ord på
   samme linje (5 identiske y-hits) så søgeudpegningen sad ved siden
   af ordet. Læring: læg aldrig afsnits-ord i linje-slots via
   positionsbrøk — brug geometri-tro bokse (README trin 6).
9. **Blind PSM 6-fallback i Tesseract-lag.** PSM 3 opgiver krumme sider
   helt ("Empty page!!" — side 150 med 83 reelle ord), men `--psm 6`
   gætter løs på figursider (94/276 ord fragment-støj på 052/112).
   Læring: fallback kun med dansk-gate (>= 20 stopord: 150 giver 43,
   figursider 9) — ellers forurenes søgningen med volapyk-hits.

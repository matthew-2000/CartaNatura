# Carta Natura — baseline GIS post-stabilizzazione

Data: **4 settembre 2026**  
Stato: **baseline ufficiale della milestone GIS**  
Ambito: correttezza geometrica, categorie vegetazionali, CO2 deterministica e valori economici derivati. Non costituisce un giudizio di prontezza dell'intero esperimento.

## Metodo riproducibile

- Il layer Carta Natura viene validato nel CRS sorgente **EPSG:32633**.
- Le geometrie sorgente invalide sono riparate con `shapely.make_valid` prima della conversione a EPSG:4326 e del clipping.
- Una riparazione viene rifiutata se produce geometrie non areali, resta invalida/vuota o cambia l'area relativa oltre `1e-9`.
- Dopo il clipping, ogni geometria risultante viene riproiettata in **EPSG:32633** e `ettari` viene sovrascritto con `geometry.area / 10.000`.
- I 24 codici distinti presenti nel dataset sono tutti classificati. L'insieme delle esclusioni esplicite è attualmente vuoto.
- Summary, categorie, top category e CO2 sono prodotti dal core backend condiviso da GUI e conversational.
- I valori economici sono `totalCo2 × prezzo`, senza modifica dei quattro coefficienti di prezzo esistenti.
- I valori tabellari sono arrotondati a due decimali soltanto per la presentazione; i calcoli economici usano il float non arrotondato.

## Identità dei dataset

| File | SHA-256 |
|---|---|
| `shapeCN/CNPulita.shp` | `eaa634322ded9fa753d1ba4da079c2dd04d52abcfdee3c3a23455f55ca8fe2d4` |
| `shapeCN/CNPulita.dbf` | `35c5cda8f6a0aa31ea37917296ee6ac219fbdd1c9112aca3a07a7c51ab6ff172` |
| `shapeCN/CNPulita.shx` | `0461dfe94c58939d1b75b0817560ae8e361d3dd0aecc23ebcf60e2c7ff06f308` |
| `shapeCN/CNPulita.prj` | `228d99c48fb48491aa26f6fd3732051c70d4d0cd578fb21a56297b3678d397ad` |
| `campania-municipalities-32633.geojson` | `e54b88d10dc653d62849557b3197c328aa50a7f30cc58a8b52ed52e6a5fe42d4` |
| `moddedCampania.geojson` | `b05ce1e77900f747f024d87851dce5d367fa05a514b859d668fb396a51436683` |

## Baseline principale

| Area | Superficie, ha | Categorie | Categoria prevalente | CO2, t/anno | CO2/ha, t/ha/anno |
|---|---:|---:|---|---:|---:|
| Benevento | 805,44 | 3 | Querceti di roverella | 2.795,85 | 3,47 |
| Montella | 4.477,97 | 8 | Faggete | 32.560,57 | 7,27 |
| Avellino | 66,97 | 3 | Castagneti | 338,51 | 5,05 |
| Salerno | 1.651,61 | 7 | Leccete | 8.071,15 | 4,89 |
| Caserta | 1.070,29 | 3 | Querceti di roverella | 4.476,63 | 4,18 |
| Serino | 2.428,70 | 6 | Castagneti | 15.371,00 | 6,33 |
| Avellino + Salerno | 1.718,59 | 7 | Leccete | 8.409,66 | 4,89 |

La baseline congiunta coincide, entro la precisione floating-point, con la somma delle superfici e della CO2 delle due analisi singole: i comuni non si sovrappongono e la maschera viene trattata come unione.

## Categorie per area

Superficie post-clip in ettari, arrotondata a due decimali.

| Area | Categorie riconosciute |
|---|---|
| Benevento | Boschi igrofili 329,91; Querceti di roverella 460,51; Altri boschi di conifere, pure o miste 15,02 |
| Montella | Boschi igrofili 11,11; Querceti di roverella 103,28; Ostrieti e carpineti 858,91; Leccete 275,55; Altri boschi caducifogli 4,18; Cerrete e boschi di farnetto 754,30; Castagneti 344,41; Faggete 2.126,23 |
| Avellino | Boschi igrofili 3,53; Querceti di roverella 23,48; Castagneti 39,96 |
| Salerno | Boschi igrofili 44,31; Querceti di roverella 492,48; Ostrieti e carpineti 150,90; Leccete 752,87; Pinete di pini mediterranei 15,18; Castagneti 167,64; Altri boschi di conifere, pure o miste 28,22 |
| Caserta | Querceti di roverella 754,66; Leccete 280,17; Altri boschi di conifere, pure o miste 35,46 |
| Serino | Boschi igrofili 3,21; Querceti di roverella 226,52; Ostrieti e carpineti 610,17; Leccete 82,20; Castagneti 878,10; Faggete 628,50 |
| Avellino + Salerno | Boschi igrofili 47,83; Querceti di roverella 515,97; Ostrieti e carpineti 150,90; Leccete 752,87; Pinete di pini mediterranei 15,18; Castagneti 207,61; Altri boschi di conifere, pure o miste 28,22 |

## Scenari economici derivati

| Area | Costo sociale, 138 EUR/t | Prezzo ombra, 303 EUR/t | Mercato regolamentato, 82 EUR/t | Mercato volontario, 20 EUR/t |
|---|---:|---:|---:|---:|
| Benevento | 385.826,89 EUR | 847.141,65 EUR | 229.259,46 EUR | 55.916,94 EUR |
| Montella | 4.493.359,24 EUR | 9.865.853,99 EUR | 2.669.967,09 EUR | 651.211,48 EUR |
| Avellino | 46.714,02 EUR | 102.567,74 EUR | 27.757,61 EUR | 6.770,15 EUR |
| Salerno | 1.113.819,34 EUR | 2.445.559,85 EUR | 661.834,68 EUR | 161.423,09 EUR |
| Caserta | 617.774,76 EUR | 1.356.418,50 EUR | 367.083,56 EUR | 89.532,57 EUR |
| Serino | 2.121.197,59 EUR | 4.657.412,11 EUR | 1.260.421,76 EUR | 307.419,94 EUR |
| Avellino + Salerno | 1.160.533,36 EUR | 2.548.127,59 EUR | 689.592,29 EUR | 168.193,24 EUR |

## Verifica GUI/conversational

Per ciascuna delle sette aree, `analyze_municipalities(names)` è stato confrontato con `analyze_selection(build_municipality_selection_payload_dict(names))`. I dizionari `summary` sono risultati **esattamente uguali**, inclusi:

- `totalHectares`;
- lista e ordine degli `items`;
- ettari e coefficienti per categoria;
- `topCategory`;
- `totalCo2`;
- `hasSupportedVegetation`.

Un test di regressione separato confronta inoltre l'endpoint HTTP GUI `/gis` con il tool conversazionale usando la stessa geometria sintetica metrica.

## Geometrie sorgente invalide

Il file sorgente contiene 21 Polygon segnalati da GEOS come `Ring Self-intersection`. L'applicazione standardizzata di `make_valid`:

- conserva 10.058 record;
- produce 21 Polygon validi, nessuna geometria vuota o non areale;
- modifica l'area aggregata delle 21 geometrie di meno di `1e-10 ha`, quindi molto sotto la soglia fail-closed;
- non cambia area o CO2, neppure alla precisione float osservata, per le sette baseline sopra rispetto al clipping eseguito senza repair nell'ambiente auditato.

La riparazione non è quindi usata per “aggiustare” quantitativamente i risultati: elimina una dipendenza dal comportamento implicito di GEOS, mantenendo invariata l'area osservata. Dataset futuri con riparazioni materialmente diverse saranno rifiutati.

## Artefatti invalidati

- `asita-2026-feasibility-check.md`: tutti i valori numerici, confronti e riscontri economici della pipeline precedente sono obsoleti; il documento resta storico.
- `system-design-verification-audit.md`: le tabelle pre-fix e il verdetto F01/F02 descrivono correttamente il difetto storico, non lo stato post-correzione.
- `system-design-dossier.md`: le sezioni sulla pipeline area/codici e le limitazioni F01/F02 sono storiche; l'architettura generale resta valida.
- Qualunque PDF, screenshot, export o log prodotto prima di questa milestone e contenente superficie, categorie, prevalente, CO2 o valore economico è contaminato dalla pipeline precedente e non deve essere usato come reference answer.
- Non sono state trovate fixture o golden answer di test contenenti le vecchie baseline reali; la suite precedente non le verificava.

## Limiti residui di questa baseline

- La milestone non valida bibliograficamente i coefficienti CO2 né ne cambia valori o unità.
- L'area EPSG:32633 è coerente con il CRS nativo dei due dataset scientifici usati; una diversa convenzione geodetica richiederebbe una decisione metodologica esplicita.
- Piccole differenze sub-metro quadrato possono emergere da serializzazione GeoJSON e round-trip CRS; i test sintetici usano una tolleranza di `0,001 ha`, mentre GUI e conversational confrontati sullo stesso payload restano identici.

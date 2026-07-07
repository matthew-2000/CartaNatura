# Task sheet operatore — pilot ASITA 2026

Versione: `ASITA-2026-PILOT-v0.1`
Protocollo: [docs/asita-2026-pilot-protocol.md](asita-2026-pilot-protocol.md)
URL: `/progettoGIS/cartaNatura/?study=1`

## Setup sessione

Partecipante: `participant_###`
Ordine condizioni:

- partecipante dispari: `webgis` → `conversational`
- partecipante pari: `conversational` → `webgis`

Input standard:

- comuni: `Avellino` e `Benevento`
- scenario valore singolo: `social_cost`
- timeout T1-T5: 6 min
- timeout T6: 4 min

## Procedura per ogni condizione

1. Console operatore: scegliere `participantId`, `condition`, task T1.
2. Premere `Avvia`.
3. Premere `Inizia attività`.
4. Leggere solo consegna task.
5. Osservare senza guidare.
6. Premere `Completa`, `Errore` o `Non compresa`.
7. Passare al task successivo e premere `Inizia attività`.
8. A fine condizione: esportare JSON e JSONL.
9. Somministrare misure soggettive di condizione.
10. Premere `Reset` prima della condizione successiva.

## Regole rapide per condizione

### `webgis`

Partecipante deve completare con controlli grafici.

Consentito:

- pannello comuni/disegno;
- analisi UI;
- report;
- scenario prezzo UI;
- calcolo valore UI;
- export PDF;
- verifica mappa.

Non consentito:

- chat;
- voce;
- prompt suggeriti.

### `conversational`

Partecipante deve completare tramite chat/voce.

Consentito:

- chat;
- voce se configurata;
- mappa per verifica;
- report aperto dalla chat;
- export PDF dal pulsante visibile nel report.

Non consentito:

- selezione comuni da UI per completare;
- disegno area per completare;
- analisi UI;
- selezione/calcolo economico UI;
- storico come sorgente di completamento.

## Task

### T1 — Analisi comuni/area

ID log: `asita_t1_area_analysis`

Consegna WebGIS:
“Seleziona Avellino e Benevento e produci l’analisi dell’area.”

Consegna conversazionale:
“Chiedi al sistema di analizzare Avellino e Benevento.”

Successo osservabile:

- risultato visibile in mappa/report;
- `analysisId` presente.

Log da controllare:

- `task_started`;
- `analysis_completed` oppure `tool_completed`;
- `details.analysisId`;
- `task_completed`.

Fallimento:

- niente analisi entro timeout;
- comuni errati;
- uso canale non consentito per completare.

### T2 — Categorie forestali e CO2

ID log: `asita_t2_forest_co2`

Consegna WebGIS:
“Trova nel risultato le categorie forestali e la CO2 assorbita.”

Consegna conversazionale:
“Chiedi al sistema quali categorie forestali sono state trovate e quanta CO2 assorbono.”

Successo osservabile:

- partecipante indica categorie/assenza motivata;
- partecipante indica CO2 totale.

Log da controllare:

- `task_started`;
- `report_opened` o eventi chat/tool;
- `details.analysisId`;
- `task_completed`.

Fallimento:

- valori non collegabili ad analisi corrente;
- risposta chat non verificabile;
- timeout.

### T3 — Valore economico

ID log: `asita_t3_economic_value`

Consegna WebGIS:
“Calcola il valore economico usando lo scenario Costo sociale.”

Consegna conversazionale:
“Chiedi al sistema di calcolare il valore economico con lo scenario Costo sociale.”

Successo osservabile:

- risultato include CO2, scenario/prezzo, valore totale, area/analisi.

Log da controllare:

- `task_started`;
- `valuation_completed`;
- `details.analysisId`;
- `details.scenarioKey: social_cost`;
- `details.priceEurPerTon`;
- `details.totalCo2`;
- `details.totalValueEur`;
- `task_completed`.

Fallimento:

- scenario errato;
- valore inventato/non tracciato;
- nessun `analysisId`.

### T4 — Confronto scenari

ID log: `asita_t4_scenario_compare`

Consegna WebGIS:
“Confronta gli scenari economici disponibili per l’analisi corrente.”

Consegna conversazionale:
“Chiedi al sistema di confrontare tutti gli scenari economici disponibili.”

Successo osservabile:

- tutti gli scenari disponibili sono mostrati;
- prezzi e valori sono coerenti tra UI/chat.

Log da controllare:

- `task_started`;
- WebGIS: `interaction_completed` con `scenario_comparison_viewed` o `report_opened`;
- conversazionale: `chat_message`, `tool_started`, `tool_completed`, `chat_response`;
- `details.analysisId`;
- `task_completed`.

Fallimento:

- scenari mancanti;
- prezzi incoerenti;
- confronto fatto con controllo UI in condizione conversazionale.

### T5 — Report e PDF

ID log: `asita_t5_report_pdf`

Consegna WebGIS:
“Apri il report ed esporta il PDF.”

Consegna conversazionale:
“Chiedi al sistema di aprire il report, poi esporta il PDF dal comando visibile.”

Successo osservabile:

- report aperto;
- PDF generato.

Log da controllare:

- `task_started`;
- `report_opened`;
- `report_generated`;
- `details.reportFormat: pdf`;
- `details.analysisId`;
- `task_completed`.

Fallimento:

- report non aperto;
- PDF non generato;
- chat dichiara generazione PDF senza evento `report_generated`.

### T6 — Verifica mappa

ID log: `asita_t6_map_verify`

Consegna WebGIS:
“Verifica sulla mappa che il risultato corrisponda ai comuni analizzati.”

Consegna conversazionale:
“Usa la mappa per verificare il risultato ottenuto tramite chat, senza rifare l’analisi dai controlli grafici.”

Successo osservabile:

- partecipante localizza area/comuni;
- report/chat/mappa sono coerenti.

Log da controllare:

- `task_started`;
- `ui_action` di verifica mappa, `report_opened` o azione chat di focus/legenda;
- nessuna nuova analisi UI non dichiarata in conversazionale;
- `task_completed`.

Fallimento:

- area non localizzata;
- risultato mappa diverso da report/chat;
- uso controllo grafico bloccato per produrre nuovo risultato.

## Misure soggettive

Dopo ogni task, modulo esterno:

- difficoltà 1-7;
- fiducia nel risultato 1-7;
- chiarezza risultato 1-7;
- nota libera opzionale.

Dopo ogni condizione:

- SUS o UMUX-LITE;
- NASA-TLX short/raw;
- percezione di controllo;
- percezione di verificabilità;
- commento libero.

Dopo entrambe:

- preferenza complessiva;
- motivazione preferenza;
- problemi principali.

## Checklist post-condizione

- JSON esportato.
- JSONL esportato.
- 6 task presenti in `summary.tasks`.
- Ogni task ha `taskRunId` diverso.
- Ogni task ha status terminale.
- `condition` corretta.
- `analysisId` coerente nei task T1-T6.
- `protocolViolationCount` controllato.
- errori annotati.
- misure soggettive raccolte.

## Classificazione sessione

Valida:

- tutti i task tracciati e completati;
- nessuna contaminazione sostanziale;
- export e misure soggettive presenti.

Parzialmente valida:

- task fallito/interrotto ma log chiaro;
- violazione non usata per completare;
- misura soggettiva minore mancante.

Non valida:

- export mancante;
- condizione contaminata e non isolabile;
- completamento fuori log;
- aiuto sostanziale non documentato.

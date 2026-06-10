# Demo Readiness Fase 3

## Stato

- stato: completata
- data validazione: 2026-06-10
- verifica automatica: `python manage.py test cartaNatura`, `python manage.py check`, `node --check cartaNatura/static/js/app.js`
- verifica browser: Browser plugin desktop e mobile su `http://127.0.0.1:8000/progettoGIS/cartaNatura/`

## Deliverable

- `uiActions` con whitelist server/client
- handler frontend sicuri per azioni consentite
- test CRS dichiarato errato/in URN EPSG
- test selezione mista comuni + geometria disegnata
- test confronto dopo due analisi GIS
- riduzione payload modello: nessun `clipped` o `selectionPayload` nel tool output inviato al modello
- grounding vegetazionale alleggerito senza lista codici

## Azioni UI consentite

- `show_last_analysis`
- `open_report_panel`
- `show_legend`
- `focus_map_results`

Regola: qualunque azione fuori allowlist viene scartata dal backend e dal frontend.

## QA browser

Flusso testato:

```text
app load -> apri assistente -> invia "analizza Avellino" -> mappa aggiornata -> report aperto
```

Esito:

- pagina corretta: `Carta Natura`
- contenuto non vuoto
- nessun overlay errore
- console senza errori o warning rilevanti
- mappa aggiornata con risultati Avellino
- report aperto via `show_last_analysis`
- mobile sanity OK: titolo, mappa e pulsante assistente presenti

## Prossimo confine

Non aggiungere nuove capacita LLM prima di decidere scope fase 4.
Prossime direzioni possibili:

- pipeline e2e CI
- ottimizzazione asset statici/dataset
- deploy staging
- nuova azione UI solo con handler e test dedicati

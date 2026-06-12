# Hardening Fase 2

## Obiettivo

Portare l'assistente WebGIS da implementazione funzionante a feature stabilizzabile:

- validazione reale con OpenAI Responses API
- osservabilita minima su turni, provider, tool, latenza e token usage
- QA GIS su edge-case critici
- rifinitura azioni UI e messaggi errore

## Stato iniziale

Gia presenti:

- endpoint `/interact` e `/interact/stream`
- runtime OpenAI Responses API con tool use
- tool deterministici per analisi comuni, selezione corrente, confronto, ultima analisi, metodologia e reset
- analysis store e session store via sessione Django
- test automatici per runtime, orchestrator, tool e streaming SSE

## Stato avanzamento

- osservabilita minima: implementata in `cartaNatura/interaction/observability.py`
- validazione reale provider: eseguita localmente con `OPENAI_API_KEY` il 2026-06-10
- QA automatico: `python manage.py test cartaNatura` e `python manage.py check`
- sanity HTTP locale: home e `static/js/app.js` rispondono 200 su `127.0.0.1:8000`
- browser render sanity: screenshot headless Chrome prodotto su home locale
- fase 3 follow-up: whitelist `uiActions`, QA browser interattivo e payload/costi completati il 2026-06-10

## Checklist fase 2

1. Osservabilita runtime
   - log provider call con `response_id`, `previous_response_id`, durata e token usage
   - log tool call con nome tool, durata, esito e presenza analisi
   - log errori provider/tool senza esporre payload sensibili o GeoJSON completi

   Stato: completato per runtime assistente.

2. Validazione manuale reale
   - configurare `OPENAI_API_KEY`
   - avviare app locale
   - provare flussi v1: comuni, selezione corrente, explain, compare, ambiguity, reset
   - salvare anomalie riproducibili come test o issue tecniche

   Stato: validazione minima completata su home, reset, chiarimento ambiguo, analisi Avellino e SSE.

3. QA GIS edge-case
   - geometria vuota
   - geometria fuori Campania
   - comuni senza vegetazione supportata
   - payload CRS errato o incompleto
   - selezione mista comuni + disegno

   Stato: copertura automatica ampliata per payload vuoto, CRS dichiarato errato, CRS URN valido, area senza risultati natura e selezione mista comuni + disegno.

4. UX assistant
   - rendere visibili azioni UI validate
   - distinguere chiarimento, errore provider, errore GIS
   - migliorare quick actions in base al contesto corrente

   Stato: follow-up suggestions cliccabili, `uiActions` filtrate da whitelist server/client e azioni consentite eseguite dal frontend.

## Exit criteria fase 2

Fase 2 chiusa solo se:

- test automatici passano
- osservabilita minima e documentata e' presente
- flussi v1 sono stati provati con provider reale
- edge-case GIS principali sono coperti da test o da decisione documentata
- anomalie residue sono esplicite e non bloccano uso demo/staging

## Fase 3 completata

- whitelist server/client per `uiActions`
- azioni consentite: `show_last_analysis`, `open_report_panel`, `show_legend`, `focus_map_results`
- test confronto dopo due analisi reali con fixture GIS
- verifica che output tool verso modello non includa `clipped` o `selectionPayload`
- prompt modello alleggerito rimuovendo codici vegetazionali dal grounding
- QA Browser plugin desktop: app load, assistant interaction, mappa aggiornata, report aperto, zero console error/warn
- QA Browser plugin mobile: layout renderizzato, mappa e controlli principali presenti, zero console error/warn

## Residui non bloccanti

- aggiungere test browser automatizzato persistente in CI quando esiste pipeline e2e dedicata
- aggiungere whitelist piu ricca solo quando esistono nuove azioni UI con handler espliciti

# Architettura

## Scopo

`CartaNatura` è un sistema WebGIS per supportare analisi e valutazione economica del servizio ecosistemico di sequestro forestale della CO2. Il progetto è organizzato come applicazione unica, senza linee parallele o moduli storici: interfaccia mappa, conversazione, voce, report e logging sperimentale condividono gli stessi servizi analitici.

## Moduli

```text
Browser
  -> Leaflet map workspace
  -> conversational panel
  -> voice input
  -> report/PDF
  -> experimental event client

Django
  -> views.py
  -> domain/
  -> services/
  -> interaction/
  -> experiments/

Dataset locali
  -> shapeCN/CNPulita.shp
  -> static/data/*.geojson
```

## Separazione Responsabilità

### WebGIS e Mappa

- [static/js/modules/map-controller.js](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/static/js/modules/map-controller.js:1)
- selezione comuni
- disegno, modifica e rimozione geometrie
- rendering categorie forestali e comuni interessati
- verifica spaziale dei risultati

### Analisi Spaziale

- [services/payloads.py](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/services/payloads.py:1)
- [services/datasets.py](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/services/datasets.py:1)
- [services/gis_clip.py](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/services/gis_clip.py:1)
- validazione payload GeoJSON
- conversione CRS
- clip tra selezione e Carta della Natura
- comuni interessati

### CO2 Sequestrata

- [domain/vegetation.py](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/domain/vegetation.py:1)
- coefficienti per categoria forestale
- serializzazione categorie per frontend
- sintesi server/client coerente

### Valutazione Economica

- scenari prezzo configurati in [views.py](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/views.py:47)
- calcolo lato client: prezzo EUR/t moltiplicato per CO2 annua stimata
- evento sperimentale `valuation_completed`

### Interfaccia Conversazionale

- [interaction/models.py](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/interaction/models.py:1)
- [interaction/resolvers.py](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/interaction/resolvers.py:1)
- [interaction/orchestrator.py](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/interaction/orchestrator.py:1)
- [interaction/assistant_runtime.py](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/interaction/assistant_runtime.py:1)
- intenti di dominio
- fast path deterministici
- runtime LLM provider-neutral con tool use
- stato conversazionale in sessione Django

### Supporto Vocale

- `MediaRecorder` nel browser acquisisce un messaggio audio breve
- Django invia audio a OpenAI Audio Transcriptions
- il transcript torna al frontend e viene inviato allo stesso endpoint conversazionale
- channel `voice`, metadata `interactionMode=voice`
- log senza salvare transcript

### Report

- [static/js/modules/pdf-export.js](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/static/js/modules/pdf-export.js:1)
- report HTML nel pannello laterale
- PDF con mappa, CO2, superficie, categoria prevalente, scenario prezzo, valore stimato, comuni interessati
- evento `report_generated`

### Logging Sperimentale

- [experiments/logging.py](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/experiments/logging.py:1)
- log session-scoped
- export JSON
- niente testo libero utente, transcript, IP o identificativi personali

## Flusso WebGIS

```mermaid
flowchart TD
  A["Utente seleziona comuni o disegna area"] --> B["Frontend costruisce payload GeoJSON"]
  B --> C["POST /gis"]
  C --> D["parse_selection_payload"]
  D --> E["clip_selection"]
  E --> F["Sintesi categorie forestali e CO2"]
  F --> G["Mappa + report aggiornati"]
  G --> H["Scenario prezzo + PDF"]
```

## Flusso Conversazionale

```mermaid
flowchart TD
  A["Utente scrive o detta richiesta"] --> B["InteractionRequest"]
  B --> C["Intent resolver"]
  C --> D{"Serve LLM?"}
  D -->|no| E["Handler deterministico"]
  D -->|si| F["Provider LLM configurato + tool registry"]
  E --> G["Analisi GIS"]
  F --> G
  G --> H["Risposta testuale + uiHints"]
  H --> I["Mappa aggiornata e verificabile"]
```

## Regole

- Numeri GIS e CO2 arrivano solo da servizi deterministici.
- LLM interpreta richieste, guida workflow e sintetizza risultati tramite provider configurato (`openai` o `ollama`).
- Il provider selezionato, il modello e gli identificativi di turno sono isolati nel layer `interaction/llm.py` e nel runtime conversazionale; orchestratore, tool e servizi GIS non dipendono da OpenAI.
- Ogni risultato prodotto dalla conversazione deve restare verificabile su mappa.
- Le view Django restano sottili.
- I dataset locali sono caricati con caching.
- CRS critici:
  - comuni UI: `EPSG:32633`
  - disegni mappa: `EPSG:4326`
  - analisi finale: conversione coerente prima del clip

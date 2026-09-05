# Telemetria Raw

Carta Natura non gestisce partecipanti, task o sessioni di studio. L'operatore
gestisce il protocollo ASITA 2026 esternamente all'applicazione.

## Persistenza

Il log primario è un file JSONL append-only per sessione anonima:

```text
<DJANGO_DATA_DIR>/raw-events/session_<uuid>.jsonl
```

Ogni evento è serializzato in una singola scrittura protetta da lock di file e
`fsync`, così processi e thread concorrenti non sovrascrivono eventi. Non vengono
creati summary o metriche aggregate. L'analisi avviene offline sul JSONL.

Il solo endpoint di scrittura dal browser è:

- `POST /progettoGIS/cartaNatura/telemetry/events`

Accetta esclusivamente eventi client-side: `gui_action`,
`economic_evaluation`, `report_prepared`, `pdf_generated` ed `error`.
Rifiuta testo utente, transcript e risposta assistente: questi contenuti sono
autorevoli solo sul backend.

## Schema evento

Campi sempre presenti:

- `schemaVersion`: attualmente `1`;
- `eventId`: UUID univoco;
- `timestamp`: UTC ISO 8601;
- `anonymousSessionId`: UUID casuale conservato nella sessione Django;
- `interactionMode`: `gui`, `text` o `voice`;
- `eventType`.

Campi opzionali, solo quando pertinenti:

- `interactionId`, `operation`, `durationMs`, `analysisId`;
- `userText`, `transcript`, `assistantResponse`;
- `tool: {name, callId}`;
- `error: {type, message}`;
- `data`: argomenti/risultati essenziali, summary GIS, scenari e metadati tecnici allow-listed.

## Eventi

- `interaction_started`, `interaction_completed`, `interaction_failed`;
- `voice_transcribed`;
- `tool_started`, `tool_completed`, `tool_failed`, `tool_recovered`;
- `gui_action`;
- `analysis_completed`, `economic_evaluation`, `comparison_completed`;
- `report_prepared`, `pdf_generated`;
- `error`.

## Autorità e deduplicazione

- Backend: testo inviato, transcript vocale, risposta assistente, tool, risultati
  strutturati, errori backend e durata dell'interazione.
- Frontend: azioni GUI, calcolo economico eseguito nel browser, apertura report,
  PDF ed errori esclusivamente client-side.

Il transcript viene scritto al termine della trascrizione e riutilizza lo stesso
`interactionId` dell'eventuale richiesta vocale successiva. L'audio raw non viene
persistito. Il frontend non può inviare contenuti conversazionali al logger.

## Modalità operative

L'operatore imposta una modalità senza participant/task lifecycle:

- `?mode=gui-only` — disabilita e blocca gli endpoint conversazionali;
- `?mode=conversational-only` — disabilita e blocca l'avvio dell'analisi GUI;
- `?mode=full` — ripristina entrambe le interfacce.

La scelta viene conservata nella sessione Django e applicata sia nella UI sia
nelle view server per le operazioni principali.

## Dati legacy

Eventuali directory `var/study-logs/` create da versioni precedenti non vengono
migrate, lette o cancellate automaticamente. Non appartengono al nuovo schema e
devono essere archiviate come dati legacy separati.

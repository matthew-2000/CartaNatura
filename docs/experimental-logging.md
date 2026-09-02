# Logging Sperimentale

## Obiettivo

Il logging prepara il sistema per un confronto controlled within-subject tra interfaccia WebGIS tradizionale e interfaccia conversazionale testuale/vocale.

## Endpoint

- `GET /progettoGIS/cartaNatura/experiment/log`
- `POST /progettoGIS/cartaNatura/experiment/log`
- `DELETE /progettoGIS/cartaNatura/experiment/log`
- `GET /progettoGIS/cartaNatura/experiment/study/session`
- `GET /progettoGIS/cartaNatura/experiment/study/session?format=jsonl`
- `POST /progettoGIS/cartaNatura/experiment/study/session`
- `DELETE /progettoGIS/cartaNatura/experiment/study/session`

Il log operativo ordinario vive nella sessione Django e può essere esportato come JSON.
La modalità studio persistente usa file locali esclusi da git in `var/study-logs/`.

## Archivio Locale

La pagina `/progettoGIS/cartaNatura/study-admin/` elenca tutte le sessioni
persistenti, mostra riepiloghi ed eventi e permette di scaricare JSON/JSONL o
eliminare una sessione chiusa. Pagina, download ed eliminazione richiedono la
password condivisa configurata in `STUDY_ADMIN_PASSWORD`. Se la variabile non è
configurata, l'archivio resta chiuso. La password non viene salvata nella sessione:
la sessione conserva soltanto un token HMAC, che viene invalidato quando la
password cambia. Una sessione attiva nella sessione Django corrente deve essere
chiusa dalla console Studio prima di poterla eliminare.

## Attivazione Riservata

La console operatore viene generata solo aprendo l'app con:

```text
/progettoGIS/cartaNatura/?study=1
```

Senza `study=1` non vengono renderizzati controlli riservati. Se una sessione persistente è già attiva nella sessione Django, gli eventi ordinari continuano a essere salvati su file anche quando la UI riservata non è visibile.

`POST /experiment/study/session` crea la sessione persistente con `participantId`, `condition` (`webgis` o `conversational`) e `taskId`. Il partecipante deve essere identificato solo tramite codice anonimo, per esempio `participant_001`.

## Eventi

Eventi ammessi:

- `session_started`
- `task_started`
- `task_completed`
- `task_failed`
- `task_interrupted`
- `ui_action`
- `chat_message`
- `chat_response`
- `tool_started`
- `tool_completed`
- `tool_failed`
- `protocol_violation`
- `selection_changed`
- `analysis_started`
- `analysis_completed`
- `valuation_completed`
- `report_generated`
- `report_opened`
- `interaction_started`
- `interaction_completed`
- `voice_started`
- `voice_transcribed`
- `reset_completed`
- `error`
- `unknown_request`

## Metriche Derivate

`summary` nell'export include:

- `taskCompletionCount`
- `taskCompletionDurationMs`
- `interactionCount`
- `operationalStepCount`
- `errorCount`
- `unknownRequestCount`
- `textInteractionCount`
- `voiceInteractionCount`
- `completedOperations`
- `reportGeneratedCount`
- `uiActionCount`
- `chatMessageCount`
- `toolCallCount`
- `failedTaskCount`
- `interruptedTaskCount`
- `protocolViolationCount`
- `tasks`

## Minimizzazione Dati

Nel log ordinario non vengono salvati:

- testo libero richieste utente
- transcript voce
- IP
- user agent
- nomi personali
- identificativi account

In modalità studio persistente vengono salvati anche testo utente, transcript vocale e risposta assistente, perché parte dell'analisi sperimentale. Restano esclusi identificativi personali non necessari come nome, cognome, email, IP e user-agent.

## Persistenza Studio

Struttura file:

```text
var/study-logs/
  participant_001/
    session_20260613_101500_webgis/
      events.jsonl
      summary.json
```

Ogni evento persistente include contesto sessione (`participantId`, `studySessionId`, `condition`, `taskId`) più metadati operativi e, solo in modalità studio, campi conversazionali (`userText`, `userTranscript`, `assistantResponse`, `intent`).

Nel log ordinario sono ammessi solo metadati operativi: conteggi, durate, stato, canale, operazione, numero categorie, CO2 totale, scenario prezzo.

## Protocollo Pilot ASITA 2026

Il protocollo operativo versionato è in [asita-2026-pilot-protocol.md](asita-2026-pilot-protocol.md).
Il foglio operativo per l'operatore è in [asita-2026-task-sheet.md](asita-2026-task-sheet.md).

## Workflow Studio

Per ogni partecipante:

1. assegnare ordine condizioni dal protocollo
2. avviare sessione persistente in `?study=1`
3. avviare ogni task con `Inizia attività`
4. chiudere ogni task con `Completa`, `Errore` o `Non compresa`
5. esportare JSON e JSONL a fine condizione
6. fare reset prima della condizione successiva

Ordine delle condizioni da controbilanciare tra partecipanti.

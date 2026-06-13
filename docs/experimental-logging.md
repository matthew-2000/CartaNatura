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
- `selection_changed`
- `analysis_started`
- `analysis_completed`
- `valuation_completed`
- `report_generated`
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

## Workflow Studio

Per ogni partecipante:

1. svuotare log con `DELETE`
2. assegnare task sperimentale
3. far completare task in modalità WebGIS
4. esportare log JSON
5. svuotare log
6. far completare task equivalente in modalità conversazionale
7. esportare log JSON

Ordine delle condizioni da controbilanciare tra partecipanti.

# Logging Sperimentale

## Obiettivo

Il logging prepara il sistema per un confronto controlled within-subject tra interfaccia WebGIS tradizionale e interfaccia conversazionale testuale/vocale.

## Endpoint

- `GET /progettoGIS/cartaNatura/experiment/log`
- `POST /progettoGIS/cartaNatura/experiment/log`
- `DELETE /progettoGIS/cartaNatura/experiment/log`

Il log vive nella sessione Django e può essere esportato come JSON.

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

Non vengono salvati:

- testo libero richieste utente
- transcript voce
- IP
- user agent
- nomi personali
- identificativi account

Sono ammessi solo metadati operativi: conteggi, durate, stato, canale, operazione, numero categorie, CO2 totale, scenario prezzo.

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

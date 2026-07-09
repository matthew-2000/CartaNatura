# Protocollo pilot ASITA 2026

Versione: `ASITA-2026-PILOT-v0.1`
Data: 2026-07-07
Stato: protocollo operativo per pilot, non raccolta definitiva.
App: `/progettoGIS/cartaNatura/?study=1`

## 1. Scopo

Questo protocollo guida un pilot within-subject per confrontare:

- condizione `webgis`: interfaccia WebGIS tradizionale;
- condizione `conversational`: interfaccia conversazionale testuale o vocale, con mappa usata per verifica.

Il pilot verifica eseguibilità, logging, equivalenza minima dei task e chiarezza operativa. Non dichiara risultati sperimentali definitivi.

## 2. Regole generali

- Ogni partecipante usa codice anonimo stabile, formato consigliato `participant_001`.
- Ogni task deve essere avviato dalla console operatore con `Inizia attività`.
- Ogni task deve terminare con un solo evento terminale: `task_completed`, `task_failed` o `task_interrupted`.
- La durata valida è quella tra `task_started` e evento terminale dello stesso `taskRunId`.
- Il completamento del task richiede criterio osservabile più evento terminale. Una semplice visualizzazione non basta se manca prova applicativa o conferma operatore.
- Errori, timeout, aiuti non consentiti o uso di canali bloccati vanno registrati come `error`, `unknown_request`, `task_failed`, `task_interrupted` o `protocol_violation`.
- I risultati numerici non sono hard-coded nel protocollo: dipendono dal dataset locale. Per il pilot si controlla coerenza tra UI, chat, storico, report e log.

## 3. Input standard pilot

Input primario:

- comuni: `Avellino` e `Benevento`;
- scenario economico per valore singolo: `social_cost` (`Costo sociale: 138 EUR/t`);
- confronto scenari: tutti gli scenari disponibili dall'app;
- canale conversazionale: testo. Voce ammessa solo se ambiente audio/API configurato.

Input di riserva, se il dataset locale non restituisce categorie forestali supportate:

- comune: `Salerno`;
- annotare la sostituzione nel foglio operatore e nei log di sessione.

## 4. Condizioni sperimentali

### 4.1 Condizione WebGIS tradizionale

Consentito:

- selezione comuni da UI;
- disegno/uso area in mappa;
- pulsante analisi;
- apertura report;
- selezione scenario prezzo;
- calcolo valore economico da UI;
- esportazione PDF;
- zoom/pan/legenda/storico se utili alla verifica.

Non consentito:

- chat testuale;
- input vocale;
- comandi conversazionali per completare task.

Controllo implementato:

- durante task attivo `webgis`, pannello assistente e invio chat/voce sono disabilitati;
- endpoint chat/stream/voice rispondono con blocco di condizione;
- tentativi bloccati sono registrati come `protocol_violation`.

### 4.2 Condizione conversazionale

Consentito:

- messaggi chat;
- input vocale, se configurato;
- tool conversazionali deterministici;
- apertura report tramite azione chat;
- esportazione PDF dal comando visibile nel report, dopo risultato economico disponibile;
- zoom/pan/legenda e ispezione mappa per verifica.

Non consentito per completare task:

- selezione comuni da UI;
- disegno area;
- pulsante analisi;
- storico come sorgente di completamento;
- selezione scenario prezzo da UI;
- pulsante calcolo valore economico da UI.

Controllo implementato:

- durante task attivo `conversational`, controlli grafici di completamento sono disabilitati o bloccati;
- endpoint GIS risponde con blocco di condizione;
- tentativi bloccati sono registrati come `protocol_violation`;
- mappa resta disponibile per verifica.

Differenza dichiarata:

- nella condizione conversazionale la chat apre/attiva il report; il PDF viene esportato tramite pulsante visibile nel report. Il pulsante PDF è considerato export del risultato, non canale di calcolo GIS/economico.

## 5. Task sperimentali

Timeout default: 6 minuti per task. Timeout breve: 4 minuti per task di sola verifica o confronto. Timeout massimo sessione: 75 minuti, pause escluse.

Aiuti consentiti:

- ripetere consegna del task;
- indicare dove si trova la console operatore solo al facilitatore, non al partecipante;
- ricordare che in conversazionale può usare mappa per verifica;
- chiarire significato di "scenario economico" senza indicare sequenza di click o formulazione esatta del prompt.

Aiuti non consentiti:

- dire quale pulsante usare per completare il task;
- suggerire prompt esatto durante task, salvo fallimento tecnico documentato;
- completare azioni al posto del partecipante;
- sbloccare manualmente controlli non consentiti.

### T1 — Analisi di comuni/area

ID log: `asita_t1_area_analysis`

Obiettivo: produrre un'analisi GIS per uno o più comuni.

Input: `Avellino` e `Benevento`.

Risultato atteso: analisi completata con `analysisId`, comuni interessati e risultati visibili in mappa/report.

Successo:

- WebGIS: partecipante seleziona i comuni e avvia analisi da UI;
- conversazionale: partecipante chiede analisi dei comuni alla chat;
- log contiene `analysis_completed` o tool conversazionale equivalente, stesso `taskRunId`, con `details.analysisId`;
- operatore marca `task_completed`.

Fallimento:

- nessuna analisi entro timeout;
- area/comuni errati non corretti;
- completamento tramite canale non consentito;
- errore backend non risolto entro timeout.

Log attesi:

- `task_started`;
- WebGIS: `ui_action`, `analysis_completed`;
- conversazionale: `chat_message`, `tool_started`, `tool_completed`, `chat_response` o `interaction_completed`;
- `task_completed` oppure terminale negativo.

### T2 — Categorie forestali e CO2

ID log: `asita_t2_forest_co2`

Obiettivo: individuare categorie forestali e CO2 assorbita dall'analisi corrente.

Input: analisi prodotta in T1 nella stessa condizione.

Risultato atteso: partecipante identifica almeno categorie forestali presenti/assenza motivata e CO2 totale annua.

Successo:

- WebGIS: partecipante apre/ispeziona report o popup risultati e indica categoria/e e CO2;
- conversazionale: partecipante chiede categorie forestali e CO2 alla chat;
- log collega risultato allo stesso `analysisId` di T1 o a nuova analisi dichiarata;
- operatore marca `task_completed`.

Fallimento:

- partecipante non trova CO2/categorie entro timeout;
- valori riferiti ad analisi diversa non dichiarata;
- chat produce risposta senza tool/stato applicativo verificabile;
- protocol violation usata per completare.

Log attesi:

- `task_started`;
- `report_opened` oppure eventi chat/tool con intento `extract_forest_information` o `estimate_co2_sequestration`;
- `details.analysisId`;
- `task_completed`.

### T3 — Valore economico con scenario specifico

ID log: `asita_t3_economic_value`

Obiettivo: calcolare valore economico usando scenario `social_cost`.

Input: analisi corrente; scenario `social_cost`.

Risultato atteso: valore totale in EUR, CO2 usata, prezzo/scenario usato, `analysisId`.

Successo:

- WebGIS: partecipante seleziona scenario e calcola da UI;
- conversazionale: partecipante chiede alla chat di calcolare valore con `social_cost`;
- log contiene `valuation_completed` con `details.analysisId`, `details.scenarioKey`, `details.priceEurPerTon`, `details.totalCo2`, `details.totalValueEur`;
- scenario e arrotondamenti sono coerenti con report/UI.

Fallimento:

- scenario diverso non corretto;
- valore non collegabile ad analisi;
- prezzo inventato o non presente negli scenari app;
- timeout.

Log attesi:

- `task_started`;
- WebGIS: `valuation_completed` con `interactionMode: map`;
- conversazionale: `chat_message`, tool economico, `valuation_completed` con `interactionMode: text` o `voice`;
- `task_completed`.

### T4 — Confronto scenari economici

ID log: `asita_t4_scenario_compare`

Obiettivo: confrontare tutti gli scenari economici disponibili.

Input: analisi corrente.

Risultato atteso: elenco scenari con prezzo e valore totale, ordinamento o differenze comprensibili.

Successo:

- WebGIS: partecipante visualizza tabella/confronto scenari nel report;
- conversazionale: partecipante chiede confronto scenari alla chat;
- valori derivano dagli stessi scenari definiti in `cartaNatura/domain/economics.py`;
- operatore verifica che tutti gli scenari disponibili siano rappresentati.

Fallimento:

- scenari mancanti;
- prezzi incoerenti tra UI e chat;
- confronto basato su valori inventati;
- task completato tramite selettore prezzo UI in condizione conversazionale.

Log attesi:

- `task_started`;
- WebGIS: `interaction_completed` con `operation: scenario_comparison_viewed` o `report_opened`;
- conversazionale: `chat_message`, tool economico/confronto, `chat_response`;
- `details.analysisId`;
- `task_completed`.

### T5 — Report e PDF

ID log: `asita_t5_report_pdf`

Obiettivo: aprire report e produrre export PDF del risultato.

Input: analisi corrente; se valore economico non già disponibile, usare scenario `social_cost` prima dell'export.

Risultato atteso: report aperto, PDF generato, log con `analysisId` e scenario/prezzo se presenti.

Successo:

- WebGIS: partecipante apre report e usa `Esporta PDF`;
- conversazionale: partecipante chiede alla chat di aprire/generare report; poi usa comando visibile `Esporta PDF` nel report;
- log contiene `report_opened` e `report_generated` con `details.reportFormat: pdf`;
- PDF include mappa, sintesi CO2 e valore economico se calcolato.

Fallimento:

- report non aperto;
- PDF non generato entro timeout;
- chat afferma di aver generato PDF senza `report_generated`;
- export riferito ad analisi diversa.

Log attesi:

- `task_started`;
- `report_opened`;
- `report_generated`;
- `details.analysisId`;
- `details.scenarioKey`, `details.priceEurPerTon`, `details.totalValueEur` se valore disponibile;
- `task_completed`.

### T6 — Verifica risultati in mappa

ID log: `asita_t6_map_verify`

Obiettivo: verificare spazialmente sulla mappa i risultati prodotti.

Input: analisi corrente.

Risultato atteso: partecipante mostra area/comuni analizzati e controlla coerenza visiva con report/chat.

Successo:

- WebGIS: partecipante usa mappa, layer/zoom/pan/risultati per confermare area;
- conversazionale: partecipante usa mappa solo per verifica, non per completare analisi o calcolo;
- se serve, chat può usare azioni `focus_map_results`/`show_legend`;
- operatore osserva corrispondenza tra area in mappa e `analysisId` usato.

Fallimento:

- impossibile localizzare area;
- mappa mostra risultato diverso dall'analisi/report;
- in conversazionale partecipante usa controllo grafico bloccato/non consentito per produrre nuovo risultato;
- timeout.

Log attesi:

- `task_started`;
- `ui_action` di verifica mappa, `report_opened` o azione chat di focus/legenda;
- nessun nuovo `analysis_completed` non dichiarato, salvo reset/nuova analisi registrata;
- `task_completed`.

## 6. Reset

### 6.1 Reset tra task

Procedura:

1. esportare log parziale se richiesto dal pilot;
2. premere `Completa` o `Errore` prima di cambiare task;
3. selezionare task successivo nella console;
4. premere `Inizia attività`;
5. verificare stato console `In corso: <taskId> / <condition>`;
6. non cancellare risultati se task successivo dipende dall'analisi corrente.

Effetto atteso:

- nuovo `taskRunId`;
- stato operativo incoerente pulito dove previsto dall'app;
- eventi successivi associati al task nuovo.

### 6.2 Reset tra condizioni

Procedura:

1. terminare task attivo;
2. esportare JSON e JSONL della condizione;
3. premere `Reset`;
4. ricaricare pagina se operatore osserva stato UI ambiguo;
5. selezionare nuova condizione;
6. avviare nuova sessione con stesso `participantId` e condizione diversa;
7. iniziare T1 della nuova condizione.

Effetto atteso:

- nuovo `studySessionId`;
- log precedente conservato su export/file persistente;
- assistant, selezioni, risultati e storico operativo non contaminano condizione successiva.

## 7. Controbilanciamento pilot

Assegnazione minima:

- partecipanti dispari: `webgis` → `conversational`;
- partecipanti pari: `conversational` → `webgis`.

Task order nel pilot:

1. T1;
2. T2;
3. T3;
4. T4;
5. T5;
6. T6.

Nota metodologica: ordine fisso semplifica pilot e debug. Per raccolta definitiva si può controbilanciare anche ordine task, ma non in questa milestone.

## 8. Dati oggettivi da esportare

Per ogni condizione esportare JSON e JSONL.

Campi/eventi minimi:

- `participantId`;
- `studySessionId`;
- `condition`;
- `taskId`;
- `taskRunId`;
- `eventType`;
- `timestamp`;
- `durationMs`;
- `channel`;
- `interactionMode`;
- `operation`;
- `status`;
- `error`;
- `details.analysisId`;
- `details.scenarioKey`;
- `details.priceEurPerTon`;
- `details.totalCo2`;
- `details.totalValueEur`;
- `details.reportFormat`;
- `details.toolName`;
- `summary.taskCompletionDurationMs`;
- `summary.uiActionCount`;
- `summary.chatMessageCount`;
- `summary.toolCallCount`;
- `summary.errorCount`;
- `summary.unknownRequestCount`;
- `summary.protocolViolationCount`;
- `summary.tasks`.

Metriche derivate:

- durata end-to-end per task;
- numero azioni UI;
- numero messaggi chat;
- numero tool call;
- errori/fallimenti/timeout;
- violazioni protocollo;
- report aperti/generati;
- coerenza `analysisId` tra analisi, valutazione, report e task.

## 9. Misure soggettive

Raccolta esterna, non dentro l'app.

Dopo ogni task:

- difficoltà percepita: scala 1-7;
- fiducia nel risultato: scala 1-7;
- chiarezza del risultato: scala 1-7;
- nota libera breve opzionale.

Dopo ogni condizione:

- SUS o UMUX-LITE;
- NASA-TLX short/raw;
- preferenza parziale: cosa ha aiutato/ostacolato;
- percezione di controllo e verificabilità del risultato.

Dopo entrambe le condizioni:

- preferenza complessiva;
- confronto qualitativo tra WebGIS e conversazionale;
- eventuali strategie usate.

## 10. Validità sessione

Sessione valida:

- tutti i task hanno un solo start e un solo terminale;
- condizione corretta per tutti gli eventi principali;
- nessuna violazione protocollo che completa un task;
- export JSON/JSONL disponibile;
- `analysisId` coerente nei task dipendenti;
- misure soggettive raccolte.

Sessione parzialmente valida:

- uno o più task falliti o interrotti, ma log ricostruibile;
- una misura soggettiva mancante non critica;
- violazione protocollo non usata per completare;
- errore tecnico documentato con retry controllato.

Sessione non valida:

- contaminazione tra condizioni non ricostruibile;
- task completati fuori console/log;
- export mancante;
- partecipante usa condizione sbagliata per completare task e violazione non è isolabile;
- operatore fornisce aiuto sostanziale non documentato.

## 11. Checklist pilot

Pre-pilot:

- app avviata con `?study=1`;
- provider conversazionale configurato (`LLM_PROVIDER=openai` con `OPENAI_API_KEY`, oppure `LLM_PROVIDER=ollama` con `OLLAMA_BASE_URL` e modello); `OPENAI_API_KEY` resta necessaria se si testa la voce;
- console operatore visibile;
- lista task ASITA T1-T6 visibile;
- export JSON/JSONL provato;
- PDF provato con almeno un'analisi;
- foglio soggettivo esterno pronto;
- ID partecipante assegnato;
- ordine condizioni assegnato.

Durante sessione:

- avviare sessione;
- avviare task;
- leggere consegna task;
- non aiutare oltre regole;
- terminare task con esito corretto;
- annotare errori/aiuti;
- esportare a fine condizione.

Post-sessione:

- controllare `summary.tasks`;
- controllare `protocolViolationCount`;
- verificare presenza misure soggettive;
- classificare sessione valida/parziale/non valida;
- salvare export con nome `participant_condition_timestamp`.

# Interfaccia Conversazionale

## Obiettivo

L'assistente permette richieste in linguaggio naturale orientate allo studio, senza obbligare l'utente a conoscere comandi tecnici. La conversazione non sostituisce la mappa: ogni analisi deve produrre risultati verificabili nello spazio.

## Canali

- testo: pannello assistente via OpenAI Responses API
- voce: registrazione audio browser, trascrizione OpenAI, transcript inviato come richiesta conversazionale
- mappa: contesto corrente usato per analizzare selezioni esistenti

## Intenti Di Dominio

Gli intenti applicativi sono definiti in [interaction/models.py](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/interaction/models.py:14):

- `analyze_selection`: analisi della selezione corrente
- `analyze_municipalities`: analisi di comuni nominati
- `extract_forest_information`: estrazione e spiegazione categorie forestali
- `estimate_co2_sequestration`: stima CO2 sequestrata annualmente
- `compare_economic_scenarios`: confronto scenari prezzo
- `compare_analyses`: confronto tra analisi recenti
- `explain_last_analysis`: spiegazione risultati
- `generate_report`: guida o apertura del report
- `guide_workflow`: guida nei passaggi necessari
- `reset_session`: azzeramento contesto
- `unknown`: richiesta non compresa

## Tool Deterministici

Il runtime LLM usa un contratto provider-neutral e può usare solo tool registrati:

- `search_municipalities`
- `analyze_municipalities`
- `analyze_current_selection`
- `get_last_analysis`
- `compare_recent_analyses`
- `get_methodology`
- `reset_analysis_context`

Regola: il modello non calcola direttamente superfici, CO2 o valori GIS. Deve chiamare tool o chiedere chiarimento.

## Interpretazione e richieste composte

Ogni richiesta testuale o vocale passa dall'LLM, inclusi analisi semplici, confronti e reset. Non ci sono scorciatoie basate su parole chiave, esecuzioni di ripiego scelte dal codice o risposte di dominio composte da template. La selezione strutturata inviata dai controlli WebGIS resta un'operazione grafica diretta.

Il modello sceglie i tool e riceve ogni risultato o errore prima di decidere il passo successivo. Il ciclo prosegue finché restituisce la risposta finale, entro il limite operativo di sei round di tool. Il testo finale e i suggerimenti provengono dall'LLM; le azioni UI sono limitate al contratto applicativo. Errori tecnici di input o del provider restano segnalazioni applicative.

Le mutazioni conversazionali dello storico sono transazionali: analisi, valutazioni e reset sono visibili ai tool successivi dello stesso turno, ma vengono applicati alla sessione soltanto dopo una risposta finale strutturata e validata. Un errore OpenAI, una risposta vuota o malformata e una violazione di grounding scartano l'intero staging. Durante lo streaming vengono pubblicati avanzamento e lifecycle dei tool; risultati GIS e testo finale diventano applicabili dalla UI solo dopo la validazione conclusiva.

Se il modello ha concluso le operazioni ma risponde fuori dal formato JSON previsto, gli viene richiesta una sola riformattazione finale, senza tool. Il codice non sostituisce il testo con una risposta precompilata e non deduce automaticamente che serva un chiarimento.

Per esempio, «Analizza separatamente Avellino e Benevento e confrontali» richiede due chiamate di analisi con un comune ciascuna, seguite dal confronto. Una singola chiamata con entrambi i comuni produce invece un'analisi congiunta. Il modello può concatenare anche analisi, valutazione e apertura report; il PDF viene generato dal pulsante del report.

Se il provider non è disponibile o restituisce una risposta vuota, il sistema segnala l'errore senza sostituire il modello con regole locali. Il reset viene eseguito soltanto dal relativo tool, non perché il testo o l'intento finale contengono la parola «reset».

## Provider LLM

Il percorso ASITA 2026 è congelato su questa configurazione:

- provider: `LLM_PROVIDER=openai` (obbligatorio per gli endpoint conversazionali Web)
- modello: `OPENAI_MODEL=gpt-5-mini`
- base URL: `OPENAI_BASE_URL=https://api.openai.com/v1`
- timeout: `LLM_TIMEOUT_SECONDS=60`, passato realmente ai client Responses e STT
- retry SDK: `0`, per non superare implicitamente il budget temporale con retry automatici
- Responses API: tool schema strict, `parallel_tool_calls=false`, tool chaining sequenziale, output finale JSON Schema strict, verbosity `low`; temperature e seed non vengono impostati
- STT: `OPENAI_TRANSCRIPTION_MODEL=gpt-4o-transcribe`, lingua italiana

`LLM_MODEL` e `LLM_BASE_URL` non sovrascrivono modello e base URL OpenAI. Restano compatibilità del provider Ollama fuori dallo studio. `AI_LLM_PROVIDER` non è più una seconda fonte di configurazione.

Il supporto Ollama può essere usato fuori dal percorso sperimentale tramite il layer provider-neutral. Richiede `LLM_PROVIDER=ollama`, `LLM_MODEL` o `OLLAMA_MODEL` e `LLM_BASE_URL` o `OLLAMA_BASE_URL`; `OLLAMA_THINK=false` disattiva il reasoning. Gli endpoint conversazionali ASITA rifiutano questa configurazione con errore esplicito.
- `OLLAMA_NUM_CTX`: numero di token del contesto locale, default `16384`. Le richieste composte includono tutti gli scambi con i tool; un contesto troppo piccolo può troncare la richiesta originale o le istruzioni. Il valore è configurabile in funzione della memoria disponibile.

Non esiste fallback automatico: errori di configurazione, timeout, indisponibilità e risposte vuote o malformate producono errori espliciti e nessuna operazione conversazionale viene committata.

## Confine di fiducia quantitativo

Il backend calcola e restituisce geometrie, superfici, CO2, rapporti, differenze, ranking, scenari e valori economici. Il modello interpreta, orchestra e formula la risposta. Prima di consegnare il testo, il runtime estrae ogni numero scritto in cifre e verifica che coincida con un valore autorevole (o con il suo arrotondamento a 0, 1 o 2 decimali) presente nei risultati dei tool dello stesso turno. Un numero non verificabile fa fallire il turno e annulla le mutazioni staged.

La garanzia è deliberatamente precisa ma non assoluta sul linguaggio naturale: impedisce che vengano consegnati valori numerici letterali divergenti o inventati; non dimostra formalmente la correttezza di parafrasi qualitative, confronti espressi senza cifre o numeri scritti interamente in lettere. I risultati strutturati restano sempre la fonte autorevole per la UI.

## Output

Ogni risposta strutturata include:

- intento risolto
- testo assistente
- eventuale richiesta di chiarimento
- azioni UI consentite
- suggerimenti successivi

Azioni UI ammesse:

- `show_last_analysis`
- `open_report_panel`
- `show_legend`
- `focus_map_results`

## Voce

Il supporto vocale usa `MediaRecorder` nel browser e un endpoint Django dedicato:

1. il browser registra audio dopo click su `Voce`
2. invia il file a `/progettoGIS/cartaNatura/voice/transcribe`
3. Django trascrive con `OPENAI_TRANSCRIPTION_MODEL`, default `gpt-4o-transcribe`
4. il transcript viene inviato allo stesso orchestratore della chat con `interactionMode=voice`

Il transcript viene registrato una sola volta dal backend con lo stesso `interactionId` riutilizzato dal successivo turno LLM. Un transcript vuoto non viene inviato. Errori STT (`operation=voice_transcription`) ed errori LLM (`operation=conversational_request`) restano distinti; l'audio raw vive soltanto nella richiesta e non viene scritto nella telemetria o nello storico.

## Report e PDF

`prepare_report` restituisce esclusivamente `action=open_existing_report` e autorizza l'azione UI `open_report_panel`. Non genera file. Il PDF nasce soltanto dopo il click client su “Genera PDF”; il download richiede poi il click separato sul link `download`. Il runtime rifiuta una risposta LLM che dichiari un PDF generato, creato, salvato o scaricato: nessuna di queste transizioni può essere prodotta dai tool conversazionali.

## Esempi Richieste

- "Analizza Avellino e Benevento"
- "Analizza la selezione corrente"
- "Quali categorie forestali hai trovato?"
- "Quanta CO2 viene sequestrata ogni anno?"
- "Confronta gli scenari economici"
- "Genera il report"
- "Spiegami il risultato"
- "Guidami nei passaggi"

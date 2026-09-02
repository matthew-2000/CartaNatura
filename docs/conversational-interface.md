# Interfaccia Conversazionale

## Obiettivo

L'assistente permette richieste in linguaggio naturale orientate allo studio, senza obbligare l'utente a conoscere comandi tecnici. La conversazione non sostituisce la mappa: ogni analisi deve produrre risultati verificabili nello spazio.

## Canali

- testo: pannello assistente via provider LLM configurato (`openai` o `ollama`)
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

Se il modello ha concluso le operazioni ma risponde fuori dal formato JSON previsto, gli viene richiesta una sola riformattazione finale, senza tool. Il codice non sostituisce il testo con una risposta precompilata e non deduce automaticamente che serva un chiarimento.

Per esempio, «Analizza separatamente Avellino e Benevento e confrontali» richiede due chiamate di analisi con un comune ciascuna, seguite dal confronto. Una singola chiamata con entrambi i comuni produce invece un'analisi congiunta. Il modello può concatenare anche analisi, valutazione e apertura report; il PDF viene generato dal pulsante del report.

Se il provider non è disponibile o restituisce una risposta vuota, il sistema segnala l'errore senza sostituire il modello con regole locali. Il reset viene eseguito soltanto dal relativo tool, non perché il testo o l'intento finale contengono la parola «reset».

## Provider LLM

Il provider conversazionale si seleziona da variabili d'ambiente:

- `LLM_PROVIDER=openai`: usa OpenAI remoto. Richiede `OPENAI_API_KEY`; usa `LLM_MODEL` o `OPENAI_MODEL` e `LLM_BASE_URL` o `OPENAI_BASE_URL`.
- `LLM_PROVIDER=ollama`: usa un modello locale esposto da Ollama. Richiede `LLM_MODEL` o `OLLAMA_MODEL` e `LLM_BASE_URL` o `OLLAMA_BASE_URL`. `OLLAMA_THINK=false` disattiva il reasoning per i modelli che supportano il flag `think`.
- `OLLAMA_NUM_CTX`: numero di token del contesto locale, default `16384`. Le richieste composte includono tutti gli scambi con i tool; un contesto troppo piccolo può troncare la richiesta originale o le istruzioni. Il valore è configurabile in funzione della memoria disponibile.

OpenAI e Ollama sono normalizzati nello stesso contratto runtime: testo, tool calling, output JSON strutturato, streaming e cronologia. Non esiste fallback automatico tra provider: errori di configurazione, indisponibilità o modelli non compatibili producono errori espliciti.

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

Il log sperimentale registra uso voce, durata e lunghezza transcript, non il transcript.

## Esempi Richieste

- "Analizza Avellino e Benevento"
- "Analizza la selezione corrente"
- "Quali categorie forestali hai trovato?"
- "Quanta CO2 viene sequestrata ogni anno?"
- "Confronta gli scenari economici"
- "Genera il report"
- "Spiegami il risultato"
- "Guidami nei passaggi"

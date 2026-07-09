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

## Provider LLM

Il provider conversazionale si seleziona da variabili d'ambiente:

- `LLM_PROVIDER=openai`: usa OpenAI remoto. Richiede `OPENAI_API_KEY`; usa `LLM_MODEL` o `OPENAI_MODEL` e `LLM_BASE_URL` o `OPENAI_BASE_URL`.
- `LLM_PROVIDER=ollama`: usa un modello locale esposto da Ollama. Richiede `LLM_MODEL` o `OLLAMA_MODEL` e `LLM_BASE_URL` o `OLLAMA_BASE_URL`. `OLLAMA_THINK=false` disattiva il reasoning per i modelli che supportano il flag `think`.

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

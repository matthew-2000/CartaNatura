# Contratto Prodotto Assistente LLM

## Stato documento

- stato: storico, implementato fino a fase 3 demo readiness
- ambito originale: fase 0 del programma assistente LLM
- target: assistente WebGIS reale, non rule-based, non mockato

Nota 2026-06-10: i limiti descritti nella sezione "Problema da risolvere" sono il punto di partenza storico. Il codice attuale include Responses API, tool use, stato server-side, SSE streaming, osservabilita minima e `uiActions` validate.

## Obiettivo

Portare `CartaNatura` da chat LLM accessoria a assistente WebGIS completo, capace di:

- capire richieste in linguaggio naturale
- interrogare servizi GIS deterministici
- mantenere contesto multi-turn
- aggiornare mappa e pannelli UI
- spiegare risultati senza inventare dati

Principio base:

- LLM interpreta, pianifica, chiarisce, sintetizza
- backend GIS calcola
- frontend rende stato e risultati

## Problema da risolvere

Versione attuale ha limiti strutturali:

- routing intenti basato su keyword e matching comuni
- prompt one-shot con singolo `Summary JSON`
- memoria conversazionale minima
- nessun function calling / tool use vero
- nessun contratto strutturato tra LLM, GIS e UI

Questo non basta per assistente production-grade.

## Obiettivi v1

V1 deve supportare end-to-end:

1. analisi di uno o più comuni nominati nel messaggio
2. analisi di selezione corrente in mappa
3. spiegazione del risultato appena prodotto
4. confronto tra due analisi recenti
5. chiarimento di richieste ambigue o incomplete
6. reset esplicito di contesto conversazionale e analitico
7. suggerimento di prossime azioni utili in UI

## Non obiettivi v1

Fuori scope prima release:

- RAG documentale generico
- query libere su fonti esterne web
- voice input/output
- editing geometrie tramite linguaggio naturale
- collaborazione multiutente in stessa sessione
- training/fine-tuning custom

## Requisiti di prodotto

### Requisiti funzionali

- assistente deve rispondere in italiano
- assistente deve poter chiedere chiarimenti prima di lanciare analisi
- ogni risposta numerica deve derivare da tool GIS backend
- assistente deve poter usare stato mappa corrente
- assistente deve poter richiamare ultima analisi senza ricalcolo inutile
- assistente deve restituire risposta testuale + metadati UI strutturati

### Requisiti non funzionali

- latenza target:
  - chiarimento senza tool: p95 < 4s
  - analisi con tool GIS: p95 < 12s
- nessun dato inventato
- tool output validato con schema
- osservabilità completa di turni, tool call, errori, costi
- fallback chiaro in caso di errore provider o GIS

## Esperienze utente chiave

### Flusso A: analisi comuni nominati

Utente:

`Analizza Avellino e Benevento`

Sistema:

- interpreta richiesta
- invoca tool GIS su comuni canonici
- riceve summary strutturato
- risponde con sintesi grounded
- aggiorna mappa, stato, pannelli

### Flusso B: follow-up

Utente:

`Quale comune pesa di piu?`

Sistema:

- usa contesto ultima analisi
- se dati insufficienti, invoca tool confronto o dettaglio
- risponde senza far ripetere utente

### Flusso C: richiesta ambigua

Utente:

`Analizza san`

Sistema:

- non inventa target
- propone opzioni compatibili
- attende disambiguazione

### Flusso D: explainability

Utente:

`Spiegami perche castagneti dominano`

Sistema:

- usa risultato tool recente
- spiega con linguaggio naturale
- non ricalcola se non serve

## Guardrail di dominio

- LLM non produce mai valori GIS originari senza tool
- LLM non interpreta GeoJSON grezzo se backend puo riassumere
- LLM non modifica stato mappa senza `ui_actions` esplicite e validate
- richieste ambigue devono fermarsi a chiarimento
- richieste fuori scope devono dirlo chiaramente

## Contratto logico target

### Input turno

Ogni turno assistente deve ricevere:

- `user_message`
- `ui_context`
- `analysis_context`
- `conversation_context`
- elenco tool disponibili

### Output turno

Ogni turno assistente deve restituire oggetto strutturato con:

- `assistant_text`
- `tool_calls`
- `ui_actions`
- `needs_clarification`
- `clarification_question`
- `citations_internal`
- `conversation_patch`

### Stato

Separare tre stati:

1. `UIContext`
   - comuni selezionati
   - extent mappa
   - layer attivi
   - selection source
2. `AnalysisContext`
   - analisi salvate
   - summary
   - result ids
   - confronti
3. `ConversationContext`
   - turno corrente
   - task aperto
   - chiarimenti pendenti
   - riferimenti a tool output

## Architettura target minima

```text
Browser UI
  -> chat panel + map state + SSE stream
  -> POST /interactions

Django interaction layer
  -> request validation
  -> conversation state load/save
  -> OpenAI Responses runtime
  -> tool execution loop
  -> UI action serializer

GIS tools
  -> analyze_municipalities
  -> analyze_selection
  -> compare_analyses
  -> get_last_analysis
  -> export_report

Datasets locali
  -> shapeCN/*
  -> static/data/*
```

## Decisioni tecniche vincolanti

- API LLM primaria: Responses API
- integrazione: tool use / function calling
- output macchina: Structured Outputs con schema
- prompt: gestiti in codice, versionati, testati
- conversation state: server-side
- streaming: SSE HTTP lato web

Motivo:

- OpenAI raccomanda `Responses API` per nuove integrazioni agentiche con tool, stato e output strutturato.
- Structured Outputs riduce errori di formato.
- prompt trattati come codice evitano drift e regressioni.

Riferimenti ufficiali:

- [Responses API](https://developers.openai.com/api/docs/guides/migrate-to-responses)
- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Conversation state](https://developers.openai.com/api/docs/guides/conversation-state)
- [Prompting](https://developers.openai.com/api/docs/guides/prompting)
- [Streaming responses](https://developers.openai.com/api/docs/guides/streaming-responses)

## Criteri di accettazione fase 0

Fase 0 chiusa solo se esistono:

1. capability list v1 approvata
2. non-goals chiari
3. guardrail di dominio chiari
4. architettura target minima approvata
5. lista tool backend necessari
6. backlog implementativo fase successiva mappato al repo

## Deliverable fase 0

- questo documento
- backlog tecnico fase 1 in documento separato

## Exit criteria

Fase 0 finisce quando team puo iniziare implementazione senza altre scelte architetturali bloccanti.

Stato implementazione:

- fase 1 completata nel codice: tool layer GIS, contratti strutturati, analysis store, orchestrator e runtime Responses API
- fase 2 completata: osservabilita minima, validazione reale, QA GIS edge-case e documentazione
- fase 3 completata: demo readiness, `uiActions` allowlist, payload/costi alleggeriti e QA browser desktop/mobile

Step successivo:

- aprire PR/merge verso branch principale oppure procedere a staging/deploy

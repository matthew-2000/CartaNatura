# Backlog Fase 1

## Obiettivo

Costruire tool layer GIS serio per assistente LLM.

Esito atteso:

- niente keyword routing come cuore sistema
- niente prompt che simulano logica applicativa
- tool backend deterministici, tipizzati, testati

## Confine fase 1

Dentro fase 1:

- contratti input/output tool
- servizi GIS callable da agent runtime
- persistenza minima stato analitico
- test unit e integration per tool

Fuori fase 1:

- streaming UI
- runtime completo Responses API
- memoria conversazionale estesa
- redesign completo pannello chat

## Deliverable tecnici

### 1. Tool contracts

Creare package nuovo:

```text
cartaNatura/interaction/tools/
  __init__.py
  contracts.py
  registry.py
  execution.py
```

Contenuto minimo:

- schema richieste tool
- schema risposte tool
- enum tool names
- validazione centralizzata

### 2. Tool GIS v1

Creare moduli:

```text
cartaNatura/interaction/tools/gis_analysis.py
cartaNatura/interaction/tools/analysis_history.py
cartaNatura/interaction/tools/methodology.py
```

Tool minimi:

- `analyze_municipalities`
- `analyze_current_selection`
- `compare_analyses`
- `get_last_analysis`
- `reset_analysis_context`
- `get_methodology`

### 3. Analysis store

Creare supporto stato analitico server-side:

- tenere storico analisi recente in sessione Django per v1
- assegnare `analysis_id`
- salvare:
  - input normalizzato
  - summary
  - comuni coinvolti
  - timestamp

Possibile file:

```text
cartaNatura/interaction/analysis_store.py
```

### 4. UI context serializer

Normalizzare contesto frontend ricevuto da browser.

Possibile file:

```text
cartaNatura/interaction/ui_context.py
```

Responsabilita:

- validare `selectedMunicipalities`
- validare `mapExtent`
- serializzare `selectionSource`
- preparare payload tool-safe

### 5. Refactor orchestrator

Preparare orchestrator a runtime agentico.

In questa fase non serve ancora chiamare OpenAI in loop tool-based, ma serve:

- separare `intent resolution` da `tool execution`
- introdurre registry tool
- smettere di accoppiare handler a prompt builder

File da toccare:

- `cartaNatura/interaction/orchestrator.py`
- `cartaNatura/interaction/handlers.py`
- `cartaNatura/interaction/models.py`

### 6. Test

Ampliare test:

- tool contract validation
- canonicalizzazione comuni
- history compare
- retrieval ultima analisi
- reset contesto analitico
- errori input invalidi

File da ampliare:

- `cartaNatura/tests.py`

## Contratti minimi richiesti

### Tool input: analyze municipalities

```json
{
  "municipality_names": ["Avellino", "Benevento"]
}
```

### Tool output: analyze municipalities

```json
{
  "analysis_id": "analysis_...",
  "requested_municipalities": ["Avellino", "Benevento"],
  "intersected_municipalities": ["Avellino", "Benevento"],
  "summary": {
    "items": [],
    "totalCo2": 0,
    "totalHectares": 0,
    "hasSupportedVegetation": false,
    "topCategory": null
  }
}
```

Regola:

- output tool no HTML
- output tool no testo lungo narrativo
- output tool solo dati e metadati

## Checklist implementativa

1. creare `interaction/tools/`
2. estrarre contratti tipizzati
3. introdurre analysis store
4. implementare tool GIS v1
5. cablare tool registry
6. adattare orchestrator
7. estendere test

## Exit criteria fase 1

Fase 1 chiusa solo se:

- analisi comuni e selezione corrente sono disponibili come tool backend veri
- confronto e ultima analisi non dipendono dal prompt
- orchestrator puo invocare tool tramite registry
- test automatici coprono casi base e failure principali

## Rischi

- payload geometrie troppo grande per sessione
- accoppiamento eccessivo tra summary e UI
- store sessione troppo povero per confronti futuri

Mitigazioni:

- salvare summary e riferimenti, non blob inutili
- separare output tool da rendering UI
- assegnare `analysis_id` stabile fin da subito

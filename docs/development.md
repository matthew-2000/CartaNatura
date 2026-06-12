# Sviluppo

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

## Test

```bash
python manage.py test cartaNatura
python manage.py check
```

## Modifica Analisi GIS

Verificare sempre:

- payload vuoto rifiutato
- CRS comuni/disegni coerenti
- clip con area senza vegetazione supportata
- comuni interessati corretti
- mappa aggiornata dopo risposta backend

## Modifica Assistente

Regole:

- aggiungere intenti in `InteractionIntent`
- documentare intenti in [conversational-interface.md](/Users/matteoercolino/IdeaProjects/CartaNatura/docs/conversational-interface.md:1)
- mantenere tool deterministici per numeri GIS
- non aggiungere azioni UI fuori allowlist server/client
- testare fast path rule-based e runtime LLM mockato

## Modifica Voce

Il flusso vocale usa `MediaRecorder` lato browser e OpenAI Audio Transcriptions lato Django.

Variabili:

- `OPENAI_API_KEY`
- `OPENAI_TRANSCRIPTION_MODEL`, default `gpt-4o-transcribe`

Regole:

- non inviare API key al browser
- non salvare transcript nei log sperimentali
- mantenere il transcript come input dello stesso orchestratore conversazionale

## Modifica Logging Sperimentale

Regole:

- aggiungere nuovi eventi solo in `ALLOWED_EVENT_TYPES`
- non salvare testo utente o transcript
- aggiungere test su sanitizzazione/export
- mantenere export JSON analizzabile senza dipendenze esterne

## Modifica Scenari Prezzo

Aggiornare `PRICE_OPTIONS` in [views.py](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/views.py:47). Ogni opzione deve avere:

- `label`
- `value` in EUR/t CO2

Il frontend calcola `value * totalCo2`.

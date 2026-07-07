# CartaNatura

Sistema WebGIS Django + Leaflet per analizzare aree forestali in Campania, stimare la CO2 sequestrata annualmente e calcolare il valore economico secondo scenari di prezzo configurabili. Il sistema supporta due modalità di lavoro confrontabili nello stesso ambiente: interfaccia grafica WebGIS tradizionale e interfaccia conversazionale testuale/vocale basata su LLM.

La mappa resta l'ambiente principale per selezionare aree, verificare risultati, interpretare categorie forestali e controllare ciò che viene prodotto dalla conversazione.

## Funzioni Principali

- selezione di comuni e geometrie disegnate in mappa
- identificazione delle categorie forestali Carta della Natura
- stima della CO2 sequestrata annualmente
- valutazione economica con scenari di prezzo alternativi
- chat testuale con intenti applicativi di dominio
- input vocale via registrazione browser e trascrizione OpenAI
- report analitico e PDF con mappa, metriche e comuni interessati
- logging sperimentale esportabile in JSON/JSONL
- protocollo pilot ASITA 2026 versionato

## Stack

- Python 3.11+
- Django 4
- GeoPandas / Pandas / Shapely
- Leaflet + Leaflet Draw
- JavaScript modulare vanilla
- OpenAI Responses API per l'assistente, quando configurata

## Avvio Locale

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

App:

- `http://127.0.0.1:8000/progettoGIS/cartaNatura/`

Docker:

```bash
cp .env.example .env
docker compose up --build
```

## Configurazione

Variabili principali:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CORS_ALLOWED_ORIGINS`
- `AI_ASSISTANT_ENABLED`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `OPENAI_TRANSCRIPTION_MODEL`
- `OPENAI_BASE_URL`

Gli scenari di prezzo CO2 sono configurati in [cartaNatura/domain/economics.py](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/domain/economics.py:8) come `PRICE_OPTIONS` e inviati al frontend via config applicativa.

## Architettura

Moduli principali:

- [cartaNatura/domain](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/domain): categorie forestali, coefficienti CO2, regole sui comuni
- [cartaNatura/services](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/services): parsing payload, dataset GIS, clip spaziale, sintesi analitica
- [cartaNatura/interaction](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/interaction): intenti, orchestratore, runtime LLM, tool deterministici, stato conversazionale
- [cartaNatura/experiments](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/experiments): eventi sperimentali e export JSON
- [cartaNatura/static/js/modules](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/static/js/modules): API client, mappa, analisi lato client, export PDF
- [cartaNatura/templates](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/templates): shell UI WebGIS

Dettaglio: [docs/architecture.md](/Users/matteoercolino/IdeaProjects/CartaNatura/docs/architecture.md:1).

## Flussi Utente

WebGIS tradizionale:

1. seleziona comuni o disegna area
2. avvia analisi
3. verifica risultati su mappa
4. apre report
5. sceglie scenario prezzo
6. esporta PDF

Conversazionale:

1. apre assistente
2. scrive o detta richiesta orientata al dominio
3. il sistema risolve intento e usa tool GIS deterministici
4. la mappa mostra area e risultati
5. l'assistente spiega cosa ha calcolato, parametri usati e area analizzata

Intenti documentati: [docs/conversational-interface.md](/Users/matteoercolino/IdeaProjects/CartaNatura/docs/conversational-interface.md:1).

## Logging Sperimentale

Endpoint:

- `GET /progettoGIS/cartaNatura/experiment/log` esporta log JSON
- `POST /progettoGIS/cartaNatura/experiment/log` registra evento controllato
- `DELETE /progettoGIS/cartaNatura/experiment/log` svuota log sessione

Metriche raccolte: tempo completamento task, numero interazioni, passaggi operativi, errori, richieste non comprese, uso testo/voce, operazioni completate, generazione report. Il log evita testo libero, transcript, identificativi personali e dati browser.

Dettaglio: [docs/experimental-logging.md](/Users/matteoercolino/IdeaProjects/CartaNatura/docs/experimental-logging.md:1).

## Pilot ASITA 2026

Protocollo operativo: [docs/asita-2026-pilot-protocol.md](/Users/matteoercolino/IdeaProjects/CartaNatura/docs/asita-2026-pilot-protocol.md:1).

Task sheet operatore: [docs/asita-2026-task-sheet.md](/Users/matteoercolino/IdeaProjects/CartaNatura/docs/asita-2026-task-sheet.md:1).

## Test

```bash
python manage.py test cartaNatura
python manage.py check
```

Con Makefile:

```bash
make test
make check
```

## Dataset Inclusi

- shapefile Carta della Natura: `cartaNatura/shapeCN/`
- comuni e confini Campania per UI: `cartaNatura/static/data/`
- asset guida e branding: `cartaNatura/static/assets/`

## Licenza

Vedi [LICENSE](/Users/matteoercolino/IdeaProjects/CartaNatura/LICENSE:1).

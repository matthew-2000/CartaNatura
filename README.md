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
- provider LLM configurabile: OpenAI remoto oppure Ollama locale

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
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DJANGO_DATA_DIR`: directory persistente per SQLite e telemetria raw JSONL
- `AI_ASSISTANT_ENABLED`
- `LLM_PROVIDER`: deve essere `openai` nel runtime conversazionale ASITA 2026
- `LLM_MODEL`, `LLM_BASE_URL`: compatibilità Ollama fuori dal percorso sperimentale; non sovrascrivono OpenAI
- `LLM_TIMEOUT_SECONDS`: timeout applicato sia a Responses API sia a STT
- `OPENAI_API_KEY`
- `OPENAI_MODEL`: modello OpenAI del pilot, default `gpt-5-mini`
- `OPENAI_TRANSCRIPTION_MODEL`
- `OPENAI_BASE_URL`
- `OLLAMA_MODEL`: richiesto se `LLM_PROVIDER=ollama` e `LLM_MODEL` è vuoto
- `OLLAMA_BASE_URL`: richiesto se `LLM_PROVIDER=ollama` e `LLM_BASE_URL` è vuoto
- `OLLAMA_THINK`: `false` per disattivare il reasoning dei modelli Ollama che lo supportano
- `OLLAMA_NUM_CTX`: contesto Ollama in token, default `16384`, per conservare istruzioni e risultati nelle richieste con più tool; valori maggiori richiedono più memoria

Gli scenari di prezzo CO2 sono configurati in [cartaNatura/domain/economics.py](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/domain/economics.py:8) come `PRICE_OPTIONS` e inviati al frontend via config applicativa.

Esempio OpenAI:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5-mini
OPENAI_BASE_URL=https://api.openai.com/v1
```

Esempio Ollama:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1
OLLAMA_THINK=false
```

Il percorso Web conversazionale usato nello studio accetta esclusivamente OpenAI. Se `LLM_PROVIDER` non è `openai`, se la configurazione è incompleta o se OpenAI non è disponibile, la richiesta fallisce esplicitamente prima di ogni operazione di dominio. Non esiste fallback verso Ollama. Il supporto Ollama rimane nel repository soltanto per uso non sperimentale tramite il layer provider-neutral.

### Railway

Il container applica automaticamente le migrazioni e avvia Django con Gunicorn sulla porta fornita dalla piattaforma. Su Railway la modalità debug viene disattivata automaticamente e `/data` diventa il percorso predefinito per database e log. Per conservarli tra i deploy, collegare un volume Railway montato su `/data`.

```env
DJANGO_SECRET_KEY=<una-chiave-lunga-e-casuale>
DJANGO_ALLOWED_HOSTS=.up.railway.app
DJANGO_CSRF_TRUSTED_ORIGINS=https://nome-servizio.up.railway.app
DJANGO_SECURE_SSL_REDIRECT=true
```

Se Railway espone `RAILWAY_PUBLIC_DOMAIN`, il dominio viene aggiunto automaticamente sia agli host consentiti sia alle origini CSRF attendibili.

## Architettura

Moduli principali:

- [cartaNatura/domain](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/domain): categorie forestali, coefficienti CO2, regole sui comuni
- [cartaNatura/services](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/services): parsing payload, dataset GIS, clip spaziale, sintesi analitica
- [cartaNatura/interaction](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/interaction): intenti, orchestratore, runtime LLM, tool deterministici, stato conversazionale
- [cartaNatura/telemetry.py](/Users/matteoercolino/IdeaProjects/CartaNatura/cartaNatura/telemetry.py): eventi runtime raw JSONL append-only
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

## Telemetria Raw

Il runtime salva eventi raw JSONL correlati tramite sessione anonima e, quando
pertinente, `interactionId`. Non calcola metriche di studio. Il backend è
autorevole per messaggi, transcript, risposte e tool; il browser registra solo
azioni e risultati client-side. Audio, participant ID, IP e user-agent non sono
persistiti.

Dettaglio: [docs/experimental-logging.md](/Users/matteoercolino/IdeaProjects/CartaNatura/docs/experimental-logging.md:1).

## Pilot ASITA 2026

Protocollo operativo: [docs/asita-2026-pilot-protocol.md](/Users/matteoercolino/IdeaProjects/CartaNatura/docs/asita-2026-pilot-protocol.md:1).

Task sheet operatore: [docs/asita-2026-task-sheet.md](/Users/matteoercolino/IdeaProjects/CartaNatura/docs/asita-2026-task-sheet.md:1).

Il protocollo, i partecipanti, le consegne e l'assegnazione delle condizioni sono
gestiti manualmente dall'operatore fuori dall'app. Per impostare una prova usare
`?mode=gui-only` oppure `?mode=conversational-only`; `?mode=full` riattiva entrambe.
I documenti di protocollo precedenti restano materiale storico e non descrivono
un lifecycle implementato dal runtime corrente.

Funzioni provate online e limiti: [docs/asita-2026-feasibility-check.md](docs/asita-2026-feasibility-check.md).

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

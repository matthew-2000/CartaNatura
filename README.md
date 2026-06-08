# CartaNatura

Web GIS Django + Leaflet per analizzare la vegetazione forestale in Campania a partire da comuni selezionati o geometrie disegnate in mappa. L'app interseca la selezione con il dataset Carta della Natura, restituisce le categorie forestali rilevate e genera una sintesi con superficie, CO2 annua stimata e valorizzazione economica.

## Stato del progetto

- Backend GIS refactorizzato in layer `domain` + `services`
- Frontend modularizzato in ES modules
- UI desktop e mobile rifinita
- Dataset locali inclusi nella repository
- Test automatici minimi presenti su parsing payload, servizio GIS e smoke view

## Stack

- Python 3.11+
- Django 4
- GeoPandas / Pandas / Shapely
- Leaflet + Leaflet Draw
- JavaScript modulare vanilla

## Quick Start

### 1. Setup locale

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

App disponibile su:

- `http://127.0.0.1:8000/progettoGIS/cartaNatura/`

### 2. Setup con Docker

```bash
cp .env.example .env
docker compose up --build
```

## Variabili ambiente

Le variabili supportate sono:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CORS_ALLOWED_ORIGINS`

Vedi [.env.example](/Users/matteoercolino/IdeaProjects/CartaNatura/.env.example:1).

## Comandi utili

Se usi il [Makefile](/Users/matteoercolino/IdeaProjects/CartaNatura/Makefile:1):

```bash
make install
make migrate
make run
make test
make check
```

Senza `make`:

```bash
python manage.py test cartaNatura
python manage.py check
```

## Struttura repository

```text
CartaNatura/
  cartaNatura/
    domain/           # regole di dominio: categorie vegetazione, comuni
    services/         # parsing payload, dataset loader, clip GIS
    static/           # css, js, assets, geojson client-side
    templates/        # pagina e shell UI
    tests.py          # smoke/unit tests
    views.py          # view Django sottili
  progettoGIS/        # settings e routing globale Django
  docs/               # architettura, sviluppo, piano refactor
  Dockerfile
  docker-compose.yml
  .env.example
  Makefile
```

## Architettura

Documentazione consigliata:

- [docs/architecture.md](/Users/matteoercolino/IdeaProjects/CartaNatura/docs/architecture.md:1)
- [docs/development.md](/Users/matteoercolino/IdeaProjects/CartaNatura/docs/development.md:1)
- [docs/refactoring-plan.md](/Users/matteoercolino/IdeaProjects/CartaNatura/docs/refactoring-plan.md:1)
- [docs/ai-interaction-research.md](/Users/matteoercolino/IdeaProjects/CartaNatura/docs/ai-interaction-research.md:1)
- [docs/assistant-product-contract.md](/Users/matteoercolino/IdeaProjects/CartaNatura/docs/assistant-product-contract.md:1)
- [docs/assistant-phase-1-backlog.md](/Users/matteoercolino/IdeaProjects/CartaNatura/docs/assistant-phase-1-backlog.md:1)

## Flusso applicativo

1. L'utente seleziona uno o più comuni oppure disegna una geometria.
2. Il frontend invia una richiesta GeoJSON a `/progettoGIS/cartaNatura/gis`.
3. Django valida il payload, costruisce la maschera di analisi e fa il clip sul dataset Carta della Natura.
4. Il frontend renderizza i risultati, aggrega le categorie vegetazionali e produce il report analitico.
5. L'utente può stimare un valore economico ed esportare il report in PDF.

## Datasets inclusi

La repository include dati GIS locali:

- shapefile Carta della Natura: `cartaNatura/shapeCN/` circa `53 MB`
- geojson comuni / confini Campania: `cartaNatura/static/data/` circa `20 MB`
- asset guida e branding: `cartaNatura/static/assets/` circa `5.6 MB`

Questo rende il repository pesante. Se il progetto evolve, una direzione sensata è spostare i dataset più grandi in uno storage versionato separato o in un artefact registry.

## Limiti noti

- Il progetto usa SQLite per sviluppo locale.
- I test non coprono ancora in profondità tutti i casi GIS edge-case.
- Gli asset statici sono ancora più pesanti del necessario.
- Il Docker setup è orientato a sviluppo, non a produzione.

## Licenza

Vedi [LICENSE](/Users/matteoercolino/IdeaProjects/CartaNatura/LICENSE:1).

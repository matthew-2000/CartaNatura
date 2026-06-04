# Sviluppo

## Prerequisiti

- Python 3.11 o superiore
- `pip`
- ambiente virtuale consigliato
- opzionale: Docker + Docker Compose

## Avvio locale

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

Apri:

- `http://127.0.0.1:8000/progettoGIS/cartaNatura/`

## Variabili ambiente

Il progetto legge `.env` automaticamente tramite `python-dotenv`.

Variabili disponibili:

```env
DJANGO_SECRET_KEY=change-me
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
DJANGO_CORS_ALLOWED_ORIGINS=
```

## Comandi standard

### Test

```bash
python manage.py test cartaNatura
```

### Check Django

```bash
python manage.py check
```

### Raccolta statici

```bash
python manage.py collectstatic --noinput
```

## Makefile

Il repository espone scorciatoie:

```bash
make install
make migrate
make run
make test
make check
make collectstatic
```

## Docker

```bash
cp .env.example .env
docker compose up --build
```

Uso previsto:

- sviluppo locale
- smoke environment

Non è ancora un setup production-grade.

## Convenzioni operative

- usare `domain/` per regole pure
- usare `services/` per logica GIS e accesso dataset
- tenere le view Django sottili
- evitare asset o GeoJSON embedded dentro JS applicativo
- non introdurre dipendenze da servizi esterni per il flusso base

## Testing manuale minimo consigliato

1. Aprire la home.
2. Selezionare almeno un comune.
3. Eseguire `Estrai`.
4. Aprire `Analisi`.
5. Calcolare un valore economico.
6. Verificare export PDF.
7. Verificare layout desktop e mobile.

## Troubleshooting

### GeoPandas / shapely non installano

Aggiorna `pip`, `setuptools`, `wheel`:

```bash
pip install --upgrade pip setuptools wheel
```

### L'app parte ma la mappa è vuota

Controlla:

- presenza dei file in `cartaNatura/static/data/`
- URL statici serviti correttamente
- errori browser console

### L'endpoint GIS risponde lentamente

Primo check:

- dataset caricati da disco
- dimensione layer
- ambiente Docker troppo limitato

Il backend usa cache in-process sui dataset, quindi la prima richiesta tende a costare più delle successive.

## Cosa non fare

- non spostare logica di mapping vegetazione dentro `views.py`
- non duplicare costanti business in più punti senza motivo
- non usare URL assoluti hardcoded per l'API
- non rimettere dataset grossi direttamente in `app.js`

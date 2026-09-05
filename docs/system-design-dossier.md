# Carta Natura — System Design Dossier

> **Nota di versione — 4 settembre 2026.** Le sezioni che descrivono il riuso di `ettari` dopo il clipping, i mismatch case-sensitive e le relative limitazioni fotografano la revisione pre-stabilizzazione. La nuova baseline GIS ufficiale è in [`asita-2026-gis-baseline.md`](asita-2026-gis-baseline.md). L'architettura generale resta applicabile; i claim numerici vanno riletti alla luce della correzione.

Stato dell'audit: 4 settembre 2026  
Scopo: base tecnica verificabile per la futura sezione *System Design*; questo documento non è il testo del paper.  
Repository auditato: `/Users/matteoercolino/IdeaProjects/CartaNatura`

## 0. Metodo, perimetro e legenda epistemica

L'audit è stato condotto seguendo gli entry point HTTP, i contratti dati, il runtime conversazionale, i tool, i servizi GIS, lo stato browser/server, il logging sperimentale e i test. README e documenti esistenti sono stati usati solo come indici; le conclusioni derivano dal codice eseguibile e dai dati inclusi.

Verifiche eseguite:

- inventario di tutti i file applicativi Python, JavaScript, template, configurazione e dataset;
- tracciamento degli endpoint dalla UI fino ai servizi di dominio;
- ispezione dei contratti tool e del loop LLM;
- ispezione diretta dei tre dataset geografici;
- esecuzione di `python manage.py test`: **122 test superati**, nessun errore di system check;
- nessuna modifica al codice applicativo.

Legenda usata in tutto il dossier:

- **[IMPLEMENTED AND VERIFIED]**: comportamento direttamente presente nel codice, o coperto dalla suite eseguita.
- **[INFERRED FROM IMPLEMENTATION]**: conseguenza ragionevole dell'implementazione, non dichiarata o verificata end-to-end con un provider/dataset esterno reale.
- **[NOT FOUND / UNCERTAIN]**: informazione non ricostruibile con certezza dal repository.

I riferimenti hanno forma `percorso:simbolo` o `percorso:riga`. Le righe sono riferite allo stato auditato e possono spostarsi; il simbolo è il riferimento più stabile.

## 1. Executive technical reconstruction

**[IMPLEMENTED AND VERIFIED]** Carta Natura è una web application monolitica Django con frontend JavaScript vanilla e mappa Leaflet. Serve una singola shell UI, dataset GeoJSON statici, endpoint JSON/SSE e pagine amministrative dello studio. La computazione geospaziale avviene nel processo Django tramite GeoPandas/Shapely; non è presente un spatial DB. Riferimenti: `progettoGIS/settings.py`, `progettoGIS/urls.py`, `cartaNatura/urls.py`, `cartaNatura/templates/cartaNatura/index.html`, `cartaNatura/services/gis_clip.py`.

**[IMPLEMENTED AND VERIFIED]** Il sistema presenta due percorsi di interazione che condividono la stessa pipeline GIS:

1. GUI WebGIS: l'utente seleziona comuni e/o disegna geometrie, il browser invia un payload strutturato a `POST /gis`, Django valida, esegue il clip, calcola metriche e restituisce geometrie e summary;
2. interfaccia conversazionale: l'utente scrive o detta, un LLM interpreta la richiesta e orchestra uno o più tool; i tool richiamano gli stessi servizi deterministici, mentre il modello produce la spiegazione finale.

Riferimenti: `cartaNatura/static/js/app.js:buildAnalysisPayload`, `runAnalysis`, `runAssistantInteraction`; `cartaNatura/views.py:gis`, `interact`, `interact_stream`; `cartaNatura/interaction/orchestrator.py:InteractionOrchestrator`; `cartaNatura/interaction/tools/gis_analysis.py:_build_analysis_result`.

**[IMPLEMENTED AND VERIFIED]** Il confine di fiducia principale è architetturale: l'LLM decide *quale* operazione chiedere, con quali riferimenti linguistici e in quale sequenza; il backend esegue lookup, validazione, clip, aggregazioni, valutazioni, confronti, lookup dello storico e filtri. Le geometrie ritagliate non vengono reinserite nel contesto del modello; al modello tornano identificativo, comuni e summary numerico. Riferimenti: `cartaNatura/interaction/assistant_runtime.py:AssistantToolExecutor`, `_build_model_tool_output`, `_build_instructions`.

**[IMPLEMENTED AND VERIFIED]** La mappa e i pannelli visualizzano i payload strutturati, non numeri estratti dal testo dell'assistente. Questo rende l'output operativo dell'interfaccia più affidabile del solo testo generato. Riferimenti: `cartaNatura/static/js/app.js:applyAnalysisResult`, `applyEconomicResult`, `applyAssistantMapFilter`, `routeStructuredAssistantResult`.

**[IMPLEMENTED AND VERIFIED]** Non esiste TTS. La voce è input-only: MediaRecorder nel browser → upload audio → OpenAI transcription → testo editabile o invio automatico → normale pipeline conversazionale. `TextToSpeechProvider` è soltanto un protocollo non implementato; `audio_output_text` non viene serializzato come audio né riprodotto. Riferimenti: `cartaNatura/static/js/app.js:initializeVoiceInput`; `cartaNatura/interaction/voice.py:transcribe_uploaded_audio`; `cartaNatura/interaction/providers.py:TextToSpeechProvider`; `cartaNatura/views.py:_serialize_interaction_response`.

## 2. Architettura complessiva

### 2.1 Strati logici

#### Browser / presentation layer

**[IMPLEMENTED AND VERIFIED]** La UI è una pagina Django con componenti imperativi JavaScript:

- `index.html`: shell di navigazione, mappa, pannelli selezione/report/storico/assistente e dipendenze browser;
- `app.js`: stato client, wiring degli eventi, policy sperimentale, orchestration UI, voce e routing degli output assistente;
- `map-controller.js`: Leaflet, layer di base, selezioni, disegno e rendering dei risultati;
- `api.js`: chiamate HTTP, CSRF, parser SSE e upload voce;
- `analysis.js`: calcoli/formatting client e fallback di summary;
- `analysis-history.js`: viste di storico e confronto;
- `pdf-export.js`: report PDF client-side;
- `workspace-ui.js`: layout e resizing dei pannelli.

Riferimenti: `cartaNatura/static/js/app.js:loadModules`; `cartaNatura/templates/cartaNatura/index.html`.

#### HTTP/application layer

**[IMPLEMENTED AND VERIFIED]** `cartaNatura/views.py` espone:

- pagina principale;
- analisi GIS tradizionale;
- CRUD e confronto dello storico;
- interazione conversazionale sincrona e SSE;
- trascrizione voce;
- log sperimentale e sessioni di studio;
- archivio amministrativo protetto da password condivisa.

Riferimenti: `cartaNatura/urls.py:urlpatterns`; `cartaNatura/views.py`.

#### Interaction/orchestration layer

**[IMPLEMENTED AND VERIFIED]** `InteractionOrchestrator` separa due casi:

- richieste `WEB_MAP` con selezione strutturata: risoluzione rule-based e handler diretto, senza LLM;
- qualsiasi richiesta testuale/voice: `AssistantRuntime` obbligatorio e pianificazione LLM con tool calling.

Il `RuleBasedIntentResolver` e gli handler testuali esistono, ma nel wiring corrente la chat standard non li usa: il resolver viene raggiunto solo per una selezione grafica. Le classi `AnalyzeMunicipalitiesHandler`, `ExplainLastAnalysisHandler`, `CompareAnalysesHandler` e `ResetSessionHandler` restano utilizzabili direttamente e sono testate, ma sono un percorso secondario/legacy rispetto al runtime tool-based. Riferimenti: `cartaNatura/interaction/orchestrator.py:handle`, `build_default_orchestrator`; `cartaNatura/interaction/resolvers.py`; `cartaNatura/interaction/handlers.py`.

#### Domain and deterministic services

**[IMPLEMENTED AND VERIFIED]** Il dominio comprende:

- 12 categorie vegetazionali, 24 codici, colore e coefficiente CO₂ per ettaro;
- 4 scenari economici fissi;
- 81 comuni esclusi come privi di dati natura.

Riferimenti: `cartaNatura/domain/vegetation.py:VEGETATION_CATEGORIES`; `cartaNatura/domain/economics.py:PRICE_OPTIONS`; `cartaNatura/domain/municipalities.py:MUNICIPALITIES_WITHOUT_NATURE`.

**[IMPLEMENTED AND VERIFIED]** I servizi caricano dataset con cache di processo, validano il payload, convertono CRS, eseguono clip e aggregano metriche. Riferimenti: `cartaNatura/services/datasets.py`; `payloads.py`; `gis_clip.py`; `analysis_summary.py`.

#### Persistence and observability

**[IMPLEMENTED AND VERIFIED]** Stato conversazionale e storico sono salvati nella sessione Django. Le sessioni Django usano il backend predefinito database e il DB configurato è SQLite. I log dello studio controllato sono inoltre persistiti su filesystem in JSONL più un summary JSON. Riferimenti: `progettoGIS/settings.py:DATABASES`, `STUDY_LOG_ROOT`; `cartaNatura/interaction/session.py:DjangoSessionStore`; `analysis_store.py:DjangoSessionAnalysisStore`; `experiments/study_logging.py`.

**[INFERRED FROM IMPLEMENTATION]** Poiché `SESSION_ENGINE` non è ridefinito, la persistenza sessione è quella Django database-backed (`django_session`) dentro `db.sqlite3`; il cookie contiene l'identificatore di sessione, non lo storico completo.

### 2.2 Deployment topology

**[IMPLEMENTED AND VERIFIED]** Il deployment previsto è un singolo container Python 3.11 con Gunicorn, WhiteNoise per statici e SQLite/log su `DJANGO_DATA_DIR`; su Railway il default è `/data`. Il Docker Compose di sviluppo usa `runserver` e monta il repository in `/app`. Riferimenti: `Dockerfile`; `docker-compose.yml`; `progettoGIS/settings.py:RUNNING_ON_RAILWAY`, `DATA_DIR`, `STATICFILES_STORAGE`.

**[IMPLEMENTED AND VERIFIED]** Il browser dipende anche da risorse remote: tile OpenStreetMap, Google Fonts, Bootstrap 4.3.1 e jsPDF CDN. Leaflet, Leaflet Draw, GeometryUtil e `dom-to-image` sono vendorizzati localmente. Riferimenti: `index.html`; `map-controller.js:constructor`.

**[NOT FOUND / UNCERTAIN]** Non sono presenti reverse proxy config, autoscaling, object storage, job queue, CDN applicativo, monitoring service, backup automatico o replica del database.

## 3. Stack tecnologico effettivo

**[IMPLEMENTED AND VERIFIED]** Backend:

- Python 3.11 nel container;
- Django `>=4.1,<5.0`;
- GeoPandas `>=0.14,<1.0`, Pandas `>=2,<3`, Shapely transitiva;
- OpenAI Python SDK `>=1.93,<2.0`;
- SQLite, Gunicorn, WhiteNoise, django-cors-headers, python-dotenv.

Riferimenti: `requirements.txt`, `Dockerfile`, `progettoGIS/settings.py`.

**[IMPLEMENTED AND VERIFIED]** Frontend:

- HTML/CSS e JavaScript ES modules, senza React/Vue/Svelte;
- Leaflet + Leaflet Draw + Leaflet GeometryUtil;
- Fetch API, Streams API/SSE parsing, MediaRecorder;
- jsPDF 1.5.3 e dom-to-image per il PDF;
- OpenStreetMap come tile basemap.

Riferimenti: `index.html`; `static/js/app.js`; `modules/api.js`; `modules/map-controller.js`; `modules/pdf-export.js`.

**[IMPLEMENTED AND VERIFIED]** AI:

- OpenAI Responses API con streaming e strict tool schema;
- Ollama `/api/chat`, tool calling e normalizzazione nel contratto Responses-like;
- OpenAI Audio Transcriptions per STT anche quando il provider LLM scelto è Ollama.

Riferimenti: `interaction/llm.py:OpenAiResponsesLlmProvider`, `OllamaChatLlmProvider`; `interaction/voice.py`.

## 4. WebGIS tradizionale

### 4.1 Selezioni spaziali

**[IMPLEMENTED AND VERIFIED]** Sono supportate due classi di area, combinabili nello stesso payload:

- `municipalities`: una FeatureCollection dei comuni selezionati, nel dataset EPSG:32633;
- `drawn`: geometrie disegnate da Leaflet, EPSG:4326.

La UI abilita poligono e rettangolo; marker, polyline, circle e circlemarker sono disabilitati. Le geometrie disegnate possono essere modificate ed eliminate. Riferimenti: `map-controller.js:_initializeControls`, `buildSelectedMunicipalityGeoJson`, `buildDrawnGeoJson`; `app.js:buildAnalysisPayload`; `services/payloads.py:SUPPORTED_AREA_KINDS`, `EXPECTED_CRS_BY_KIND`.

**[IMPLEMENTED AND VERIFIED]** L'utente può combinare più comuni e una o più geometrie disegnate. Il backend ammette al massimo una area wrapper per ciascun `kind`, ma ogni FeatureCollection può contenere più feature. Riferimenti: `services/payloads.py:parse_selection_payload`, `_validate_unique_area_kinds`.

### 4.2 Validazione

**[IMPLEMENTED AND VERIFIED]** Il backend verifica:

- presenza di almeno un'area;
- kind ammesso e non duplicato;
- FeatureCollection non vuota;
- CRS dichiarato, se presente;
- geometria Shapely non vuota e valida.

Riferimenti: `services/payloads.py:parse_selection_payload`, `_validate_declared_crs`, `_validate_feature_geometries`. Test: `PayloadParsingTests`.

**[IMPLEMENTED AND VERIFIED]** Se il GeoJSON non dichiara il CRS, il backend assegna il CRS atteso in base al kind. Questa è una convenzione di contratto, non un rilevamento automatico. Riferimenti: `services/gis_clip.py:SOURCE_EPSG_BY_KIND`, `_area_to_geodataframe`.

### 4.3 Elaborazione GIS

**[IMPLEMENTED AND VERIFIED]** Pipeline:

1. parsing in `SelectionRequest`/`SelectionArea`;
2. costruzione GeoDataFrame e conversione a EPSG:4326;
3. concatenazione delle aree in una maschera;
4. per aree disegnate, clip dei confini comunali per ricavare i comuni intersecati;
5. clip del layer Carta della Natura con la maschera;
6. rimozione dalla lista dei comuni degli 81 nomi hard-coded senza dati natura;
7. serializzazione del risultato clipped in GeoJSON;
8. aggregazione per categoria supportata.

Riferimenti: `services/gis_clip.py:clip_selection`; `interaction/tools/gis_analysis.py:_build_analysis_result`.

**[IMPLEMENTED AND VERIFIED]** Dataset osservati nell'audit:

- `shapeCN/CNPulita.shp`: 10.058 poligoni, EPSG:32633, 24 codici distinti, campi tra cui `CODICE`, `ettari`, `nomeclasse`;
- `moddedCampania.geojson`: 550 multipoligoni comunali, EPSG:4326;
- `campania-municipalities-32633.geojson`: 550 multipoligoni comunali, EPSG:32633.

Riferimenti loader: `services/datasets.py`. I conteggi derivano da lettura diretta con GeoPandas durante l'audit.

### 4.4 Pipeline CO₂

**[IMPLEMENTED AND VERIFIED]** Per ogni feature clipped il codice:

- legge `CODICE` e `ettari`;
- risolve la categoria in `VEGETATION_BY_CODE`;
- accumula ettari per categoria;
- calcola `co2_per_hectare × hectares`;
- somma `totalCo2` e `totalHectares`;
- determina `topCategory` per superficie.

Solo codici mappati contribuiscono alle metriche. Output: `items`, `totalCo2`, `totalHectares`, `hasSupportedVegetation`, `topCategory`. Riferimenti: `services/analysis_summary.py:summarize_clipped_features`; `domain/vegetation.py`.

**[IMPLEMENTED AND VERIFIED — CRITICAL LIMITATION]** Dopo il clip non viene ricalcolata l'area geometrica della porzione ritagliata. `summarize_clipped_features` usa il valore `ettari` originale conservato come attributo della feature sorgente. Per selezioni che tagliano solo parte di un poligono Carta della Natura, superficie e CO₂ possono quindi riferirsi all'intero poligono originario, non alla sola intersezione. Riferimenti: `gis_clip.py:clip_selection`; `analysis_summary.py:summarize_clipped_features`.

**[IMPLEMENTED AND VERIFIED — CRITICAL LIMITATION]** Il lookup `VEGETATION_BY_CODE.get(str(code))` è case-sensitive. Quattro codici presenti nello shapefile non coincidono con la configurazione: dataset `41.B`, `41.C1`, `41.Lcn`, `44.D2cn`; mapping `41.b`, `41.c1`, `41.lcn`, `44.d2cn`. Le feature con questi codici non contribuiscono quindi a ettari o CO₂. Sono 615 feature con un attributo `ettari` complessivo di circa 13.900,85 ha sull'intero dataset; sono coinvolte parzialmente “Altri boschi caducifogli”, “Altri boschi di conifere, pure o miste” e “Boschi igrofili”. Riferimenti: `services/analysis_summary.py:summarize_clipped_features`; `domain/vegetation.py:VEGETATION_CATEGORIES`; verifica diretta dei valori distinti in `shapeCN/CNPulita.shp`.

**[NOT FOUND / UNCERTAIN]** Non sono presenti nel repository provenienza scientifica, anno di riferimento, incertezza, unità formalmente dichiarata o validazione bibliografica dei coefficienti `co2_per_hectare`. L'UI li interpreta come tCO₂/anno per ettaro, ma la fonte deve essere confermata dall'autore.

### 4.5 Risultati, mappa ed economia nella GUI

**[IMPLEMENTED AND VERIFIED]** Il browser riceve `clipped`, comuni intersecati e summary; aggiorna layer natura, contorni comunali, KPI, categorie, storico e pannello report. Le selezioni di input vengono cancellate dopo l'applicazione del risultato. Riferimenti: `app.js:applyAnalysisResult`; `map-controller.js:renderNature`, `renderIntersectedMunicipalities`.

**[IMPLEMENTED AND VERIFIED]** Nella GUI tradizionale il valore economico è calcolato nel browser come `totalCo2 × prezzo`. I quattro prezzi arrivano dalla config server ma il calcolo non richiama un endpoint backend. Riferimenti: `app.js:renderInfoSummary` righe 2494–2519; `analysis.js:buildEconomicScenarioRows`; `views.py:index`.

**[IMPLEMENTED AND VERIFIED]** Ne consegue che una valutazione eseguita solo con la GUI non viene salvata nel record `StoredAnalysis`; la valutazione conversazionale invece usa un tool backend e aggiorna `economic_valuation`. Riferimenti: `interaction/tools/economic_valuation.py:calculate_analysis_economic_value`; `app.js:renderSelectedScenarioValue`.

## 5. Estensione conversazionale

### 5.1 Ingresso e orchestrazione

**[IMPLEMENTED AND VERIFIED]** Il client invia:

- `message`;
- `context.selectedMunicipalities`;
- `context.mapExtent`;
- `context.selectionPayload` corrente;
- `context.displayedAnalysisId`;
- `metadata.interactionMode` (`text` o `voice`).

Riferimenti: `app.js:buildInteractionContext`, `runAssistantInteraction`; `views.py:_build_text_interaction_request`; `interaction/ui_context.py:build_interaction_context`.

**[IMPLEMENTED AND VERIFIED]** Il runtime esegue un loop model → tool → output tool → model, con tool non paralleli e massimo 6 round. Dopo ogni tool il modello può pianificare ulteriori operazioni; questo supporta richieste composte nello stesso turno. Riferimenti: `assistant_runtime.py:_run_response_loop`, `stream_handle`, `_build_model_request_payload` (`parallel_tool_calls=False`). Test: `LlmRequestPlanningTests`.

### 5.2 Ruolo dell'LLM

**[IMPLEMENTED AND VERIFIED]** Il modello è responsabile di:

- interpretazione semantica e disambiguazione;
- scelta del tool e costruzione degli argomenti;
- composizione sequenziale di più tool;
- scelta dell'intent finale;
- formulazione del testo finale e della domanda di chiarimento;
- proposta di follow-up e scelta tra quattro UI actions consentite.

Riferimenti: `assistant_runtime.py:_build_instructions`, `_build_model_tools`, `_build_final_response_format`.

**[IMPLEMENTED AND VERIFIED]** Il modello non esegue direttamente:

- lookup canonico dei comuni;
- costruzione della selezione geometrica;
- clip o intersezioni;
- calcolo ettari/CO₂;
- calcolo e confronto economico;
- recupero/confronto dello storico;
- validazione del filtro categoria;
- persistenza o reset;
- rendering mappa/UI/PDF.

Queste operazioni sono nei tool e nel client deterministico. Riferimenti: `interaction/tools/*`; `services/*`; `app.js`.

### 5.3 Prompt e grounding

**[IMPLEMENTED AND VERIFIED]** Le istruzioni di sistema impongono italiano, plain text, nessun JSON visibile, nessun dato GIS inventato, numeri solo da tool, completamento di tutti i passaggi, gestione distinta di nuovi comuni/selezione corrente/ultima analisi/storico, uso dei tool metodologici e output finale JSON schema. Riferimento completo: `assistant_runtime.py:_build_instructions`.

**[IMPLEMENTED AND VERIFIED]** Ogni turno include un user prompt JSON con:

- messaggio corrente;
- stato UI ridotto;
- ultima analisi;
- ultimo intent e ultimi 8 messaggi;
- elenco tool, scenari prezzo e categorie;
- regole di grounding.

Riferimento: `assistant_runtime.py:_build_user_prompt`.

**[IMPLEMENTED AND VERIFIED]** L'output finale deve aderire a uno schema rigido con `intent`, `assistant_text`, chiarimento, `ui_actions`, citazioni interne e suggerimenti. Se il primo output finale non è JSON, il runtime fa un singolo turno di riformattazione senza tool; se ancora non valido/vuoto, fallisce. Riferimenti: `_build_final_response_format`, `_parse_final_payload`, `_formatting_request`.

### 5.4 Tool/function calling inventory dettagliato

Tutti i tool sotto sono **[IMPLEMENTED AND VERIFIED]**. Contratti modello: `assistant_runtime.py:_build_model_tools`; dispatch: `AssistantToolExecutor.execute`; implementazioni: `interaction/tools/`.

| Tool esposto al modello | Input | Output/responsabilità deterministica | Effetto su stato/UI |
|---|---|---|---|
| `search_municipalities` | `query`, `limit` | match esatti e suggerimenti sul dataset | solo grounding testuale |
| `analyze_municipalities` | `municipality_names[]` | selezione canonica, clip, summary, GeoJSON | salva analisi; aggiorna mappa/report |
| `analyze_current_selection` | nessuno | usa esclusivamente selezione UI corrente, poi clip/summary | salva analisi; aggiorna mappa/report |
| `filter_last_analysis_categories` | `category_names[]`, `show_all` | risolve categorie dell'analisi *visualizzata* | filtro visuale mappa, KPI invariati |
| `calculate_economic_value` | `scenario_key` enum | `totalCo2 × prezzo` sull'ultima analisi | persiste valutazione; aggiorna report |
| `compare_economic_scenarios` | nessuno | calcola tutti i quattro scenari sull'ultima analisi | aggiorna pannello report |
| `get_last_analysis` | nessuno | serializza ultima analisi salvata | grounding per spiegazione |
| `compare_recent_analyses` | `recent_count` | confronto ultime N (2–10) | apre confronto storico |
| `list_recent_analyses` | `limit` | lista compatta newest-first (1–50) | può aprire storico |
| `compare_saved_analyses` | `selectors[]` | risolve id/label/comune, rifiuta ambiguità, confronta | apre confronto storico |
| `get_methodology` | nessuno | descrizione statica della metodologia | grounding testuale |
| `reset_analysis_context` | nessuno | cancella storico analisi server/sessione | reset contesto e workspace client |
| `prepare_report` | nessuno | recupera contesto dell'ultima analisi e action `open_existing_report` | apre report esistente; non crea PDF |

### 5.5 Validazione degli argomenti del modello

**[IMPLEMENTED AND VERIFIED]** Primo livello: JSON Schema dei tool con `strict=True`, tipi, required, `additionalProperties=False` ed enum per lo scenario economico (OpenAI). Per Ollama gli stessi `parameters` vengono convertiti nel formato chat tool, ma non vi è una garanzia repository-side che ogni modello locale rispetti lo schema. Riferimenti: `_build_model_tools`; `llm.py:_to_ollama_tool`.

**[IMPLEMENTED AND VERIFIED]** Secondo livello: coercizione e limiti nell'executor/tool (`str`, `int`, range 1–10/50, liste pulite), lookup esatto dei comuni, convalida scenario, esistenza analisi, ambiguità selector, corrispondenza dell'analisi visualizzata e validazione GIS completa. Riferimenti: `AssistantToolExecutor.execute`; `municipality_lookup.py`; `analysis_history.py`; `economic_valuation.py`; `map_filtering.py`; `payloads.py`.

**[IMPLEMENTED AND VERIFIED]** Un `ValueError` di tool viene convertito in `{ok:false,error:...}` e restituito al modello, che può correggere la chiamata o chiedere chiarimento. Eccezioni non previste propagano come errore. Riferimento: `assistant_runtime.py:_execute_tool_call`. Test: `test_tool_error_goes_back_to_model_for_recovery`.

**[IMPLEMENTED AND VERIFIED — LIMITATION]** Se una lista di comuni contiene nomi validi e inventati, la costruzione geometrica filtra per match esatto e può procedere con il sottoinsieme valido; non verifica che *tutti* i nomi richiesti siano stati risolti. Se nessuno è valido, fallisce. Riferimento: `services/municipality_text.py:build_municipality_selection_payload`.

### 5.6 Contesto e stato

**[IMPLEMENTED AND VERIFIED]** `SessionContext` conserva:

- `selection_payload` dell'ultima analisi/turno pertinente;
- `last_analysis` compatta;
- `last_intent`;
- metadata, in particolare fino a 16 messaggi user/assistant.

Riferimenti: `interaction/models.py:SessionContext`; `session.py:DjangoSessionStore`; `assistant_runtime.py:_updated_conversation_messages`.

**[IMPLEMENTED AND VERIFIED]** `InteractionContext` è invece uno snapshot del browser per il turno corrente: comuni selezionati, extent, selezione corrente, id analisi visualizzata. Il prompt distingue esplicitamente selezione corrente, ultima analisi e analisi visualizzata. Riferimenti: `models.py:InteractionContext`; `ui_context.py`; `_build_user_prompt`.

**[IMPLEMENTED AND VERIFIED]** Dopo una nuova analisi nello stesso tool loop, il runtime aggiorna il contesto interno del turno: la nuova analisi diventa visualizzata, la selezione corrente viene svuotata e tool successivi operano sul nuovo risultato. Riferimento: `assistant_runtime.py:_advance_tool_context`.

**[IMPLEMENTED AND VERIFIED]** Gli id di risposta provider non sono riusati tra turni; la continuità cross-turn è ricostruita esplicitamente con messaggi e contesto di dominio. Gli id sono usati solo dentro la catena tool dello stesso turno. Riferimenti: `_previous_response_id`, `_build_updated_context`.

**[INFERRED FROM IMPLEMENTATION — LIMITATION]** Con Ollama, lo storico può apparire sia come messaggi chat (fino a 16) sia incorporato nel JSON del prompt corrente (ultimi 8), creando duplicazione contestuale. OpenAI elimina `conversation_messages` dal payload provider e vede il contesto incorporato. Riferimenti: `llm.py:_without_provider_only_payload`, `_build_ollama_messages`; `assistant_runtime.py:_build_user_prompt`.

### 5.7 Aggiornamenti UI e mappa

**[IMPLEMENTED AND VERIFIED]** Gli output strutturati determinano:

- `analysisResult.clipped`: nuovo layer natura, contorni comuni, KPI/report e storico;
- comparison in `analysisResult.analyses`: pannello storico/confronto;
- `economicResult`: prezzo e valore nel report;
- `scenarioComparison`: dati scenari nel report;
- `reportContext`: apertura del report esistente;
- `mapFilter`: filtro delle feature già caricate senza ricalcolo;
- `uiHints.uiActions`: apertura report, legenda o focus mappa, dopo whitelist server e client.

Riferimenti: `app.js:routeStructuredAssistantResult`, `applyAnalysisResult`, `applyEconomicResult`, `applyAssistantMapFilter`, `applyAssistantUiActions`; `interaction/ui_actions.py`.

**[IMPLEMENTED AND VERIFIED]** Un filtro categoria conserva `state.clipped` completo e filtra solo le feature renderizzate. Report, KPI ed economia restano riferiti all'analisi completa. Riferimenti: `map_filtering.py`; `app.js:applyAssistantMapFilter`, `renderAnalysisScopeState`.

## 6. Provider LLM e failure policy

### 6.1 OpenAI

**[IMPLEMENTED AND VERIFIED]** `OpenAiResponsesLlmProvider` usa `OpenAI.responses.create/stream`, `OPENAI_MODEL` (default `gpt-5-mini`), `OPENAI_BASE_URL`, timeout applicato al client e zero retry SDK. Normalizza con `model_dump`. Riferimento: `interaction/llm.py:OpenAiResponsesLlmProvider`.

### 6.2 Ollama

**[IMPLEMENTED AND VERIFIED]** `OllamaChatLlmProvider` usa HTTP JSON a `/api/chat`, temperatura 0, `num_ctx` configurabile (default 16384), reasoning `think` opzionale, tool conversion e adapter di streaming verso eventi compatibili col runtime. La modalità JSON schema viene applicata solo nella fase finale senza tool, per non ostacolare il planning. Riferimenti: `llm.py:OllamaChatLlmProvider`, `_OllamaStreamManager`, `_should_send_ollama_json_format`.

### 6.3 Selezione e fallback

**[IMPLEMENTED AND VERIFIED]** Gli endpoint conversazionali ASITA richiedono `LLM_PROVIDER=openai`; `OPENAI_MODEL` e `OPENAI_BASE_URL` sono le sole fonti per modello e URL OpenAI. Ollama resta nel layer provider-neutral per uso non sperimentale, ma viene rifiutato dalle view dello studio. Errori e timeout non attivano fallback. Riferimenti: `llm.py:load_llm_provider_config`, `views.py:_provider_failure_response`.

**[IMPLEMENTED AND VERIFIED]** Il runtime non usa un fallback keyword/rule-based per la chat se il modello fallisce o restituisce output vuoto. Il resolver rule-based resta per la selezione WebGIS strutturata. Test: `test_empty_model_response_never_triggers_a_keyword_fallback`.

## 7. Voce

**[IMPLEMENTED AND VERIFIED]** Flusso STT:

1. verifica MediaRecorder/getUserMedia;
2. scelta MIME tra WebM/Opus, WebM, MP4, OGG/Opus;
3. registrazione, annullamento, “trascrivi” o “trascrivi e invia”;
4. multipart POST con audio e durata;
5. limite backend 12 MiB;
6. OpenAI `audio.transcriptions.create`, modello default `gpt-4o-transcribe`, lingua italiana, response text;
7. transcript nel textarea o invio con `interactionMode=voice`.

Riferimenti: `app.js:initializeVoiceInput`; `api.js:transcribeVoiceMessage`; `views.py:voice_transcribe`; `interaction/voice.py`.

**[IMPLEMENTED AND VERIFIED]** Lo STT richiede sempre `OPENAI_API_KEY`, anche con LLM Ollama. Non usa `SpeechToTextProvider` tramite dependency injection. Riferimenti: `voice.py`; `providers.py`.

**[NOT FOUND / UNCERTAIN]** Nessuna sintesi vocale, riproduzione della risposta, wake word, endpoint audio output, diarizzazione o conservazione intenzionale del file audio. Il file viene letto in memoria e inviato a OpenAI; non è scritto localmente dal codice.

## 8. Streaming

**[IMPLEMENTED AND VERIFIED]** `POST /interact/stream` produce Server-Sent Events tramite `StreamingHttpResponse`:

- `status`;
- `tool_pending`;
- `tool_start`;
- `tool_result`;
- `analysis_result`;
- `message_delta`;
- `done`;
- `error`.

Riferimenti: `views.py:interact_stream`; `orchestrator.py:handle_stream`; `assistant_runtime.py:stream_handle`; `api.js:sendInteractionMessageStream`.

**[IMPLEMENTED AND VERIFIED]** Poiché la risposta finale è JSON, `AssistantTextDeltaExtractor` estrae incrementi dal campo `assistant_text` durante lo stream. I risultati GIS possono arrivare e aggiornare la mappa prima della risposta testuale finale. Riferimenti: `assistant_runtime.py:AssistantTextDeltaExtractor`; `app.js:onAnalysisResult` nel `runAssistantInteraction`.

**[IMPLEMENTED AND VERIFIED]** La sessione è salvata prima dell'evento `done`, così un follow-up immediato del browser vede storico e contesto aggiornati. Riferimento: `views.py:interact_stream` righe 765–769. Test: `test_interact_stream_persists_analysis_before_done_event`.

## 9. Storico, confronti e report

### 9.1 StoredAnalysis

**[IMPLEMENTED AND VERIFIED]** Ogni analisi salvata contiene id UUID abbreviato, source, timestamp UTC, label, kind (`municipalities`, `drawn`, `mixed`, `unknown`), flag geometria disegnata, summary, comuni richiesti/intersecati, selection payload completo, valutazione economica opzionale e metadata allow-listed. Riferimenti: `analysis_store.py:StoredAnalysis`, `create_stored_analysis`.

**[IMPLEMENTED AND VERIFIED]** Lo storico è limitato a 10 record per default, newest-first in lettura; supporta elenco, dettaglio, rename (max 120 caratteri), delete, clear e compare. Riferimenti: `analysis_store.py:analysis_history_limit`, `DjangoSessionAnalysisStore`; `views.py:analysis_history*`; `api.js`.

### 9.2 Confronti

**[IMPLEMENTED AND VERIFIED]** Il confronto deterministico produce:

- record normalizzati;
- ranking per CO₂ totale, ettari e CO₂/ha;
- differenze assolute e percentuali per due analisi;
- vincitore su CO₂ totale e intensità;
- categorie comuni/parziali e breakdown;
- confronto economico per tutti gli scenari.

Riferimento: `services/analysis_compare.py:compare_saved_analyses` e helper.

**[IMPLEMENTED AND VERIFIED]** I selector conversazionali possono essere id, label esatta normalizzata o comune. Zero match genera errore; più match genera ambiguità esplicita. Riferimento: `interaction/tools/analysis_history.py:_resolve_saved_analyses`.

### 9.3 Report e PDF

**[IMPLEMENTED AND VERIFIED]** Il report interattivo è un pannello HTML generato dallo stato client. Include KPI, superficie, categoria prevalente, scenari economici, dettaglio categorie e comandi mappa. Riferimento: `app.js:renderInfoSummary`.

**[IMPLEMENTED AND VERIFIED]** Il PDF è generato interamente nel browser: A4, 4 pagine (executive, vegetazione, economia, metodologia), mappa catturata con timeout di 10 secondi e fallback a report senza immagine. Il risultato è un Blob/object URL, non viene caricato o salvato dal server. Riferimento: `modules/pdf-export.js:generatePdfReport`, `captureMap`, `prepareDocument`.

**[IMPLEMENTED AND VERIFIED]** `prepare_report` non genera né certifica un PDF; restituisce `action: open_existing_report`. L'istruzione di sistema vieta al modello di dichiarare che il PDF è stato generato. Riferimenti: `tools/economic_valuation.py:prepare_analysis_report`; `assistant_runtime.py:_build_instructions`.

## 10. GUI tradizionale vs modalità conversazionale

| Aspetto | GUI WebGIS | Conversazionale |
|---|---|---|
| Definizione area | checkbox comuni + draw/edit/delete | nomi in linguaggio naturale o riferimento alla selezione UI corrente |
| Interpretazione | deterministica, controlli espliciti | LLM |
| GIS | backend GeoPandas condiviso | stesso backend tramite tool |
| Economia | calcolo browser | tool backend con scenario enum |
| Confronto | selezione manuale record | recenti o selector linguistici |
| Report | pannello + generazione PDF browser | tool apre il pannello; PDF resta azione browser separata |
| Voce | non applicabile | STT OpenAI, poi stessa chat |
| Error recovery | messaggi UI | errore tool può tornare al modello per correzione |
| Stato | JS + session history | JS + SessionContext + history sessione |

Tutta la tabella è **[IMPLEMENTED AND VERIFIED]**; riferimenti nelle sezioni precedenti.

## 11. Enforcement delle condizioni sperimentali

**[IMPLEMENTED AND VERIFIED]** Le condizioni ammesse sono `webgis` e `conversational`. Una policy diventa attiva solo durante un task attivo, non semplicemente all'apertura di una sessione studio. Riferimenti: `app.js:getActiveStudyCondition`; `views.py:_active_task_condition`; `experiments/logging.py`.

**[IMPLEMENTED AND VERIFIED]** Enforcement client:

- `webgis`: disabilita/chiude assistente e voce;
- `conversational`: disabilita selezione comuni, analisi GUI, storico GUI, controlli economici e filtri; apre assistente;
- listener capture intercetta click proibiti e registra `protocol_violation`.

Riferimenti: `app.js:applyConditionPolicy`, `blockedProtocolAction`, `initializeConditionControl`; `app.css` righe 232–233.

**[IMPLEMENTED AND VERIFIED]** Enforcement server:

- durante task `webgis`, blocca `/interact`, `/interact/stream`, `/voice/transcribe`;
- durante task `conversational`, blocca `/gis`;
- risponde 403 e registra violazione.

Riferimenti: `views.py:_condition_violation_response`, `gis`, `interact`, `interact_stream`, `voice_transcribe`. Test: `test_webgis_task_blocks_chat...`, `test_conversational_task_blocks_traditional_gis_endpoint_only`.

**[IMPLEMENTED AND VERIFIED — LIMITATION]** Gli endpoint CRUD/confronto dello storico non hanno enforcement server specifico per la condizione conversazionale; sono bloccati nella UI, ma restano invocabili direttamente da un client HTTP autenticato nella stessa sessione. Anche i tool conversazionali possono legittimamente usare lo storico. Riferimenti: `views.py:analysis_history*`.

**[IMPLEMENTED AND VERIFIED]** All'avvio/sostituzione/reset di una sessione studio lo stato operativo (contesto conversazionale e analisi) viene cancellato. Un task precedente attivo viene marcato interrotto. Riferimento: `views.py:study_session`, `_clear_operational_state_for_task`.

## 12. Logging e metriche sperimentali

### 12.1 Log session-scoped

**[IMPLEMENTED AND VERIFIED]** `experiment_events` contiene fino a 500 eventi nella sessione Django. Registra tipi allow-listed per sessione/task, UI, chat, tool, violazioni, selezione, analisi, economia, report, voce, reset ed errori. Campi: timestamp, channel, condition, operation, mode, duration, step count, task/run, status/error e details sanitizzati. Riferimenti: `experiments/logging.py:ALLOWED_EVENT_TYPES`, `record_experiment_event`.

**[IMPLEMENTED AND VERIFIED]** Il log session-scoped omette deliberatamente `user_text`, transcript e risposta assistente dal record in-session, sebbene i parametri vengano accettati per inoltrarli al log persistente. Riferimento: `experiments/logging.py:record_experiment_event` righe 135–188.

### 12.2 Log persistente dello studio

**[IMPLEMENTED AND VERIFIED]** Se esiste `study_context`, lo stesso evento è scritto in `STUDY_LOG_ROOT/<participant>/<session>/events.jsonl`; `summary.json` viene rigenerato a ogni evento. Il log persistente include fino a 5.000 caratteri di user text/transcript e 8.000 di risposta assistente. Riferimento: `experiments/study_logging.py:record_study_event`.

**[IMPLEMENTED AND VERIFIED]** Le metriche aggregate includono task completati e durate server-derived, interazioni, step, errori, unknown, conteggio text/voice, operazioni, report, UI actions, chat, tool, task falliti/interrotti e violazioni. Riferimento: `experiments/logging.py:summarize_experiment_events`.

**[IMPLEMENTED AND VERIFIED]** Il browser registra eventi addizionali (selezione, azioni UI, chat message/response, tool progress, voce, economia e PDF) tramite `/experiment/log`; il backend registra eventi autorevoli per analisi/interazioni/trascrizione. Questo può produrre più eventi per una singola interazione, distinti da `eventSource`. Riferimenti: `app.js:recordExperiment`, `runAssistantInteraction`, `runAnalysis`; `views.py`.

**[IMPLEMENTED AND VERIFIED — TERMINOLOGY/PRIVACY INCONSISTENCY]** README e docstring di `experiments/logging.py` affermano che il logging evita prompt, transcript e testo libero. Ciò è vero per il log session-scoped, ma falso per il log persistente dello studio, che salva userText, userTranscript e assistantResponse. Nel paper bisogna descrivere separatamente i due livelli e la base giuridica/consenso per il testo conversazionale. Riferimenti: `README.md:Logging Sperimentale`; `experiments/logging.py` docstring; `experiments/study_logging.py:record_study_event`.

### 12.3 Archivio studio

**[IMPLEMENTED AND VERIFIED]** L'archivio amministrativo elenca, visualizza, esporta JSON/JSONL ed elimina sessioni non attive. È protetto da password condivisa configurata, token HMAC legato a password e `SECRET_KEY`, confronto constant-time, session key rotation al login e CSRF sulle mutazioni. Se la password non è configurata, fallisce chiuso. Riferimenti: `views.py:_study_admin_*`, `study_admin_*`; test `StudyAdminTests`.

**[NOT FOUND / UNCERTAIN]** Non sono presenti ruoli multipli, audit dell'accesso amministrativo, cifratura applicativa dei log, retention automatica o pseudonimizzazione oltre alla sanitizzazione dell'identificativo immesso.

## 13. Gestione errori e fallback

**[IMPLEMENTED AND VERIFIED]** Principali risposte:

- payload/argomento invalido: HTTP 400 o errore tool recuperabile;
- provider/configurazione/STT non disponibile: HTTP 503;
- feature disabilitata: 404;
- violazione condizione: 403;
- record storico mancante: 404;
- stream: evento `error`.

Riferimenti: `views.py:gis`, `interact`, `interact_stream`, `voice_transcribe`, `analysis_history_detail`; `api.js:handleJsonResponse`.

**[IMPLEMENTED AND VERIFIED]** Il client mostra notice, ripristina busy state, registra timeout/failure e mantiene il testo trascritto editabile. Il PDF degrada senza immagine mappa se la cattura fallisce. Riferimenti: `app.js:runAnalysis`, `runAssistantInteraction`, `initializeVoiceInput`; `pdf-export.js:generatePdfReport`.

**[NOT FOUND / UNCERTAIN]** Non sono presenti retry automatici con backoff, circuit breaker, fallback provider, transazioni distribuite, coda offline o replay idempotente generale. Il logging task ha alcune garanzie di idempotenza per eventi terminali, non per tutte le operazioni.

## 14. Trust boundary e affidabilità

### 14.1 Matrice decisione/esecuzione

| Attività | LLM | Applicazione deterministica |
|---|---:|---:|
| Comprendere la richiesta | sì | no, salvo percorso GUI |
| Disambiguare linguisticamente | sì, assistito da lookup | lookup e ambiguità verificati |
| Scegliere/ordinare tool | sì | limite round e dispatch |
| Validare geometrie/CRS | no | sì |
| Eseguire clip/intersezioni | no | sì |
| Calcolare ettari/CO₂ | no | sì |
| Calcolare prezzi/valori | no | sì |
| Risolvere storico e confrontare | sceglie riferimenti | sì |
| Formulare risposta naturale | sì | schema/whitelist soltanto |
| Aggiornare mappa/UI | propone action | sì, da payload strutturato |
| Generare PDF | no | browser |
| Salvare/reset stato | richiede tool | sì |

**[IMPLEMENTED AND VERIFIED]** La tabella deriva da `assistant_runtime.py`, `tools/*`, `services/*` e `app.js`.

### 14.2 Meccanismi anti-hallucination

**[IMPLEMENTED AND VERIFIED]** Meccanismi presenti:

- istruzione esplicita “numeri GIS solo da tool”;
- tool schema tipizzati e scenario enum;
- validazione backend indipendente;
- geometrie escluse dal contesto del modello;
- payload strutturati separati dal testo;
- UI actions in whitelist sia server sia client;
- selezione corrente distinta dall'ultima analisi;
- filtro vincolato all'id realmente visualizzato;
- nessun reset senza tool realmente eseguito;
- nessun PDF dichiarato dal solo `prepare_report`;
- un errore tool ritorna al modello per recovery.

Riferimenti: `assistant_runtime.py:_build_instructions`, `_build_model_tool_output`, `_build_interaction_response`; `ui_actions.py`; `map_filtering.py`.

**[IMPLEMENTED AND VERIFIED — CRITICAL LIMITATION]** Non esiste un validatore che confronti i numeri citati in `assistant_text` con gli output tool. Il modello riceve dati verificati ma può ancora trascriverli, arrotondarli o interpretarli male. I pannelli strutturati restano ground truth applicativa; il testo naturale non ha la stessa garanzia. Riferimenti: `assistant_runtime.py:_build_interaction_response` accetta `assistant_text`; nessun post-validator numerico trovato.

**[INFERRED FROM IMPLEMENTATION]** Per il paper è quindi corretto affermare “i risultati computazionali sono prodotti deterministicamente e passati al modello per la verbalizzazione”, ma non “ogni affermazione numerica nella risposta testuale è verificata automaticamente”.

## 15. Flussi end-to-end rappresentativi

### Flusso 1 — “Analizza Avellino”

Tutto il flusso è **[IMPLEMENTED AND VERIFIED]**.

1. **Utente** → invia il testo nel pannello assistente.
2. **Interfaccia** → `runAssistantInteraction` allega selected municipalities, extent, selection payload e displayed analysis id; apre SSE.
3. **Backend/orchestrazione** → `interact_stream` crea `InteractionRequest(WEB_CHAT)` e `InteractionOrchestrator` delega ad `AssistantRuntime`.
4. **LLM** → interpreta il nuovo comune; può chiamare `search_municipalities` se ambiguo, poi `analyze_municipalities(["Avellino"])`.
5. **Tool/funzione** → `AssistantToolExecutor` invoca registry → `gis_analysis.analyze_municipalities`.
6. **Processing deterministico** → lookup geometria EPSG:32633 → parsing → reproiezione 4326 → clip Carta Natura → summary CO₂/ettari/categorie.
7. **Stato** → `StoredAnalysis` in session history; `SessionContext.last_analysis` e conversazione aggiornati.
8. **Risposta** → al modello tornano id, comuni e summary (non geometria); il modello produce JSON finale con testo italiano.
9. **UI/mappa** → evento `analysis_result` applica subito clipped GeoJSON, contorni, KPI e report; `done` finalizza il messaggio e le UI actions.

Riferimenti: `app.js:runAssistantInteraction`; `views.py:interact_stream`; `assistant_runtime.py:stream_handle`; `tools/gis_analysis.py`; `services/municipality_text.py`; `services/gis_clip.py`; `services/analysis_summary.py`; `app.js:applyAnalysisResult`.

### Flusso 2 — “Confrontalo con il precedente”

Tutto il flusso è **[IMPLEMENTED AND VERIFIED]**, assumendo almeno due analisi in sessione.

1. **Utente** → usa riferimento anaforico al risultato corrente/precedente.
2. **Interfaccia** → invia messaggio, displayed analysis id e contesto UI.
3. **Backend/orchestrazione** → carica `SessionContext` e `DjangoSessionAnalysisStore`.
4. **LLM** → usa conversazione recente e regole di grounding; sceglie `compare_recent_analyses(recent_count=2)`.
5. **Tool/funzione** → recupera le ultime due analisi newest-first.
6. **Processing deterministico** → normalizza record, calcola ranking, differenze, categorie ed economia.
7. **Stato** → non crea una nuova analisi; preserva ultima analisi e aggiorna last intent/conversation.
8. **Risposta** → il modello verbalizza il confronto usando il payload tool.
9. **UI/mappa** → `analysisResult.analyses` viene instradato al pannello storico/confronto; la mappa esistente non viene ricalcolata.

Fallback verificato: con meno di due analisi il tool restituisce errore al modello, che deve chiedere/indicare la condizione mancante. Riferimenti: `tools/analysis_history.py:compare_recent_analyses`; `services/analysis_compare.py`; `app.js:routeStructuredAssistantResult`; test `test_orchestrator_compares_recent_analyses`.

### Flusso 3 — voce: “Analizza Salerno e mostrami solo i castagneti”

Tutto il flusso è **[IMPLEMENTED AND VERIFIED]** come composizione supportata; la riuscita STT/provider reale dipende dai servizi esterni.

1. **Utente** → registra e sceglie “Trascrivi e invia”.
2. **Interfaccia/voce** → MediaRecorder crea Blob; `/voice/transcribe` invia a OpenAI STT; transcript ritorna e viene inviato con mode `voice`.
3. **Backend/orchestrazione** → normale SSE assistant runtime.
4. **LLM** → pianifica `analyze_municipalities(["Salerno"])`, poi, dopo il risultato, `filter_last_analysis_categories(["castagneti"], false)`.
5. **Tool analisi** → pipeline GIS deterministica e salvataggio.
6. **Stato intra-turno** → `_advance_tool_context` imposta la nuova analisi come displayed e rimuove la selezione corrente, permettendo al filtro di riferirsi alla nuova analisi.
7. **Tool filtro** → verifica id visualizzato, presenza e univocità della categoria; restituisce solo key/label.
8. **Risposta** → il modello spiega analisi e filtro; output resta testuale, senza TTS.
9. **UI/mappa** → prima mostra l'intero risultato dall'evento `analysis_result`, poi filtra le feature locali per `CODICE`; report e KPI restano completi.

Riferimenti: `app.js:initializeVoiceInput`, `runAssistantInteraction`, `applyAssistantMapFilter`; `voice.py`; `assistant_runtime.py:_advance_tool_context`; `tools/map_filtering.py`; test `test_analysis_then_filter_uses_analysis_created_in_this_turn`.

### Flusso 4 — GUI tradizionale con area mista e PDF

Tutto il flusso è **[IMPLEMENTED AND VERIFIED]**.

1. **Utente** → seleziona comuni e disegna/modifica poligono o rettangolo.
2. **Interfaccia** → costruisce due aree (`municipalities`, `drawn`) e POST `/gis`.
3. **Backend** → percorso rule-based senza LLM; validazione, clip, summary, salvataggio.
4. **UI/mappa** → rendering risultati e apertura report.
5. **Utente** → seleziona prezzo e calcola; JavaScript moltiplica totalCo2 × prezzo.
6. **Utente** → genera PDF; jsPDF impagina quattro pagine, tenta cattura mappa e offre Blob da scaricare.
7. **Logging** → eventi analisi, valutazione e report con durata e dettagli sanitizzati.

Riferimenti: `map-controller.js`; `app.js:buildAnalysisPayload`, `runAnalysis`, `renderInfoSummary`; `views.py:gis`; `pdf-export.js`.

## 16. Incoerenze di nomi e concetti

### Terminologia consigliata per il paper

**[IMPLEMENTED AND VERIFIED]** Usare:

- “web application monolitica Django con client WebGIS Leaflet”, non microservizi;
- “LLM-mediated tool orchestration” o “interfaccia conversazionale tool-augmented”, non “LLM che esegue analisi GIS”;
- “risultati GIS deterministici verbalizzati dall'LLM”;
- “stima annuale di CO₂ basata su coefficienti per categoria”, evitando “misurazione”;
- “session-scoped analysis history”, non database permanente delle analisi;
- “voice input via STT”, non assistente vocale bidirezionale;
- “apertura/preparazione del report” per `prepare_report`; “generazione PDF client-side” solo dopo l'azione jsPDF;
- “map-only category filter”, non nuova analisi filtrata;
- “OpenAI remoto / Ollama self-hosted o locale”, perché Ollama è configurato via URL e non necessariamente sullo stesso host.

### Incoerenze trovate

**[IMPLEMENTED AND VERIFIED]** L'enum `InteractionIntent` comprende `EXTRACT_FOREST_INFORMATION`, `ESTIMATE_CO2_SEQUESTRATION`, `GENERATE_REPORT` ecc., ma molti non corrispondono a pipeline computazionali separate: sono classificazioni semantiche finali sopra gli stessi tool. Riferimento: `interaction/models.py:InteractionIntent`; `assistant_runtime.py`.

**[IMPLEMENTED AND VERIFIED]** I nomi “last analysis”, “displayed analysis” e “current selection” sono talvolta colloquialmente sovrapposti nell'UI/documentazione, ma il runtime li tratta correttamente come tre contesti distinti. Nel paper vanno definiti separatamente. Riferimenti: `_build_user_prompt`; `map_filtering.py`.

**[IMPLEMENTED AND VERIFIED]** La documentazione descrive un pilot con due incarichi estesi, mentre `STUDY_TASKS` espone sei task T1–T6. L'implementazione runtime attuale usa sei task. Riferimenti: `README.md:Pilot ASITA 2026`; `views.py:STUDY_TASKS`.

**[IMPLEMENTED AND VERIFIED]** La privacy del logging è descritta in modo assoluto nei documenti, ma differisce tra log sessione (senza testo) e log persistente (con testo). Vedi §12.

**[IMPLEMENTED AND VERIFIED]** Esistono `SpeechToTextProvider` e `TextToSpeechProvider` come astrazioni, ma il codice voce concreto chiama direttamente OpenAI e non esiste TTS. Non descriverli come provider abstraction implementata per la voce. Riferimenti: `providers.py`; `voice.py`.

## 17. Limitazioni tecniche attuali

### Verificate

- **Area post-clip non ricalcolata**: possibile sovrastima di ettari e CO₂ su intersezioni parziali (§4.4).
- **Quattro codici non riconosciuti per differenza maiuscole/minuscole**: sottostima delle categorie coinvolte e dei totali (§4.4).
- **Testo LLM non numericamente post-validato**: ground truth solo nei payload/pannelli strutturati (§14.2).
- **Persistenza session-scoped**: storico limitato e legato alla sessione, nessun modello dominio DB.
- **SQLite + filesystem locale**: topologia single-instance; consistenza/retention multi-replica non progettata.
- **STT solo OpenAI**: chiave esterna richiesta anche con LLM Ollama.
- **Nessun TTS**.
- **Nessun fallback LLM automatico**.
- **Valutazione GUI non persistita nello storico**, a differenza del tool conversazionale.
- **`prepare_report` non genera PDF**; in condizione conversazionale i controlli manuali economici sono disabilitati, quindi una richiesta solo “apri report” senza precedente valutazione non produce un PDF pronto.
- **Validazione parziale dei nomi multipli**: i nomi non validi possono essere ignorati se almeno uno è valido.
- **Contesto breve**: massimo 16 messaggi conservati, 8 incorporati nel prompt di grounding.
- **Dataset caricati interamente e cached in-process**: nessun indice spaziale persistente o servizio tile/vector.
- **Dipendenze frontend esterne**: tile/font/Bootstrap/jsPDF possono fallire offline.
- **Enforcement storico prevalentemente UI** nella condizione conversazionale.
- **Log persistente contiene conversazioni**, con implicazioni privacy/retention.

Riferimenti sono riportati nelle sezioni tematiche.

### Non determinabili dal repository

- accuratezza empirica del modello per intent/tool selection;
- latency, throughput, costi e failure rate in deployment reale;
- qualità STT con accenti/rumore;
- compatibilità effettiva dei diversi modelli Ollama con tool calling e JSON schema;
- validità scientifica e provenienza dei coefficienti;
- copertura/aggiornamento/licenza operativa dei dataset oltre ai file inclusi;
- accessibilità/usabilità validate con utenti;
- strategia di consenso e retention dei testi dello studio.

## A. Architecture Inventory

Tutti gli elementi sono **[IMPLEMENTED AND VERIFIED]**.

1. **Django project (`progettoGIS`)** — config, URL root, sessioni, SQLite, statici, security/deployment.
2. **Django app/views** — API JSON/SSE, pagina, voice, study e admin.
3. **Leaflet WebGIS** — selezioni comunali, disegno, layer risultati, contorni, basemap.
4. **Client state/controller** — stato analisi, economia, storico, assistente e studio.
5. **GIS datasets** — Carta Natura e due rappresentazioni confini comunali.
6. **Payload validation** — kind, FeatureCollection, CRS, geometrie.
7. **GIS processing** — reproiezione e clip GeoPandas.
8. **Analytical summary** — ettari, categorie, CO₂ e prevalenza.
9. **Economic domain** — quattro scenari e moltiplicazione.
10. **InteractionOrchestrator** — separazione GUI strutturata/chat LLM.
11. **AssistantRuntime** — prompt, tool loop, streaming, structured output.
12. **Provider adapters** — OpenAI Responses e Ollama Chat.
13. **Tool registry/executor** — dispatch controllato verso funzioni deterministiche.
14. **SessionContext store** — continuità conversazionale.
15. **Analysis history store** — analisi, geometry payload e valutazione opzionale.
16. **Comparison service** — ranking/differenze/categorie/economia.
17. **Voice pipeline** — MediaRecorder + OpenAI STT.
18. **Report UI/PDF** — pannello HTML + PDF browser-side.
19. **Experiment logger** — eventi session-scoped e metriche.
20. **Persistent study logger/admin** — JSONL/summary, export e gestione protetta.
21. **Experimental policy** — blocco client e server delle azioni fuori condizione.

## B. Conversational Capability Inventory

Tutte sono **[IMPLEMENTED AND VERIFIED]** come tool/capability, non necessariamente come successo garantito per ogni formulazione naturale:

- cercare/disambiguare comuni;
- analizzare uno o più comuni congiuntamente;
- analizzare separatamente più comuni tramite più chiamate;
- analizzare la selezione corrente presente nella UI;
- descrivere categorie, superficie e CO₂ di una nuova/ultima analisi;
- mostrare solo categorie richieste sulla mappa o ripristinarle tutte;
- calcolare il valore economico con uno dei quattro scenari;
- confrontare tutti gli scenari economici;
- recuperare/spiegare l'ultima analisi;
- elencare analisi recenti;
- confrontare ultime N analisi;
- confrontare analisi salvate per id, label o comune;
- spiegare la metodologia statica;
- aprire il report esistente;
- resettare contesto e storico;
- comporre più operazioni nello stesso turno, per esempio analisi → economia → report o analisi separate → confronto;
- proporre apertura report, legenda, focus risultati e mostra ultima analisi tramite UI actions.

**[NOT FOUND / UNCERTAIN]** Non risultano tool per editing geometrico via linguaggio, buffer/distanze, routing, query libere sugli attributi, geocoding indirizzi, upload dataset, modifica coefficienti/prezzi, salvataggio nominativo persistente cross-session, invio report o TTS.

## C. Technology Inventory

Vedi §3. Sintesi paper-relevant: Django, GeoPandas/Pandas/Shapely, SQLite/Django sessions, Leaflet/Leaflet Draw, JavaScript ES modules, OpenAI Responses API, Ollama Chat API, OpenAI Audio Transcriptions, SSE, jsPDF/dom-to-image, JSONL study logs, Gunicorn/WhiteNoise/Docker.

## D. End-to-End Interaction Flows

Vedi §15:

1. analisi conversazionale di un comune;
2. confronto contestuale con analisi precedente;
3. richiesta vocale multi-tool con aggiornamento risultati e filtro mappa;
4. percorso GUI tradizionale con area mista, economia e PDF.

## E. Architecture Diagram Specification

Diagramma consigliato, da sinistra a destra, con quattro gruppi.

### Gruppo 1 — User and Browser

Nodi:

- User;
- Traditional WebGIS controls;
- Conversational panel;
- Voice recorder;
- Leaflet map;
- Client state/report/history UI;
- Client-side PDF generator.

Frecce:

- User → GUI controls: municipality/drawn selection;
- User → conversational panel: natural-language text;
- User → voice recorder: audio;
- Voice recorder → Django Voice API: audio multipart;
- GUI controls → Django GIS API: selection GeoJSON + CRS convention;
- Conversational panel → Django Interaction API: message + UI context;
- Django API → client state/map: structured results/SSE;
- client state → PDF generator: summary + economic data + map snapshot;
- PDF generator → User: local Blob/download.

### Gruppo 2 — Django Application

Nodi:

- HTTP Views/API Gateway;
- InteractionOrchestrator;
- AssistantRuntime;
- Tool Registry/Executor;
- deterministic GIS services;
- economic/comparison/history services;
- session stores;
- experiment/study logging.

Frecce:

- GIS API → Orchestrator direct structured path;
- Interaction API → Orchestrator → AssistantRuntime;
- AssistantRuntime ↔ LLM Provider: instructions, context, tool calls, structured final text;
- AssistantRuntime → Tool Registry: validated dispatch;
- tools → deterministic services: typed arguments;
- services → tools: verified summaries/results;
- tools ↔ session stores: analysis/context persistence;
- views/client events → logging: controlled events and metrics.

### Gruppo 3 — Data

Nodi:

- Carta Natura shapefile;
- municipality GeoJSON EPSG:32633;
- municipality boundaries EPSG:4326;
- SQLite session DB;
- study-log filesystem JSONL/JSON.

Frecce:

- geographic datasets → GIS/lookup services;
- session stores ↔ SQLite;
- study logger → filesystem;
- admin archive ← filesystem.

### Gruppo 4 — External AI and map services

Nodi:

- OpenAI Responses API;
- Ollama Chat API (alternative, explicitly selected);
- OpenAI Transcription API;
- OpenStreetMap tiles.

Frecce:

- AssistantRuntime ↔ one selected LLM adapter;
- Voice API → OpenAI Transcription → transcript;
- Leaflet map ← OSM tiles.

Visual distinction essential:

- blue/dashed arrows for model-mediated semantic decisions;
- solid green arrows for deterministic data processing;
- red trust-boundary line between LLM provider and application;
- geometry must flow only browser ↔ backend GIS ↔ browser, never to the LLM;
- mark `assistant_text` as generated, and map/report values as structured deterministic outputs.

## F. Scientific Design Decisions

1. **Shared deterministic core across modalities** — GUI and conversation converge on the same GIS functions, enabling comparison of interaction modality while keeping computation stable.
2. **LLM as semantic orchestrator, not calculator** — appropriate separation for reliable Human–GIS Interaction.
3. **Structured UI side channel** — conversational output contains machine-readable analysis/economy/filter/report payloads in addition to prose.
4. **Explicit spatial context model** — current selection, displayed analysis and last analysis are distinct, reducing anaphora/stale-context errors.
5. **Tool chaining for compound goals** — one utterance may produce several verified operations.
6. **Geometry minimization in model context** — full clipped geometry stays outside the LLM, reducing token load and preventing geometry fabrication.
7. **Reversible visualization commands** — category filtering affects map only, preserving analytical scope and KPI integrity.
8. **Dual experimental enforcement** — UI affordance restriction plus server-side denial for core cross-condition actions.
9. **Instrumented multimodality** — text/voice/channel/tool events are differentiated for study analysis.
10. **Provider-neutral core with asymmetric voice dependency** — OpenAI/Ollama abstraction for LLM, but OpenAI-only STT.
11. **Explicit cross-turn memory** — application-controlled compact context instead of opaque provider thread continuity.
12. **Progressive streaming of operational effects** — map can update before prose completes, potentially improving perceived latency and observability.

## G. Implementation Details Probably Not Relevant to the Paper

- asset cache-busting via maximum file mtime;
- exact CSS classes, icons, panel resizing and local width persistence;
- exact admin template layout;
- UUID truncation length for ids;
- low-level SSE buffer parsing;
- named PDF palette colors and drawing coordinates;
- exact Gunicorn thread/timeout defaults, unless reporting deployment reproducibility;
- HMAC label string and redirect sanitization details;
- vendor image paths and favicon assets;
- detailed Italian error copy;
- compatibility adapter class names such as `_Event`, `_ResponseRef`, `_FinalResponse`.

## H. Open Questions

1. Qual è la fonte bibliografica e l'unità esatta dei coefficienti CO₂ per categoria?
2. `ettari` rappresenta l'area dell'intero poligono sorgente? Se sì, il mancato ricalcolo post-clip è noto e accettato o è un bug da correggere prima dello studio?
3. I quattro mismatch di case nei codici vegetazionali devono essere corretti prima della produzione dei risultati sperimentali e ricalcolati retroattivamente?
4. Qual è anno/versione/licenza dei tre dataset e come sono stati preprocessati `CNPulita` e `moddedCampania`?
5. Gli 81 comuni esclusi derivano da verifica dataset o da una regola esterna?
6. Il pilot effettivo usa sei task T1–T6 o due incarichi estesi descritti nella documentazione?
7. I testi completi delle conversazioni devono essere conservati nello studio? Quali consenso, retention e access policy si applicano?
8. Il pin `gpt-5-mini` deve essere sostituito con uno snapshot datato, se OpenAI ne rende disponibile uno compatibile con Responses e con i tool richiesti?
9. È accettabile l'assenza di temperature/seed configurabili per il modello OpenAI scelto, documentando modello e data delle sessioni?
11. Il PDF è un deliverable sperimentale obbligatorio in modalità conversazionale? Se sì, come deve completarsi quando manca una valutazione economica persistita?
12. La valutazione economica GUI deve essere salvata nello storico per parità tra condizioni?
13. Quali metriche derivate saranno usate nell'analisi statistica e come verranno deduplicati eventi frontend/backend della stessa azione?
14. Quali requisiti di deployment concorrente/backup/retention valgono per SQLite e log locali?

## I. Candidate Material for the Paper

### System Design

Inserire:

- architettura a quattro gruppi del §E;
- shared deterministic GIS core;
- trust boundary LLM/applicazione;
- contratti di contesto (selection/displayed/last/history);
- tool inventory raggruppato per GIS, history, economy, report e methodology;
- provider abstraction OpenAI/Ollama e streaming;
- structured UI updates e map-only filtering;
- STT pipeline, specificando assenza TTS;
- session-scoped state e history;
- pipeline GIS/CO₂, ma solo dopo aver risolto la questione area post-clip.

### Experimental methodology

Inserire:

- definizione operativa delle condizioni `webgis` e `conversational`;
- meccanismo di enforcement client/server;
- task lifecycle e reset tra condizioni;
- eventi/metriche raccolti, correlazione `taskRunId` e derivazione server-side della durata;
- distinzione input text/voice;
- modello/provider/versione effettivamente congelati per lo studio;
- privacy/consenso/retention per i log testuali.

### Implementation section or reproducibility appendix

Inserire:

- versioni stack e deployment container;
- formati dataset e CRS;
- schema dei tool e output finale;
- limite storico e contesto conversazionale;
- dettagli PDF client-side;
- configurazione provider e assenza di fallback;
- suite: 122 test superati nello stato auditato.

### Discussion/limitations

Inserire:

- possibile errore di area dovuto all'attributo `ettari` non ricalcolato;
- esclusione di quattro codici vegetazionali per mismatch case-sensitive;
- verbalizzazione LLM non post-validata numericamente;
- dipendenza OpenAI per STT;
- no TTS;
- persistenza session-scoped/SQLite;
- dipendenze remote della UI;
- validità/provenienza dei coefficienti;
- possibile differenza di persistenza/calcolo economico tra condizioni;
- generalizzabilità limitata a operazioni e dataset toolizzati.

### Da non presentare come fatto finché non confermato

- accuratezza dei risultati CO₂;
- equivalenza metrica perfetta tra GUI e conversazione sulle valutazioni salvate;
- “assistente vocale” bidirezionale;
- generazione PDF da parte dell'LLM/backend;
- verifica automatica di ogni numero nel testo;
- deployment scalabile/multiutente persistente oltre le sessioni Django;
- provenienza scientifica dei coefficienti o aggiornamento dei dataset.

## Conclusione dell'audit

**[IMPLEMENTED AND VERIFIED]** Il design implementato è coerente con un WebGIS deterministico esteso da un livello conversazionale LLM che orchestra funzioni applicative. La scelta scientificamente più forte è il mantenimento del calcolo GIS/economico fuori dal modello e l'uso di output strutturati per aggiornare mappa e report. Tre cautele centrali sono però sostanziali: (1) la superficie post-clip non è ricalcolata dalla geometria risultante; (2) quattro codici del dataset non vengono riconosciuti per differenze di maiuscole/minuscole; (3) la verbalizzazione numerica del modello è grounded ma non verificata automaticamente. Devono essere risolte o dichiarate esplicitamente prima di formulare claim di accuratezza nel paper.

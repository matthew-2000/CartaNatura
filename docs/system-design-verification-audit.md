# Carta Natura — Independent Verification Audit

> **Documento storico pre-correzione.** Questo audit descrive lo stato `5277531` e ha motivato la milestone GIS del 4 settembre 2026. F01, F02, F18 e F19 sono stati successivamente affrontati nel codice; le tabelle diagnostiche non sono la baseline ufficiale. Per i valori post-correzione usare [`asita-2026-gis-baseline.md`](asita-2026-gis-baseline.md).

Data dell'audit: **4 settembre 2026**  
Revisione verificata: **`5277531`**  
Oggetto: repository locale, dossier precedente, task sheet ASITA v0.5, protocollo e feasibility check.  
Vincolo: **nessuna modifica al software**. Le elaborazioni riportate sotto sono diagnostiche e non sostituiscono la validazione scientifica dei dataset o dei coefficienti.

## Executive verdict

Il dossier precedente ricostruisce bene l'architettura, ma era troppo prudente sui due difetti GIS principali e troppo ottimista sulla prontezza del logging. Il secondo audit stabilisce che:

1. l'uso di `ettari` dopo il clipping è un **errore confermato e materialmente grave**, non una mera limitazione possibile;
2. il mismatch maiuscole/minuscole dei codici è **confermato** e altera categorie, colori, superfici e CO2;
3. GUI e conversational, quando ricevono la stessa geometria comunale, convergono davvero nella stessa pipeline deterministica e restituiscono lo stesso summary; tuttavia convergono anche negli stessi errori;
4. i payload strutturati e i pannelli UI sono coerenti nel percorso normale, mentre la verbalizzazione LLM non è verificata numericamente;
5. la formula economica è equivalente tra frontend e backend, ma la persistenza è asimmetrica e tutti i valori economici ereditano l'errore CO2;
6. il flusso report/PDF funziona soltanto nello stato browser corrente; `prepare_report` non genera il PDF e non ricostruisce un report dopo reload;
7. il logging persistente duplica testi ed eventi, denomina come “interazioni” conteggi di eventi e classifica come completati alcuni tool falliti ma recuperati;
8. l'enforcement delle condizioni è forte sui percorsi principali, ma non è totale su tutti gli endpoint e il catalogo task non identifica inequivocabilmente il protocollo v0.5;
9. voice significa input STT, non output vocale; con Ollama il percorso voce continua a dipendere da OpenAI;
10. OpenAI e Ollama non sono condizioni tecnicamente equivalenti. Provider, modello e configurazione devono essere congelati prima della raccolta.

**Valutazione complessiva:** il sistema non è pronto per raccogliere dati ASITA 2026 finché non sono corretti almeno area post-clip e codici vegetazionali e finché non vengono rigenerate le baseline. La suite attuale passa (**122 test**), ma non protegge la semantica geografica che oggi è errata.

## Metodo e criteri

L'audit ha riletto direttamente servizi GIS, dominio, tool, runtime LLM, viste HTTP, stato frontend, PDF, history, enforcement e logging. Sono state inoltre eseguite:

- ispezione diretta dei codici e delle geometrie nei dataset;
- esecuzione reale di `analyze_municipalities` e `analyze_selection` sulla stessa area;
- ricalcolo diagnostico dell'area delle geometrie ritagliate in EPSG:32633;
- ricalcolo diagnostico case-insensitive delle categorie;
- simulazione dei contatori di logging;
- suite Django completa: **122 test superati**.

Le severità significano:

- **BLOCKER FOR EXPERIMENT**: può invalidare direttamente misure o risposte richieste dai task;
- **SHOULD FIX BEFORE EXPERIMENT**: rischio concreto per affidabilità, tracciamento o comparabilità della raccolta;
- **SHOULD FIX BEFORE PAPER**: il sistema può essere pilotato, ma claim o riproducibilità restano inaccettabili;
- **ACCEPTABLE LIMITATION**: limite gestibile se congelato nel protocollo e dichiarato;
- **DOCUMENTATION ONLY**: implementazione utilizzabile, ma descrizione da correggere.

## Verifica quantitativa della pipeline GIS

### Prova dell'errore `ettari`

`geopandas.clip` modifica la geometria ma conserva gli attributi del poligono sorgente. Il summary usa poi direttamente `row["ettari"]`. Il confronto sull'intero layer mostra che `ettari` coincide quasi esattamente con l'area del **poligono sorgente**: errore relativo mediano `1,41e-12`; somma attributo `382.990,5206295639 ha`, somma geometrica `382.990,5206295268 ha`. È quindi provato che non è un peso già adattato alla porzione ritagliata.

Per i comuni usati o già verificati nei materiali ASITA:

| Comune | Summary corrente, ha | Area geometrica post-clip dei codici oggi riconosciuti, ha | Summary corrente CO2, t/anno |
|---|---:|---:|---:|
| Benevento | 4.274,73 | 790,42 | 14.106,62 |
| Montella | 25.234,61 | 4.473,79 | 211.537,82 |
| Avellino | 6.985,39 | 66,97 | 43.508,04 |
| Salerno | 2.953,73 | 1.597,94 | 14.846,69 |
| Caserta | 1.574,31 | 1.034,83 | 6.005,74 |
| Serino | 8.788,16 | 2.428,70 | 73.300,12 |

La seconda colonna geometrica esclude ancora i quattro codici non riconosciuti; non è dunque una nuova baseline finale. Dimostra però che i numeri correnti non misurano la superficie ritagliata.

### Prova del mismatch dei codici

Codici presenti solo nel dataset: `41.B`, `41.C1`, `41.Lcn`, `44.D2cn`.  
Codici presenti solo nella configurazione: `41.b`, `41.c1`, `41.lcn`, `44.d2cn`.

Sono interessate **615 feature** con `13.900,847051 ha` di attributo sorgente. Con un ricalcolo diagnostico che applica entrambe le correzioni — area della geometria ritagliata e lookup case-insensitive — si ottiene:

| Comune | Categorie correnti | Categorie diagnostiche | Prevalente corrente | Prevalente diagnostica | Area diagnostica, ha | CO2 diagnostica, t/anno |
|---|---:|---:|---|---|---:|---:|
| Benevento | 2 | 3 | Querceti | Querceti | 805,44 | 2.795,85 |
| Montella | 7 | 8 | Faggete | Faggete | 4.477,97 | 32.560,57 |
| Avellino | 3 | 3 | Castagneti | Castagneti | 66,97 | 338,51 |
| Salerno | 6 | 7 | Leccete | Leccete | 1.651,61 | 8.071,15 |
| Caserta | 2 | 3 | Querceti | Querceti | 1.070,29 | 4.476,63 |
| Serino | 6 | 6 | Faggete | Castagneti | 2.428,70 | 15.371,00 |

Questi valori sono risultati di audit, non valori da pubblicare: dopo la correzione occorre rigenerarli nel prodotto, validare l'unità dei coefficienti e fissare una baseline versionata. È già certo, però, che i riferimenti numerici di `asita-2026-feasibility-check.md` e ogni dato prodotto dalla pipeline corrente possono cambiare in modo sostanziale.

## Equivalenza GUI vs conversational

### Conclusione esplicita

Per una stessa selezione di comuni e gli stessi parametri, **sì**: i due canali raggiungono la stessa pipeline deterministica per geometria, summary e CO2.

Il percorso GUI invia il `selectionPayload` a `analyze_selection`; il percorso conversazionale risolve i nomi sullo stesso dataset comunale e chiama `analyze_municipalities`. Entrambi convergono in `_build_analysis_result`, che esegue `parse_selection_payload -> clip_selection -> summarize_clipped_features`. Una prova diretta su Benevento, Montella, Avellino, Salerno, Caserta e Serino ha prodotto uguaglianza esatta dei dizionari `summary` tra i due tool.

| Valore | Equivalenza computazionale | Eccezioni |
|---|---|---|
| Superficie | Sì, stesso summary backend | È identicamente errata finché usa `ettari` sorgente; aree disegnate non sono creabili via tool conversazionale durante la condizione controllata |
| Categorie | Sì, stesso mapping backend nel percorso normale | Entrambi omettono i quattro codici; mappa e filtro usano lo stesso lookup case-sensitive; fallback JS duplicato |
| CO2 | Sì, stessi coefficienti e stessa aggregazione | Entrambi ereditano area e codici errati; la frase LLM può divergere dal payload |
| Valore economico | Sì, `totalCo2 * prezzo` con le stesse quattro opzioni | GUI calcola in JS e non persiste; conversational calcola nel backend e persiste; l'arrotondamento è solo di visualizzazione |

### Eccezioni operative alla parità

1. La GUI può combinare comuni e geometrie disegnate; il conversational non possiede un tool per creare un disegno equivalente.
2. `analyze_current_selection` può riusare soltanto una selezione UI realmente corrente. All'avvio della sessione/task lo stato viene resettato e nella condizione conversational i controlli di selezione sono bloccati.
3. La GUI usa normalmente il summary backend. Se questo manca, il fallback JavaScript ricalcola con la stessa logica difettosa; il fallback non restituisce `topCategory`, poi ricavata dalla UI.
4. Le geometrie con codice non riconosciuto restano nel GeoJSON e appaiono grigie, ma non contribuiscono a categorie, ettari o CO2.
5. Il testo LLM è un canale non deterministico separato: nessun controllo impone che i numeri verbalizzati coincidano col payload.
6. Il valore GUI non viene salvato nel record storico; quello conversazionale sì. I PDF nello stesso flusso corrente possono essere uguali, ma il recupero successivo non è equivalente.

## Registro dei finding

### F01 — Area sorgente riutilizzata dopo il clipping

**Classificazione: BLOCKER FOR EXPERIMENT**

- **Comportamento attuale:** ogni frammento ritagliato conserva gli ettari dell'intero poligono sorgente; superficie, CO2, CO2/ha, confronti e valori economici risultano falsati.
- **Evidenza:** `cartaNatura/services/gis_clip.py:67-71` effettua il clip; `cartaNatura/services/analysis_summary.py:17-27` legge ancora `ettari`. Il test fixture in `cartaNatura/tests.py:586-595` usa deliberatamente un attributo non aggiornato ma non asserisce il ricalcolo post-clip.
- **Impatto scientifico:** diretto e alto; altera le variabili oggettive chieste nei task e può cambiare differenze tra comuni.
- **Comparabilità GUI/conversational:** i canali sono coerenti fra loro ma condividono lo stesso errore. Questa simmetria non salva la validità del task.
- **Dati già prodotti:** sì; reference answer, log con `totalCo2`/`totalValueEur`, screenshot e PDF correnti vanno considerati contaminati e rigenerati.
- **Azione:** correzione software obbligatoria, decisione esplicita su CRS/metodo di area, nuova baseline e descrizione metodologica aggiornata.

### F02 — Lookup case-sensitive dei codici vegetazionali

**Classificazione: BLOCKER FOR EXPERIMENT**

- **Comportamento attuale:** quattro codici reali non trovano una categoria, non entrano nei totali e sono resi grigi in mappa.
- **Evidenza:** `domain/vegetation.py:25-101`, `analysis_summary.py:18-23`, `static/js/modules/analysis.js:6-13`, `map-controller.js:217-229`; verifica dataset 615 feature interessate.
- **Impatto scientifico:** altera numero delle categorie, composizione, superficie, CO2 e talvolta la prevalente. Colpisce direttamente T1 e T2.
- **Comparabilità:** stesso errore nei due canali, ma la verifica mappa/legenda di T1 diventa internamente incoerente: una geometria esiste ma non è associata al colore atteso.
- **Dati già prodotti:** sì; almeno le baseline dei comuni elencati devono essere rigenerate.
- **Azione:** correzione software/dati e test di copertura che ogni codice del dataset abbia una policy esplicita; non basta una nota nel paper.

### F03 — Nessuna verifica numerica della verbalizzazione LLM

**Classificazione: SHOULD FIX BEFORE EXPERIMENT**

- **Comportamento attuale:** il modello riceve output tool strutturati e istruzioni di non inventare, ma `assistant_text` viene accettato senza confronto con summary, scenario o comparison.
- **Evidenza:** istruzioni in `assistant_runtime.py:1377-1423`; costruzione della risposta senza validatore numerico; payload strutturato applicato separatamente dal client in `app.js:2848-2864`.
- **Impatto scientifico:** il partecipante può trascrivere dalla chat un numero diverso da quello del pannello; il rischio riguarda accuratezza, errori e tempo di correzione.
- **Comparabilità:** asimmetria sostanziale, perché la GUI legge direttamente dati strutturati mentre la condizione conversational espone anche prosa generativa come veicolo primario.
- **Dati già prodotti:** potenzialmente; occorre verificare i transcript già raccolti contro i payload/eventi.
- **Azione:** software se la risposta testuale è parte del risultato valutato; al minimo scoring/protocollo deve dichiarare il pannello strutturato come fonte autorevole e prevedere un controllo automatico o post-hoc.

### F04 — Formula economica equivalente, persistenza non equivalente

**Classificazione: SHOULD FIX BEFORE PAPER**

- **Comportamento attuale:** entrambi calcolano `totalCo2 * prezzo`; la GUI conserva il risultato solo nello stato JS, il tool conversational aggiorna `StoredAnalysis.economic_valuation`.
- **Evidenza:** `static/js/modules/analysis.js:63-76`, `app.js:2350-2375`; `interaction/tools/economic_valuation.py:37-55`.
- **Impatto scientifico:** nessuno sul valore calcolato nello stesso stato browser, ma può influire su recupero, report successivi e comportamento dopo navigazione/reload.
- **Comparabilità:** equivalenza numerica sì; equivalenza dello stato no.
- **Dati già prodotti:** i valori già prodotti ereditano F01/F02; la sola asimmetria di persistenza non ne cambia il numero originario.
- **Azione:** o uniformare la persistenza prima di sostenere equivalenza completa, oppure limitare il claim nel paper a formula e flusso ininterrotto.

### F05 — Report legato allo stato browser corrente

**Classificazione: ACCEPTABLE LIMITATION**

- **Comportamento attuale:** `prepare_report` restituisce id, area, CO2 e valutazione e ordina di aprire il report esistente; non restituisce geometria/summary completi. Dopo reload, history e last analysis possono esistere ma il pannello/PDF non sono ricostruibili da quei soli tool.
- **Evidenza:** `economic_valuation.py:74-86`; `app.js:1886-1924`; history serializza summary ma l'UI offre confronto/rinomina/elimina, non riapertura (`analysis-history.js:135-170`).
- **Impatto scientifico:** rischio operativo se un task viene interrotto da reload; non altera un flusso T2 ininterrotto.
- **Comparabilità:** il limite colpisce entrambi, ma il conversational può dare l'impressione di avere “preparato” qualcosa che il browser non può ricostruire.
- **Dati già prodotti:** no, salvo sessioni con reload interpretate come successi.
- **Azione:** non serve redesign per il pilot se il protocollo vieta/gestisce reload; correggere la frase UI “pronte per essere riaperte” e descrivere il limite nel paper.

### F06 — Evento PDF non prova download, apertura o completezza della mappa

**Classificazione: SHOULD FIX BEFORE EXPERIMENT**

- **Comportamento attuale:** `report_generated` viene emesso quando il Blob è pronto. Download e anteprima sono link senza evento dedicato. La cattura mappa può fallire e il PDF degrada comunque a successo.
- **Evidenza:** `app.js:2395-2454`; comportamento di fallback in `pdf-export.js`; il protocollo stesso riconosce che il download va osservato.
- **Impatto scientifico:** T2 richiede due file scaricati e verificati; il log non può distinguere “generato”, “scaricato”, “aperto” e “mappa presente”.
- **Comparabilità:** il pulsante PDF è comune ai due canali, quindi il meccanismo è simmetrico; l'attribuzione della riuscita resta però incompleta in entrambe le condizioni.
- **Dati già prodotti:** sì, se `report_generated` è stato interpretato come task completato o download riuscito.
- **Azione:** correzione minima di logging/verifica del deliverable oppure checklist osservazionale obbligatoria e separata; registrare anche la qualità della cattura.

### F07 — Stato selection/displayed/last/history distinto ma non completamente ricostruibile

**Classificazione: ACCEPTABLE LIMITATION**

- **Comportamento attuale:** current selection, displayed analysis, last analysis e history sono distinti correttamente. Una nuova analisi diventa displayed/last e cancella la selezione corrente; lo storico resta server-side. Lo stato mappa/report resta browser-side.
- **Evidenza:** `assistant_runtime.py:819-840`, `1240-1278`, prompt `1433-1468`; `app.js:1877-1924`; `map_filtering.py` vincola il filtro all'id visualizzato.
- **Impatto scientifico:** riduce gli errori anaforici, ma reload/back/uso fuori protocollo può creare divergenza fra storico e display.
- **Comparabilità:** sostanzialmente simmetrica durante un task ininterrotto; non equivalente nel recupero per via di F04/F05.
- **Dati già prodotti:** non altera valori; può alterare quale analisi il partecipante ritiene corrente.
- **Azione:** protocollo di recovery e wording preciso; software solo se il pilot deve tollerare reload.

### F08 — Richieste multi-tool sequenziali ma dipendenti dal provider

**Classificazione: SHOULD FIX BEFORE EXPERIMENT**

- **Comportamento attuale:** tool eseguiti sequenzialmente, massimo sei round, `parallel_tool_calls=False`; il contesto viene avanzato tra chiamate. Il response object conserva soprattutto l'ultimo risultato per tipo, mentre gli effetti intermedi possono essere emessi via stream e salvati nello storico.
- **Evidenza:** `assistant_runtime.py:459-567`, `819-840`, `1097-1120`; test di compound turn presenti.
- **Impatto scientifico:** T1/T2 lunghi richiedono pianificazione affidabile. Un modello può fermarsi presto, scegliere analisi congiunta invece di separate, superare i round o verbalizzare solo parte degli effetti.
- **Comparabilità:** la GUI obbliga passi espliciti; la chat può comprimere più passi in una richiesta. Questo è parte del trattamento, ma fallimenti parziali devono essere osservabili e valutati.
- **Dati già prodotti:** possibile; i log possono mostrare più analisi anche se la risposta finale espone solo l'ultima.
- **Azione:** non serve redesign. Congelare provider/modello, eseguire test E2E reali delle due consegne complete in entrambe le condizioni e definire criteri di successo parziale.

### F09 — Nomi multipli parzialmente invalidi vengono ignorati

**Classificazione: SHOULD FIX BEFORE EXPERIMENT**

- **Comportamento attuale:** se almeno un nome corrisponde, il payload viene creato con i comuni validi e gli altri non causano errore.
- **Evidenza:** `municipality_text.py:94-107` usa `isin(canonical_names)` e fallisce solo se `filtered.empty`.
- **Impatto scientifico:** una richiesta “A e B” può produrre silenziosamente l'analisi della sola A, con risultati formalmente validi ma area sbagliata.
- **Comparabilità:** la GUI rende visibile ogni checkbox; la chat è più esposta al partial match silenzioso.
- **Dati già prodotti:** potenzialmente, verificabile confrontando `requestedMunicipalities` e comuni effettivi.
- **Azione:** correzione software o validazione esplicita di tutti i nomi prima dell'analisi.

### F10 — Testo conversazionale duplicato nel log persistente

**Classificazione: SHOULD FIX BEFORE EXPERIMENT**

- **Comportamento attuale:** il frontend salva `chat_message` e `chat_response`; il backend salva `interaction_started` e `interaction_completed`. User text e risposta finiscono quindi più volte nel JSONL persistente. Il transcript voce può essere ripetuto ulteriormente in `voice_transcribed`.
- **Evidenza:** `app.js:2721-2733`, `2876-2897`; `views.py:612-625`, `677-695`; `study_logging.py:99-131`.
- **Impatto scientifico:** analisi testuale ingenua sovrappesa alcune utterance; aumenta esposizione privacy e dimensione dati.
- **Comparabilità:** la duplicazione riguarda soprattutto conversational/voice, creando densità di eventi e testo non confrontabile con GUI.
- **Dati già prodotti:** sì; deduplicabili con event type/source/timestamp, ma non esiste un interaction id comune dedicato.
- **Azione:** definire un record autorevole e riferimenti correlabili; formalizzare consenso, retention e accesso prima dei partecipanti.

### F11 — `textInteractionCount` e `voiceInteractionCount` contano eventi, non interazioni

**Classificazione: SHOULD FIX BEFORE EXPERIMENT**

- **Comportamento attuale:** ogni evento con `interactionMode=text` incrementa il contatore. Una singola richiesta con message/start/tool start/tool completed/completed/response produce `interactionCount=1` ma `textInteractionCount=6`.
- **Evidenza:** `logging.py:237-251`, `_count_interaction_mode` a `270-271`; il test `tests.py:3260-3290` cristallizza questa semantica.
- **Impatto scientifico:** i nomi inducono a interpretare righe evento come turni, falsando descrittive e confronti.
- **Comparabilità:** forte rischio, perché la GUI e la chat generano numeri e tipi diversi di eventi per una singola azione logica.
- **Dati già prodotti:** gli eventi grezzi sono recuperabili; summary già esportati vanno ricalcolati.
- **Azione:** correzione delle metriche o rinomina esplicita in `textEventCount`/`voiceEventCount`; l'unità osservazionale deve essere `taskRunId` e, per turni, un id di interazione.

### F12 — `operationalStepCount` non è una misura comparabile di passi

**Classificazione: SHOULD FIX BEFORE EXPERIMENT**

- **Comportamento attuale:** somma `stepCount` arbitrari da eventi frontend e backend: click=1, chat message=1, chat response=2 o 3, più altri eventi. Lo stesso episodio può contribuire più volte.
- **Evidenza:** `logging.py:238-242`; assegnazioni in `app.js`, inclusi `2721-2733` e `2876-2883`.
- **Impatto scientifico:** una metrica presentata come efficienza operativa non ha la stessa unità tra condizioni.
- **Comparabilità:** compromessa se usata come outcome GUI-vs-conversational.
- **Dati già prodotti:** sì; i raw event consentono una nuova codifica, ma non sempre la ricostruzione perfetta dei passi logici.
- **Azione:** definire prima dello studio una tassonomia e una funzione di derivazione versionata; non usare il campo corrente come numero comparabile di passi.

### F13 — Errori tool recuperabili registrati come completamenti

**Classificazione: SHOULD FIX BEFORE EXPERIMENT**

- **Comportamento attuale:** un `ValueError` del tool viene restituito al modello come `{ok:false,error}`. Lo stream emette comunque `tool_result`; il client registra sempre `tool_completed` con status `completed`. L'errore resta soltanto nel logger applicativo e nella conversazione interna del modello.
- **Evidenza:** `assistant_runtime.py:893-919` e `519-535`; `app.js:2783-2801`.
- **Impatto scientifico:** recovery, error rate e affidabilità dell'assistente sono sottostimati; un fallimento può precedere una risposta apparentemente riuscita.
- **Comparabilità:** penalità e tentativi conversazionali non sono misurati correttamente rispetto agli errori GUI.
- **Dati già prodotti:** sì; senza log applicativo correlato alcuni errori recuperati non sono ricostruibili dal JSONL sperimentale.
- **Azione:** correzione software del protocollo eventi e test specifico `tool_failed`/recovered.

### F14 — Enforcement delle condizioni forte ma non totale

**Classificazione: SHOULD FIX BEFORE PAPER**

- **Comportamento attuale:** UI e server bloccano i percorsi principali incrociati durante un task attivo. Gli endpoint history CRUD/confronto non applicano lo stesso blocco; una chiamata HTTP diretta resta possibile. L'enforcement non opera fuori da un task attivo.
- **Evidenza:** `app.js:840-943`; guardie in `views.py` per `/gis`, `/interact`, stream e STT; assenza di guardia nelle viste history.
- **Impatto scientifico:** basso con partecipanti che usano soltanto l'UI controllata, maggiore se si afferma isolamento server-side totale.
- **Comparabilità:** i normali affordance sono separati; non c'è però una garanzia di non-circumvention completa.
- **Dati già prodotti:** no, salvo violazioni fuori dall'UI non osservate.
- **Azione:** non indispensabile al pilot con ambiente controllato; precisare il threat model o estendere le guardie prima di un claim forte.

### F15 — Catalogo task e versione del protocollo non univoci nel log

**Classificazione: SHOULD FIX BEFORE EXPERIMENT**

- **Comportamento attuale:** la task sheet v0.5 definisce due task lunghi, mentre la console espone sei identificativi/titoli legacy. Il protocollo assegna manualmente più segmenti ai vecchi id; nei record non compare una versione della task sheet/batteria.
- **Evidenza:** `views.py:76-83`; `asita-2026-task-sheet.md:1-7`; `asita-2026-pilot-protocol.md:15`, `126-139`.
- **Impatto scientifico:** lo stesso `taskId` può avere significati diversi tra revisioni o segmenti; rischio di aggregazione errata e scarsa riproducibilità.
- **Comparabilità:** una mappatura manuale incoerente può assegnare fasi diverse alle condizioni.
- **Dati già prodotti:** sì; le sessioni tecniche devono essere etichettate con protocollo/versione esternamente ed escluse come già indicato.
- **Azione:** correzione minima di configurazione/schema o blocco operativo versionato e immutabile prima del primo partecipante.

### F16 — Voice è STT-only e dipende da OpenAI

**Classificazione: DOCUMENTATION ONLY**

- **Comportamento attuale:** MediaRecorder invia audio a OpenAI transcription, poi il transcript percorre la stessa chat. Non esiste sintesi o riproduzione della risposta. Con LLM Ollama serve comunque `OPENAI_API_KEY` per la voce.
- **Evidenza:** `app.js:1397-1648`; `views.py:854-921`; `interaction/voice.py`; `providers.py:22-29` contiene protocolli non collegati; `audio_output_text` resta testo.
- **Impatto scientifico:** importante per interpretare la modalità: misura input vocale con output visuale, non dialogo vocale bidirezionale.
- **Comparabilità:** voce e testo condividono il runtime dopo STT, ma voce aggiunge errori e latenza di trascrizione.
- **Dati già prodotti:** non altera i risultati GIS; può alterare intent/nome comune riconosciuto.
- **Azione:** descrizione precisa nel paper e pretest acustico; nessun TTS necessario per i task attuali.

### F17 — OpenAI e Ollama hanno comportamento diverso; configurazione sperimentale congelata

**Classificazione: FIXED FOR CONVERSATIONAL CORE**

- **Comportamento attuale:** il percorso conversazionale ASITA accetta esclusivamente OpenAI Responses API. `LLM_TIMEOUT_SECONDS` è applicato ai client Responses e STT, i retry SDK sono disabilitati e Ollama viene rifiutato prima dell'orchestrazione. Non esiste fallback.
- **Configurazione congelata:** `LLM_PROVIDER=openai`, `OPENAI_MODEL=gpt-5-mini`, `OPENAI_BASE_URL=https://api.openai.com/v1`, `LLM_TIMEOUT_SECONDS=60`, `OPENAI_TRANSCRIPTION_MODEL=gpt-4o-transcribe`, tool strict, `parallel_tool_calls=false`, output finale JSON Schema strict, verbosity `low`; temperature e seed non sono impostati.
- **Evidenza:** `interaction/llm.py`; `interaction/voice.py`; `views.py:_provider_failure_response`; regression test `OpenAiRuntimeFreezeTests`.
- **Comparabilità:** Ollama resta nel repository per uso non sperimentale, ma non è una condizione valida del pilot e non fa parte della validazione della milestone.

### F18 — 21 geometrie sorgente non valide e nessun gate di qualità dataset

**Classificazione: SHOULD FIX BEFORE EXPERIMENT**

- **Comportamento attuale:** il layer natura contiene 21 geometrie con ring self-intersection. I clip dei sei comuni controllati hanno prodotto output validi, ma non esiste un controllo/versionamento che impedisca input invalidi o cambi dataset silenziosi.
- **Evidenza:** ispezione GeoPandas/Shapely del layer; `datasets.py` carica/cacha i file senza quality gate. I dataset comunali controllati risultano validi.
- **Impatto scientifico:** geometrie non valide possono alterare intersezioni o causare errori dipendenti dalla versione GEOS; il rischio va quantificato prima della baseline definitiva.
- **Comparabilità:** stesso effetto su entrambi i canali; può però produrre fallimenti apparentemente casuali per area.
- **Dati già prodotti:** potenzialmente; nei sei clip controllati non restano geometrie output invalide, ma ciò non prova equivalenza a una versione riparata.
- **Azione:** validare/riparare o giustificare il preprocessing e registrare hash/versione dataset; rigenerare le reference answer.

### F19 — La suite protegge i contratti, non la correttezza geografica

**Classificazione: SHOULD FIX BEFORE EXPERIMENT**

- **Comportamento attuale:** 122 test passano. I test usano soprattutto fixture sintetiche e contratti; non esiste un test che asserisca area post-clip geometrica, copertura completa dei codici o baseline corretta per T1/T2.
- **Evidenza:** `tests.py:553-630` costruisce un poligono da 10 ha attributivi e lo ritaglia senza verificare la nuova area; ricerca della suite non trova reference numeriche reali dei task.
- **Impatto scientifico:** regressioni o risultati semanticamente errati possono apparire “verificati”.
- **Comparabilità:** i test di orchestrazione dimostrano convergenza e chaining, non l'uguaglianza E2E completa delle due condizioni sui task reali.
- **Dati già prodotti:** no direttamente; spiega perché gli errori hanno superato la verifica.
- **Azione:** aggiungere i test del §F dopo le correzioni e prima di sbloccare la raccolta.

### F20 — Identità sessione e scrittura dei log non sono robuste alla concorrenza

**Classificazione: SHOULD FIX BEFORE EXPERIMENT**

- **Comportamento attuale:** `studySessionId` contiene timestamp con precisione al secondo e condizione, senza nonce. Due avvii dello stesso partecipante/condizione nello stesso secondo usano la stessa directory. Gli eventi sono aggiunti a JSONL e `summary.json` è riletto e riscritto integralmente a ogni evento, senza lock o replace atomico. Una condizione invalida viene inoltre convertita silenziosamente in `webgis`.
- **Evidenza:** `study_logging.py:45-66`, `124-131`, `257-267`, `_coerce_choice` a `294-296`; `views.py:1016-1044` non rifiuta la condizione invalida prima della creazione.
- **Impatto scientifico:** collisioni rare possono fondere sessioni; richieste frontend/backend concorrenti possono lasciare un summary stale o parziale anche se il JSONL resta recuperabile; un errore di configurazione può etichettare la condizione sbagliata.
- **Comparabilità:** il conversational genera più eventi e più concorrenza fra stream e endpoint di logging; un fallback silenzioso a `webgis` altera direttamente l'assegnazione.
- **Dati già prodotti:** potenzialmente; verificare directory duplicate, coerenza `eventCount` summary/JSONL e condition prima di aggregare.
- **Azione:** id univoco, validazione fail-closed della condizione e scrittura/derivazione summary robusta; usare il JSONL grezzo come fonte primaria finché non corretto.

## A. Verification of Previous Dossier

| Finding/claim precedente | Esito | Verifica indipendente |
|---|---|---|
| Monolite Django + client Leaflet, non microservizi | **CONFIRMED** | Struttura, routing e servizi confermati |
| GUI e chat condividono il core GIS | **CONFIRMED** | Uguaglianza esatta del summary sui sei comuni verificati |
| Area post-clip non ricalcolata, “possibile sovrastima” | **PARTIALLY CONFIRMED** | Meccanismo corretto, severità sottostimata: la sovrastima è osservata e molto ampia |
| Quattro mismatch di case, 615 feature | **CONFIRMED** | Codici e conteggio riprodotti; effetti osservati sui task |
| Payload/pannelli come ground truth, testo LLM non validato | **PARTIALLY CONFIRMED** | Coerenza strutturale confermata, ma “ground truth” è improprio finché il calcolo GIS è errato |
| Formula economica deterministica condivisa | **CONFIRMED** | Stessa formula e stesse opzioni; persistenza diversa |
| `prepare_report` apre, non genera PDF | **CONFIRMED** | PDF esclusivamente client-side e dipendente dallo stato corrente |
| Current selection, displayed, last e history distinti | **CONFIRMED** | Contratti distinti; recupero dopo reload incompleto |
| Compound request supportate | **PARTIALLY CONFIRMED** | Loop e test esistono; riuscita dei task completi dipende dal provider e non è collaudata su v0.5 |
| Logging frontend/backend può generare più eventi | **PARTIALLY CONFIRMED** | Vero, ma il dossier non rilevava che i contatori “interaction” contano eventi e che errori tool recuperati risultano completati |
| Enforcement client + server | **PARTIALLY CONFIRMED** | Forte sui percorsi core; history resta accessibile direttamente e vale solo durante task attivo |
| Voice input STT, nessun TTS | **CONFIRMED** | Nessun percorso di sintesi/riproduzione trovato |
| Astrazione OpenAI/Ollama, nessun fallback | **PARTIALLY CONFIRMED** | Interfaccia comune confermata; comportamento, history, strictness, temperatura e timeout non equivalenti |
| Console runtime con sei task contro documentazione più recente | **CONFIRMED** | Il mismatch persiste e manca la versione protocollo nei record |
| Storico session-scoped | **CONFIRMED** | Persiste nella sessione Django, non ricostruisce necessariamente la UI corrente |
| 122 test superati | **CONFIRMED** | Suite rieseguita con successo il 4 settembre 2026 |

Nessun finding architetturale centrale del dossier è risultato completamente inventato. Le conclusioni **errate per eccesso** sono i claim impliciti di “ground truth” dei pannelli e di comparabilità delle metriche di logging: sono validi solo dopo le correzioni e la ridefinizione delle unità.

## B. Experiment Blockers

Devono essere chiusi prima del primo partecipante:

1. **F01:** ricalcolare la superficie sulla geometria post-clip in un CRS metrico appropriato e propagare il risultato.
2. **F02:** normalizzare/validare i codici vegetazionali in backend, fallback JS, mappa e filtri.
3. Rigenerare tutte le baseline ASITA, scenari economici, confronti e PDF; invalidare formalmente i reference number correnti.
4. Eseguire un pilot tecnico pulito su T1 e T2 completi, in entrambe le condizioni, dopo le correzioni.

F10–F13, F15, F17–F20 sono requisiti “should fix” molto vicini al blocco: se text/voice counts, step count, tool failure rate o PDF completion sono outcome primari, diventano anch'essi blocker metodologici.

## C. Scientific Validity Risks

- **Validità del costrutto:** `ettari analizzati` oggi non corrisponde all'area ritagliata; “CO2 annua” eredita lo stesso errore.
- **Validità interna:** la chat può verbalizzare numeri errati, ignorare un comune invalido o completare parzialmente una richiesta multi-tool.
- **Comparabilità:** formula/core sono condivisi, ma persistenza, prosa generativa, compattazione multi-tool e recovery introducono differenze reali.
- **Strumentazione:** counts text/voice e step non hanno unità comparabili; fallimenti tool recuperati sono invisibili; PDF generated non equivale a deliverable completato.
- **Provenienza dati:** geometrie invalide, assenza di quality gate e mancata fonte/versione scientifica dei coefficienti impediscono claim forti di accuratezza.
- **Confondente provider:** modello/provider/configurazione differenti possono modificare soltanto la condizione conversational.
- **Contaminazione pregressa:** feasibility check, log tecnici e PDF correnti incorporano la pipeline difettosa.

## D. Paper Accuracy Risks

Nello stato attuale sarebbe scorretto affermare che:

- la superficie riportata è la superficie forestale interna all'area selezionata;
- i totali CO2 e i valori economici correnti sono geograficamente validati;
- tutte le categorie del dataset sono classificate e colorate;
- GUI e conversational producono risultati “corretti” identici; producono output computazionali identici, ma oggi errati;
- ogni numero della risposta conversazionale è verificato automaticamente;
- `prepare_report` o l'LLM genera il PDF;
- `report_generated` dimostra download/apertura/verifica del file;
- lo storico permette sempre di riaprire un'analisi completa;
- le valutazioni economiche hanno persistenza equivalente tra condizioni;
- `textInteractionCount`, `voiceInteractionCount` o `operationalStepCount` sono direttamente turni o passi comparabili;
- tutte le violazioni di condizione sono impedite server-side;
- la modalità voice è un assistente vocale bidirezionale;
- OpenAI e Ollama sono intercambiabili senza effetti sperimentali;
- i task registrati sono auto-descrittivi senza indicare task sheet/protocol version;
- la suite corrente valida l'accuratezza geografica.

## E. Recommended Fix Order

1. Congelare copia/hash dei dataset e definire formalmente area, unità e CRS.
2. Correggere area post-clip nel singolo core backend.
3. Correggere e centralizzare la normalizzazione dei codici; allineare backend, UI, mappa e filtro.
4. Eseguire quality gate sulle 21 geometrie invalide e decidere il preprocessing riproducibile.
5. Rigenerare baseline, confronti, scenari economici e feasibility check; marcare obsoleti gli artefatti precedenti.
6. Rendere atomica la validazione di richieste con più comuni.
7. Correggere telemetria: interaction id, eventi tool error/recovery, deduplica testi, semantica dei count e dei passi, stato PDF.
8. Rendere univoca la sessione, fail-closed la condizione e robusta la scrittura/derivazione dei log.
9. Allineare catalogo task e versione protocollo nel log.
10. Aggiungere controllo numerico della prosa o regola di scoring basata sui payload strutturati.
11. Applicare il timeout anche a OpenAI e congelare provider/modello/opzioni.
12. Eseguire regression suite più pilot E2E reale T1/T2 in entrambi i canali.
13. Aggiornare dossier, protocollo, paper e informativa privacy con i comportamenti verificati.

## F. Regression Test Requirements

### GIS e dati

- Un poligono sorgente parzialmente ritagliato deve contribuire con l'area del frammento, non con `ettari` originale.
- Clip totale deve restituire area coerente con la geometria sorgente entro tolleranza documentata.
- Più frammenti dello stesso poligono non devono duplicare area.
- Comuni multipli e area disegnata devono usare lo stesso metodo d'area.
- Ogni codice dataset deve essere mappato o esplicitamente escluso; test dedicati per `41.B`, `41.C1`, `41.Lcn`, `44.D2cn`.
- Mappa, filtro, summary backend e fallback JS devono risolvere lo stesso codice nella stessa categoria/colore.
- Gate su geometrie nulle, vuote e invalide; hash/versione dataset registrati.
- Golden baseline post-fix per Benevento, Montella, Avellino+Salerno e Salerno con tolleranze dichiarate.

### Parità dei canali

- Stesso municipality payload via `/gis` e `analyze_municipalities`: uguaglianza di area, items, top category e CO2.
- Stessi quattro scenari: uguaglianza di prezzo, CO2 e valore tra JS e backend, inclusa precisione prima del formatting.
- Test che un valore GUI e conversational alimentino PDF equivalenti nello stesso stato.
- Test esplicito delle differenze ammesse: drawn geometry, persistence e reload.

### Stato e multi-tool

- New analysis aggiorna displayed/last, salva history e azzera current selection senza riusare selezioni stale.
- Analyze -> economy -> prepare report conserva stessa `analysisId` e scenario.
- Due analisi separate -> comparison usa esattamente le due appena create.
- Joint analysis -> corrected single analysis non valuta per errore la prima area.
- Errore tool recuperabile -> evento failed/recovered, non completed; contesto successivo corretto.
- Test E2E real-provider delle richieste complete T1/T2, non solo fake provider.

### Report

- PDF generato contiene analysis id, area, CO2, scenario e valore corretti.
- Cattura mappa riuscita/fallita è esplicita e testata.
- Eventi distinti per prepared/generated/download-requested/opened, oppure verifica osservazionale codificata.
- Due PDF successivi per la stessa analisi con scenari diversi restano distinguibili e verificabili.

### Logging ed enforcement

- Una richiesta testuale produce `interactionCount=1` e un singolo record autorevole del testo per policy.
- Conteggi text/voice definiti su interazioni, non su tutti gli eventi.
- Step metric derivata da tassonomia versionata e testata su percorsi equivalenti.
- Correlazione stabile fra frontend, backend, tool e PDF con interaction/task run id.
- Nessuna perdita silenziosa degli eventi necessari prima del terminal task event.
- Blocchi client/server per ciascuna azione proibita; test esplicito degli endpoint history secondo il threat model scelto.
- `taskId`, task sheet version e protocol version presenti e coerenti.
- Due sessioni create nello stesso secondo devono avere id distinti; una condizione invalida deve essere rifiutata.
- Append/summary concorrenti non devono perdere eventi e `summary.eventCount` deve coincidere con il JSONL.
- Test privacy: campi testuali presenti soltanto nel livello previsto, con limiti e retention applicati.

### Provider e voce

- Contract suite identica per OpenAI e Ollama: tool schema, tool chaining, JSON finale, error mapping.
- Timeout configurato ed effettivo per entrambi.
- STT con MIME supportati, dimensione limite, transcript vuoto/errato e dipendenza chiave OpenAI.
- Test negativo che nessun TTS venga dichiarato o attivato.

## G. Final Readiness Assessment

| Dimensione | Valutazione | Motivazione |
|---|---|---|
| **System readiness** | **NOT READY** | Architettura coerente e suite verde, ma core GIS produce metriche materialmente errate e dataset mapping incompleto |
| **Experiment readiness** | **NOT READY** | I task chiedono proprio le variabili alterate; baseline v0.5 non valida e full-route pilot non ancora eseguito post-fix |
| **Logging readiness** | **NOT READY FOR INFERENTIAL USE** | Raw events utili, ma duplicazioni, counts semanticamente errati, tool failure invisibili e prova PDF incompleta |
| **Paper-description readiness** | **CONDITIONALLY READY FOR ARCHITECTURE ONLY** | Si può descrivere struttura, tool orchestration, STT-only e shared core; non accuratezza numerica, equivalenza completa o metriche sperimentali finché non corretti e rivalidati |

### Decisione finale

**No-go per la raccolta con partecipanti nello stato `5277531`.**  
Il go/no-go va rivalutato dopo chiusura F01/F02, rigenerazione delle baseline, test di regressione geografici e un pilot tecnico completo T1/T2. Gli altri finding “before experiment” devono essere chiusi oppure trasformati in decisioni metodologiche esplicite prima di definire il dataset sperimentale definitivo.

# Protocollo pilot ASITA 2026

> **ARCHIVIO STORICO — NON ESEGUIRE COME PROCEDURA SOFTWARE.** La console studio,
> participant/task lifecycle, taskRunId ed export descritti qui sono stati rimossi.
> Il protocollo corrente è gestito manualmente dall'operatore; Carta Natura espone
> solo `?mode=gui-only` e `?mode=conversational-only` e salva telemetria raw.

> **Proposta precedente v0.2.** Le consegne correnti sono nella [task sheet v0.5](asita-2026-task-sheet.md): due incarichi estesi, distinti per obiettivo e percorso, che sostituiscono la proposta a quattro task. Le batterie A/B, la relativa corrispondenza con gli ID e le tabelle di assegnazione riportate sotto appartengono alla proposta precedente e non definiscono l'uso delle nuove consegne. L'assegnazione delle modalità resta a cura del ricercatore.

Versione: **ASITA-2026-PILOT-v0.2**

Data: 2 settembre 2026

Stato: proposta operativa con funzioni verificate online; durata ed equivalenza da calibrare con partecipanti pilota.

App: [Carta Natura, modalità studio](https://cartanatura-production.up.railway.app/progettoGIS/cartaNatura/?study=1)

[Consegne correnti: due task estesi](asita-2026-task-sheet.md) · [Evidenze e limiti di fattibilità](asita-2026-feasibility-check.md)

La v0.2 sostituisce la sequenza T1–T6 di micro-task dipendenti della v0.1. Si confrontano percorsi completi che iniziano sempre da un'analisi comunale. Questa revisione riguarda la documentazione: il catalogo della console online mantiene i vecchi titoli, con la corrispondenza operativa descritta sotto.

## 1. Obiettivo e unità di confronto

Confronto entro partecipante tra:

- **webgis**: selezione e operazioni tramite controlli grafici;
- **conversational**: richieste testuali interpretate dall'LLM, con tool applicativi e mappa per verifica.

Il trattamento conversazionale include la consultazione visiva e i controlli comuni per generare/scaricare il PDF. Non è una condizione priva di grafica. Usare testo come canale standard; mescolare testo e voce aggiungerebbe un fattore diverso da quello qui studiato.

Un task è un obiettivo completo con più risultati osservabili, un solo avvio e un solo termine. L'unità di confronto è il percorso svolto dal partecipante, non un clic, messaggio o singolo tool.

**Scelta proposta**: partire dalla batteria B di due dossier, se la priorità è ridurre la durata della sessione. La batteria A di quattro task permette di distinguere meglio confronto ambientale e valutazione economica. Non mescolare le batterie nello stesso campione senza un disegno dichiarato.

## 2. Batterie e copertura

| Batteria | Task per partecipante | Per modalità | Tempo operativo obiettivo |
| --- | --- | --- | --- |
| A — confronto e dossier separati | A1, A2, A3, A4: quattro totali | Un confronto + un dossier | 10–14 minuti |
| B — dossier integrati | B1, B2: due totali | Un dossier integrato | 5–7 minuti |

Totale delle sole attività: A 20–28 minuti, B 10–14. Addestramento, pause, questionari e operazioni dell'operatore sono aggiuntivi. Le durate sono ipotesi di progetto, non tempi osservati di partecipanti.

La batteria A comprende:

- A1: analisi separate Avellino → Benevento, confronto ambientale e verifica;
- A2: nuova analisi di Serino, scenari, cambio valutazione e PDF;
- A3: analisi separate Caserta → Salerno, confronto ambientale e verifica;
- A4: nuova analisi di Montella, scenari, cambio valutazione e PDF.

La batteria B comprende:

- B1: analisi separate Avellino → Benevento, confronto e dossier economico/PDF di Benevento;
- B2: analisi separate Caserta → Salerno, confronto e dossier economico/PDF di Salerno.

Copertura comune: ricerca/selezione nominale del territorio, analisi GIS, categorie, superficie e CO₂, confronto di analisi salvate e CO₂/ha, scenari economici, applicazione di uno scenario, mappa/legenda, report e PDF.

Esclusi dai task comparativi: disegno/modifica di geometrie, filtro per categoria, rinomina/eliminazione selettiva dello storico e recupero arbitrario di un vecchio report. Non hanno un percorso equivalente verificato nei due canali. Escluse anche funzioni assenti come buffer, distanze, vincoli territoriali o scenari di riforestazione. Dettagli nella verifica di fattibilità.

## 3. Comparabilità e assegnazione

Consegne identiche per obiettivi e risultati, con varianti territoriali. Non assegnare stabilmente i compiti semplici alla chat e quelli complessi al WebGIS. Nella batteria A ogni condizione include entrambe le famiglie.

Bilanciare **sia l'ordine dei canali sia l'assegnazione delle varianti**. L'inversione del solo canale non basta se una certa variante viene eseguita sempre per prima. L'uso di comuni diversi limita il riuso delle risposte, ma non elimina apprendimento e differenze di difficoltà. La nota metodologica di [I. Scott MacKenzie sul controbilanciamento](https://www.yorku.ca/mack/RN-Counterbalancing.html) motiva il controllo dell'ordine; gli schemi seguenti sono una proposta specifica per questa app.

### Batteria A — quattro sequenze

| Gruppo | Primo blocco | Secondo blocco |
| --- | --- | --- |
| 1 | WebGIS: A1 → A2 | Conversazionale: A3 → A4 |
| 2 | Conversazionale: A1 → A2 | WebGIS: A3 → A4 |
| 3 | WebGIS: A3 → A4 | Conversazionale: A1 → A2 |
| 4 | Conversazionale: A3 → A4 | WebGIS: A1 → A2 |

Ogni partecipante esegue tutti e quattro i task, ciascuno una sola volta. L'ordine interno confronto → economia resta fisso in questo pilota ed è uguale nei due trattamenti. Non attribuire un eventuale effetto dell'ordine delle famiglie alla sola interfaccia.

### Batteria B — quattro sequenze

| Gruppo | Primo blocco | Secondo blocco |
| --- | --- | --- |
| 1 | WebGIS: B1 | Conversazionale: B2 |
| 2 | Conversazionale: B1 | WebGIS: B2 |
| 3 | WebGIS: B2 | Conversazionale: B1 |
| 4 | Conversazionale: B2 | WebGIS: B1 |

Assegnare casualmente i partecipanti alle sequenze mantenendo gruppi il più possibile bilanciati; registrare il gruppo sul foglio operatore. Non decidere l'ordine dopo aver osservato le prestazioni.

Stessa struttura non dimostra equivalenza: Avellino/Benevento e Caserta/Salerno hanno numeri di categorie diversi. La consegna chiede un numero fisso di informazioni; controllare nel pilota eventuali differenze sistematiche di difficoltà. Due task offrono una sola osservazione per canale: risultati più sensibili alla variante, agli errori e alla latenza del modello.

## 4. Tempi, addestramento e istruzioni

- Obiettivo 5–7 minuti per task; timeout iniziale proposto 10 minuti, uguale per entrambe le modalità.
- Un risultato corretto in meno di 5 minuti resta un successo. Non imporre un numero minimo di click o messaggi.
- Fare una familiarizzazione di durata uguale per canale su un comune diverso da quelli della batteria, verificato prima dal facilitatore.
- Durante il task permettere uno o più prompt, incluse richieste composte. Non consegnare un prompt già pronto da copiare né obbligare il partecipante a usare uno specifico numero di turni.
- Presentare la stessa scheda di risposta esterna nei due canali. Nessun modulo di restituzione è stato aggiunto all'app.
- Avviare il timer all'esposizione della consegna e fermarlo alla restituzione richiesta, includendo lettura e controlli. Tenere costante la procedura.
- Includere la latenza nell'indicatore principale end-to-end; registrare separatamente attese e guasti tecnici. Non usare la lentezza dell'LLM per raggiungere il tempo obiettivo.

Aiuti consentiti: ripetere la consegna, chiarire il significato di un termine di dominio, ricordare che la mappa è consultabile nella condizione conversazionale. Non indicare il prossimo pulsante, dettare prompt o completare azioni. Registrare qualunque aiuto.

Calibrazione proposta: prima prova con 4–6 persone non esperte, bilanciando ordine e varianti; rivedere densità e comprensibilità prima della raccolta definitiva. Questa proposta non determina la numerosità statistica dello studio.

## 5. Regole dei trattamenti

### WebGIS

Consentiti: selezione dei comuni, analisi grafica, report e categorie, selezione delle analisi nello storico e confronto, scenari e calcolo, PDF, mappa/zoom/pan/legenda.

Non consentiti per completare il task: chat e voce. Durante un task attivo webgis il pannello assistente è disabilitato; gli endpoint conversazionali applicano il blocco di condizione.

### Conversazionale

Consentiti: chat per analisi, interrogazione dei risultati, confronto, calcolo e apertura del report; consultazione della mappa e dei risultati; controlli comuni PDF e Anteprima.

Non consentiti per completare il task: selezione comunale grafica, disegno, pulsante analisi, selezione di analisi nello storico, cambio prezzo o calcolo tramite i controlli grafici. Questi controlli sono bloccati durante il task attivo.

Leggere i risultati del confronto aperto dalla chat è consultazione ammessa. Se il partecipante deve tornare al report corrente, può richiederlo all'assistente. Il PDF nasce dai pulsanti del report: una frase della chat che ne promette il download non equivale al file.

Per entrambe le modalità:

- due comuni da confrontare richiedono due analisi separate, non un'analisi congiunta;
- il dossier di B1/B2 riguarda il secondo comune, che resta corrente;
- il PDF dell'analisi corrente non è il PDF del confronto;
- il filtro della mappa non ricalcola gli indicatori: non usarlo come analisi di un sottoinsieme;
- non richiedere la percentuale di copertura del territorio comunale; l'app mostra la superficie forestale analizzata;
- chiedere scarti assoluti, evitando ambiguità nel denominatore degli scarti percentuali.

## 6. Console attuale e identificativi

La console online espone ancora T1–T6. I titoli sono quelli del vecchio protocollo; il selettore assegna un identificativo al log e non impone una sequenza di azioni o un criterio automatico di completamento.

Per usare subito le nuove consegne senza modificare l'app, adottare questa corrispondenza esplicita e registrare batteria/versione sul foglio operatore:

| Task del protocollo | Voce attuale della console | taskId registrato |
| --- | --- | --- |
| A1 | T1 - Analisi comuni/area | asita_t1_area_analysis |
| A2 | T2 - Categorie forestali e CO2 | asita_t2_forest_co2 |
| A3 | T3 - Valore economico | asita_t3_economic_value |
| A4 | T4 - Confronto scenari | asita_t4_scenario_compare |
| B1 | T1 - Analisi comuni/area | asita_t1_area_analysis |
| B2 | T2 - Categorie forestali e CO2 | asita_t2_forest_co2 |

T5 e T6 non vanno avviati. Il titolo storico della voce non è la consegna da leggere al partecipante. Non mescolare questi log con quelli v0.1 senza la colonna batteria/versione: gli ID da soli non distinguono le due definizioni del task. Questa corrispondenza è una compatibilità operativa, non una modifica del catalogo dell'app.

### Sessioni pulite: una sessione tecnica per macro-task

Per isolare anche il contesto conversazionale, usare una nuova sessione della console per **ogni macro-task**, mantenendo lo stesso participantId. Non basta cambiare la voce Attività: questo non azzera il contesto. Il solo pulsante Reset area e risultati pulisce l'area grafica, non garantisce l'azzeramento della conversazione e dello storico.

1. Aprire la console; impostare codice anonimo, percorso e voce del task.
2. Premere **Avvia sessione**. Verificare che risultati e conversazione partano vuoti.
3. Preparare la consegna; premere **Inizia attività** e presentarla.
4. Osservare senza guidare; annotare risultati, errori e aiuti.
5. A esito verificato premere **Completa**; se il task fallisce o scade, **Errore**, annotando il motivo esternamente. **Non compresa** è per incomprensione, non un sinonimo di timeout.
6. Esportare JSON e JSONL **prima** di chiudere.
7. Premere **Chiudi sessione**. La chiusura azzera lo stato operativo; non chiudere un task riuscito senza averlo prima completato.
8. Se resta un task nello stesso blocco, avviare una nuova sessione con stesso codice e stesso percorso; al cambio trattamento scegliere il nuovo percorso.

Con A si producono quattro sessioni tecniche e quattro taskRunId per partecipante, due per condizione. Con B se ne producono due, uno per condizione. Ogni export contiene un macro-task; aggregare gli export per participantId e condition. Questionario di condizione dopo l'intero blocco, non dopo ogni sessione tecnica.

Una chiusura con task ancora attivo produce interruzione; conservarla come tale. I dati persistenti non devono essere cancellati per mascherare un fallimento.

## 7. Misure ed esiti

Ogni task ha risultati osservabili numerati nella task sheet. Il facilitatore assegna a ciascuno **corretto / parziale / mancante o errato**. Completamento pieno solo con tutti i risultati, unità e analisi corretti. Conservare il profilo dei risultati parziali, non solo il terminale binario della console.

Per i numeri confrontare le viste dell'app, accettando gli arrotondamenti mostrati. I tool e il PDF possono usare maggiore precisione della CO₂ arrotondata a schermo. Non calcolare manualmente una risposta di riferimento da un numero già arrotondato.

Dati oggettivi:

- tempo end-to-end tra task_started e il terminale dello stesso taskRunId;
- completamento totale e risultati parziali;
- errori, richieste non comprese, recuperi, aiuti e violazioni;
- latenza e problemi tecnici, distinguendoli dagli errori del partecipante;
- messaggi, tool e azioni UI come descrittori separati, non unità di sforzo equivalenti;
- corrispondenza tra analisi, confronto, valutazione finale e report.

I tempi dei soli successi non riassumono tutti i partecipanti: riportare separatamente fallimenti e timeout. Un task fallito con log ricostruibile è un dato valido dell'esperimento, non un motivo automatico per escludere la sessione. Non trattare clic/tool dello stesso partecipante come osservazioni indipendenti.

Dopo ogni task: difficoltà, fiducia e chiarezza (1–7), nota facoltativa. Dopo ogni blocco: scegliere prima dello studio SUS oppure UMUX-LITE; eventuale NASA-TLX nella versione dichiarata, controllo e verificabilità. Dopo entrambi: preferenza e motivazione. Moduli esterni all'app.

## 8. Evidenze nel logging e limiti

Campi da conservare: participantId, studySessionId, condition, taskId, taskRunId, timestamp, eventType, status, durationMs, operation, interactionMode, details.analysisId e, quando presenti, scenarioKey, priceEurPerTon, totalCo2, totalValueEur, reportFormat, toolName.

| Operazione | Evidenza disponibile |
| --- | --- |
| Avvio/termine | task_started; task_completed, task_failed o task_interrupted |
| Analisi | analysis_completed e/o eventi tool con risultati, analysisId e comune verificabile |
| Confronto WebGIS | interaction_completed con operation analysis_history_compare |
| Confronto chat | tool_started/tool_completed del confronto e risposta finale |
| Economia | valuation_completed con analisi, scenario, prezzo, CO₂ e valore |
| Report/PDF | report_opened; report_generated con reportFormat pdf e analysisId |
| Consultazione/interpretazione | osservazione e scheda esterna; non tutta la lettura produce eventi specifici |

Il confronto WebGIS non allega necessariamente tutti gli ID delle analisi all'evento: registrarli anche sul foglio operatore. Non supporre che apertura di ogni dettaglio, cambio ordinamento o comprensione siano misurati automaticamente.

L'evento PDF può avere interactionMode map anche nella condizione conversational, perché il pulsante è comune: classificare il trattamento tramite **condition**, non dal solo canale dell'evento. report_generated dimostra la generazione; il download effettivo e il controllo del file richiedono osservazione, non un evento dedicato garantito.

Sul foglio operatore registrare: versione/batteria, gruppo di assegnazione, codice task A/B, corrispondenza taskId, sessione/taskRunId, comuni, analysisId, risultati parziali, tempi, motivo del fallimento, aiuti, file PDF/export e misure soggettive.

## 9. Checklist e validità

Prima della raccolta:

- congelare batteria, versione dell'app/dataset, modello/provider e impostazioni;
- riprovare i percorsi su entrambi i canali nell'istanza online;
- calibrare durata e varianti; verificare un comune separato per addestramento;
- preparare consegne, scheda risposte, assegnazione e moduli soggettivi;
- verificare generazione/scaricamento PDF ed export del log;
- escludere i codici qa_ dalle analisi dei partecipanti.

Dopo ciascun blocco:

- controllare un task per export e il numero di export atteso;
- verificare un solo start/terminale per taskRunId;
- controllare condition, analisi/scenario finali, violazioni e risposte parziali;
- conservare anche errori e timeout; completare le misure soggettive.

Escludere o classificare separatamente secondo regole fissate prima della raccolta solo casi come log mancanti, contaminazione del canale non ricostruibile o aiuto sostanziale che rende il risultato non attribuibile al partecipante. Documentare il motivo; non cancellare gli originali.

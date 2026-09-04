# Fattibilità dei task estesi — verifica online

> **VALORI NUMERICI OBSOLETI — 4 settembre 2026.** Le verifiche contenute in questo documento sono state eseguite con la pipeline precedente, che riutilizzava `ettari` del poligono sorgente dopo il clipping e non riconosceva quattro codici vegetazionali. Non usare superfici, CO2, categorie, prevalenti o valori economici riportati qui come reference answer. La baseline ufficiale post-correzione è in [`asita-2026-gis-baseline.md`](asita-2026-gis-baseline.md). Le osservazioni di fattibilità restano memoria storica e devono essere ripetute prima dell'esperimento.

Data: **2 settembre 2026**. Protocollo: **ASITA-2026-PILOT-v0.2**.

Istanza osservata: [Carta Natura su Railway, modalità studio](https://cartanatura-production.up.railway.app/progettoGIS/cartaNatura/?study=1).

**Revisione documentale v0.5, 3 settembre 2026:** la consegna corrente contiene due incarichi estesi: T1 Benevento-Montella (analisi, categorie, legenda e confronto); T2 Avellino-Salerno, poi solo Salerno (rettifica, scenari e due PDF). Questa revisione riutilizza funzioni già controllate: non è una nuova prova online completa. Il nuovo abbinamento Benevento-Montella e le sequenze complete v0.5 in entrambe le modalità restano da collaudare. Le evidenze sotto mantengono il riferimento alle versioni effettivamente provate; non dimostrano una durata di 5–7 minuti.

**Integrazione del 3 settembre 2026 per la task sheet v0.4:** verificata dai controlli grafici, senza sessione sperimentale attiva, la sequenza di T3: analisi congiunta Avellino-Salerno (9.939,12 ha; 58.354,73 t CO₂/anno; 6 categorie; prevalenza Castagneti), poi nuova selezione e analisi del solo Salerno (2.953,73 ha; 14.846,69 t CO₂/anno; 6 categorie; prevalenza Leccete). La correzione richiede una nuova analisi, non la modifica di una geometria salvata. Le quattro nuove consegne sono distinte; le prove precedenti documentano le funzioni disponibili, ma non costituiscono un collaudo completo delle nuove sequenze in entrambe le modalità. I tempi di 5–7 minuti restano un obiettivo da verificare con partecipanti. Le sigle A/B e la corrispondenza con la console riportate nelle sezioni storiche sottostanti appartengono alla v0.2.

**Integrazione per la task sheet v0.3:** verificati online anche Eboli (1.689,13 ha, 6.243,72 t CO₂/anno, 5 categorie) e Battipaglia (281,08 ha, 962,44 t CO₂/anno, 3 categorie), entrambi con Querceti di roverella come categoria prevalente. Queste due analisi aggiuntive sono state eseguite dai controlli grafici, senza sessione sperimentale attiva. I confronti documentati sotto restano quelli effettivamente provati nella v0.2; non costituiscono un collaudo integrale di ciascuna nuova consegna v0.3.

Verifica svolta nel browser dell'app, attraverso controlli visibili e chat, con sessioni tecniche di entrambe le condizioni. Codice utilizzato: **qa_taskdesign_20260902**. Queste sessioni sono prove tecniche, da escludere dai dati dei partecipanti. Le prove non costituiscono una misura della durata per utenti non esperti.

## 1. Funzioni comuni utilizzabili

| Funzione | Evidenza WebGIS online | Evidenza conversazionale online | Uso nelle consegne |
| --- | --- | --- | --- |
| Analisi comunale | Analizzati singolarmente Avellino, Benevento, Salerno, Caserta, Serino e Montella | Analizzati Avellino, Benevento, Caserta, Salerno e Serino | Inizio di ogni task |
| Categorie, superficie, CO₂ | Report con indicatori, categoria prevalente, dettagli e ordinamento | Risposte coerenti con il report, inclusa prevalenza di Serino | Lettura ambientale |
| Confronto analisi salvate | Selezionate Avellino e Benevento nello storico; confronto con tre indicatori e scarti | Confronti Avellino–Benevento e Caserta–Salerno con dati corretti | A1/A3 e B1/B2 |
| Categorie comuni/distintive | Dettaglio disponibile nel confronto | Identificate Querceti di roverella/Castagneti per Avellino–Benevento e Leccete/Castagneti per Caserta–Salerno | Confronto qualitativo limitato a due esempi |
| Quattro scenari economici | Espansa la tabella su Avellino | Restituiti prezzi/valori su Benevento e Serino, con minimo/massimo su Serino | Dossier |
| Applicazione di uno scenario | Calcolati Costo sociale su Avellino e Mercato regolamentato su Montella | Applicato Mercato regolamentato su Benevento; su Serino applicati prima Costo sociale e poi Mercato regolamentato | Dossier e revisione della valutazione |
| Report corrente | Aperto automaticamente dopo analisi e consultabile da Risultati | Aperto il report di Benevento e poi di Serino con valutazione applicata | Dossier |
| Generazione PDF | Risposta UI Report pronto, 4 pagine, su Avellino e Montella | Stesso esito su Benevento e Serino; attivato Scarica PDF su Serino | Passaggio grafico comune |
| Mappa e legenda | Mappa con risultato comunale e comandi di consultazione | Mappa disponibile; richiesta di legenda eseguita con categorie visibili | Verifica visiva |
| Blocco di condizione | Assistente disabilitato durante task webgis | Selezione comuni, storico, selettore prezzo e Calcola valore disabilitati; Genera PDF disponibile | Separazione dei trattamenti |

Le prove hanno coperto le operazioni necessarie e dati concreti, non ogni possibile formulazione linguistica né ogni combinazione di task. Montella è stata verificata dall'interfaccia grafica; il corrispondente percorso conversazionale di analisi e revisione economica è stato provato su Serino. Non affermare che A4 sia già stato collaudato integralmente in chat con un partecipante.

## 2. Riscontri numerici per il facilitatore

Valori letti nell'app durante la verifica; servono come riferimento tecnico datato, non vanno inclusi nella consegna ai partecipanti. Aggiornarli se cambia il dataset. Non rappresentano una validazione indipendente della correttezza geografica o dei coefficienti del modello.

| Comune | Superficie analizzata, ha | CO₂ annua, t | Categorie | Prevalente per superficie |
| --- | ---: | ---: | ---: | --- |
| Avellino | 6.985,39 | 43.508,04 | 3 | Castagneti |
| Benevento | 4.274,73 | 14.106,62 | 2 | Querceti di roverella |
| Caserta | 1.574,31 | 6.005,74 | 2 | Querceti di roverella |
| Salerno | 2.953,73 | 14.846,69 | 6 | Leccete |
| Serino | 8.788,16 | 73.300,12 | 6 | Faggete |
| Montella | 25.234,61 | 211.537,82 | 7 | Faggete |

Confronti:

- Avellino–Benevento: CO₂/ha rispettivamente **6,23** e **3,30**; scarto assoluto CO₂ **29.401,42 t/anno**. Avellino maggiore nei tre indicatori. Esempi: Querceti di roverella comuni; Castagneti solo Avellino.
- Caserta–Salerno: CO₂/ha **3,81** e **5,03**; scarto assoluto CO₂ **8.840,95 t/anno**. Salerno maggiore nei tre indicatori. Esempi: Leccete comuni; Castagneti solo Salerno.

Scenari esposti in entrambi i canali:

| Scenario | Chiave applicativa | Prezzo EUR/tCO₂ |
| --- | --- | ---: |
| Costo sociale | social_cost | 138 |
| Prezzo ombra | shadow_price | 303 |
| Mercato regolamentato | regulated_market | 82 |
| Mercato volontario | voluntary_market | 20 |

Riscontri economici: Benevento con Mercato regolamentato **1.156.742,98 EUR/anno**; Serino con Costo sociale **10.115.416,94 EUR/anno**, poi con Mercato regolamentato **6.010.610,07 EUR/anno**, CO₂ invariata; Montella con Mercato regolamentato **17.346.101,02 EUR/anno**.

Gli euro usano valori di CO₂ a maggiore precisione di quelli visualizzati: differenze di centesimi rispetto al prodotto della CO₂ arrotondata non costituiscono un errore del partecipante.

## 3. Funzioni da non includere nel confronto tra canali

| Funzione | Limite verificato nell'interfaccia o nel codice | Decisione |
| --- | --- | --- |
| Disegnare/modificare poligoni o rettangoli | Comandi grafici presenti; la chat può analizzare una selezione già esistente, ma non creare lo stesso disegno tramite un tool dedicato | Esclusa |
| Filtrare categorie sulla mappa | Tool chat presente; non trovato un comando grafico equivalente per applicare il filtro. Mostra tutte serve a rimuoverlo | Esclusa dai risultati obbligatori comuni |
| Rinomina/eliminazione selettiva di analisi | Pulsanti nello storico; nessun tool conversazionale corrispondente | Escluse |
| Riaprire arbitrariamente un vecchio report | Le viste e i tool disponibili non forniscono un recupero equivalente verificato. Lo storico consente soprattutto elenco/confronto e gestione | Dossier sull'analisi corrente |
| PDF del confronto fra comuni | Il generatore usa l'analisi corrente e la sua valutazione, non il confronto | Richiedere PDF di un comune esplicito |
| CO₂ o valore di un sottoinsieme filtrato | Il filtro modifica la mappa; KPI e scenari restano sull'analisi completa | Non richiedere ricalcolo filtrato |
| Buffer, distanze, sovrapposizioni con vincoli, futuri impianti forestali | Nessuna funzione comune verificata per queste operazioni | Esclusi |
| Prezzi personalizzati e proiezioni nel tempo | I task verificati usano quattro scenari definiti nell'app e valore annuale | Esclusi |

Non è possibile includere ogni funzione dell'app e allo stesso tempo pretendere equivalenza completa dei canali. La batteria copre le principali funzioni comuni; le asimmetrie vanno dichiarate, non nascoste dentro le consegne.

## 4. Stato applicativo e logging

La console online espone ancora sei etichette T1–T6. La nuova documentazione non ha modificato il software. La corrispondenza tra task estesi e vecchi ID è specificata nel protocollo.

Controllo del codice locale a supporto delle osservazioni:

- [views.py](../cartaNatura/views.py): catalogo della console; avvio/chiusura di una sessione svuotano il contesto operativo.
- [app.js](../cartaNatura/static/js/app.js): blocchi di condizione, report, calcolo, reset grafico, eventi e generazione PDF.
- [analysis-history.js](../cartaNatura/static/js/modules/analysis-history.js): confronto con indicatori, categorie e scenari; gestione delle schede salvate.
- [assistant_runtime.py](../cartaNatura/interaction/assistant_runtime.py): tool disponibili e restituzione dei risultati.
- [map_filtering.py](../cartaNatura/interaction/tools/map_filtering.py): filtro della sola visualizzazione.
- [pdf-export.js](../cartaNatura/static/js/modules/pdf-export.js): report dell'analisi corrente; la cattura della mappa può fallire lasciando comunque un PDF con dati.

Il codice locale aiuta a chiarire i limiti; non è una prova autonoma dell'identità del commit distribuito online. Per la raccolta definitiva registrare la versione effettivamente distribuita.

**PDF:** verificata la generazione dichiarata dall'interfaccia e attivato il comando di download. Il contenuto di tutte le pagine dei file non è stato revisionato in questa verifica. Nel pre-pilot controllare il file e la presenza della mappa; un PDF generato senza immagine va distinto da un dossier completo quando la mappa è richiesta.

**Misurazione:** non sono stati analizzati gli export JSON/JSONL di queste prove. I nomi degli eventi e i limiti documentati derivano dall'ispezione del codice; confermare gli export nel pre-pilot. Lettura, comprensione e scaricamento effettivo non sono tutti deducibili automaticamente dagli eventi.

## 5. Cosa resta da validare nel pilota

1. Durata effettiva di 5–7 minuti per utenti non esperti, con il provider usato nello studio.
2. Comparabilità delle varianti: il numero di categorie varia; le richieste restano a quantità fissa.
3. Comprensione della consegna e distinzione tra CO₂ totale, CO₂/ha e valore economico.
4. Completezza del PDF e qualità delle verifiche visive sul dispositivo dello studio.
5. Export e collegamento tra risultati, analysisId, taskRunId, scenario e condition.

Le prestazioni di un agente che conosce già i controlli non stimano il tempo di un partecipante. Anche una singola richiesta composta riuscita non garantisce che ogni formulazione dell'LLM produca lo stesso percorso: registrare errori e recuperi come parte dell'interazione.

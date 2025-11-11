# Autoplay Lesson

Automazione Playwright modulare per riprodurre in sequenza le lezioni di un corso online Pegaso/Multiversity.

## Novità principali

- Avvio da CLI o da interfaccia grafica con pulsanti **Start/Stop** e pannello log.
- Profilo Chrome persistente (channel="chrome") con riuso dei cookie personali tramite `user-data-dir`.
- Rilevamento affidabile delle lezioni nel capitolo aperto tramite bounding box verticali.
- Modalità diagnostica che stampa inventario dei capitoli e delle righe individuate senza avviare la riproduzione.
- Logging dettagliato con riepilogo configurazione, tentativi di click, motivi di skip e tempi di attesa calcolati.

## Requisiti

1. Python 3.10 o superiore.
2. Dipendenze Python: `pip install -r requirements.txt`.
3. Installazione componenti Playwright: `playwright install`.

## Avvio rapido via CLI

```bash
python -m autoplay_lesson \
  --url "https://lms.pegaso.multiversity.click/videolezioni/0501906IUS15/" \
  --after-play 20 \
  --buffer 5 \
  --start-chapter 3 \
  --headless \
  --user-data-dir "C:/Users/<te>/AppData/Local/Google/Chrome/User Data"
```

Opzioni principali:

- `--url`: URL della pagina corso (obbligatorio).
- `--after-play`: attesa iniziale (secondi) dopo il click sulla lezione (default 20s).
- `--buffer`: buffer aggiuntivo a fine video (default 5s).
- `--max-wait`: tempo massimo da attendere per una singola lezione (default 3600s).
- `--start-chapter` / `--end-chapter`: filtra i capitoli da processare (1-based).
- `--headless`: esegue Playwright senza finestra grafica.
- `--slow`: ritardo in millisecondi tra le azioni Playwright (utile per debugging visivo).
- `--user-data-dir`: directory del profilo Chrome da riutilizzare (default: `~/.config/autoplay-lesson/chrome-profile`).
- `--no-chrome-profile`: disattiva l'uso del profilo persistente.
- `--diagnose`: modalità diagnostica, non avvia la riproduzione ma stampa inventario completo di capitoli/lezioni.

Il comando stampa subito il riepilogo della configurazione attiva e salva lo stato della riproduzione in `.state.json` per poter riprendere dall'ultima lezione completata.

## DarkPegaso Control Center (GUI desktop)

È disponibile un client desktop basato su **CustomTkinter** con sidebar, dashboard riepilogativa, pannello configurazione e console log. Per avviarlo:

```bash
python -m autoplay_lesson.client.main
```

Caratteristiche principali della finestra:

- Sidebar per passare rapidamente da Dashboard, Configurazione, Stato & Log e Guida rapida.
- Pulsante centrale **AVVIA AUTOMAZIONE** / **FERMA BOT** con log immediato nel pannello sottostante.
- Barra di progresso con percentuale/ETA e console log monospace con colori distinti per info, successi, avvisi ed errori.
- Schede di stato avanzate (lezioni completate, tempo medio, lezione attuale) nel tab "Stato & Log".
- Form di configurazione con salvataggio su `config.json` (username, password, modalità corso, velocità ed opzioni aggiuntive).

Tutte le impostazioni salvate vengono ricaricate automaticamente all'avvio successivo. Il client non richiede più servizi esterni (licenze/API) e può quindi essere eseguito completamente offline.

Per chiudere rapidamente l'applicazione puoi premere **Esc** o selezionare "Esci" dalla sidebar.

## Creare l'eseguibile Windows (.exe)

Per distribuire il client come applicazione Windows autonoma puoi utilizzare **PyInstaller**:

1. Prepara un ambiente virtuale e installa le dipendenze:

   ```bash
   py -m venv .venv
   .venv\\Scripts\\activate
   pip install --upgrade pip
   pip install -r requirements.txt pyinstaller
   ```

2. Genera l'eseguibile:

   ```bash
   pyinstaller \
     --name DarkPegaso \
     --windowed \
     --onefile \
     autoplay_lesson\\autoplay_lesson\\client\\main.py
   ```

   > Se vuoi un'icona personalizzata convertila in formato `.ico` (es. con Inkscape o ImageMagick) e aggiungi l'opzione `--icon percorso\\logo.ico`.

3. Il file `dist/DarkPegaso.exe` è pronto per essere distribuito. Mantieni accanto eventuali file di configurazione (`config.json`) se vuoi fornire preset precompilati.

Per ripetere la build da zero elimina le cartelle `build/`, `dist/` e il file `.spec` generato da PyInstaller.

## Modalità diagnostica

Con `--diagnose` (o spunta "Diagnostica" dalla GUI) il bot apre il capitolo richiesto, attende il rendering e stampa nel log:

- Numero totale di capitoli e rispettive posizioni verticali.
- Elenco delle righe `cursor-pointer` comprese tra `y_min` e `y_max` del capitolo.
- Per le prime 5 righe: titolo, durata raw, progress rilevato, bounding box e decisione (PLAY/SKIP) con motivazione.
- Riepilogo finale di righe trovate, valide e scartate.

Questa modalità è utile per tarare i selettori o verificare eventuali modifiche del layout.

## Rilevamento lezioni

Dopo il click sul capitolo il bot attende `lesson_render_wait` (default 5.5s) e calcola l'intervallo verticale da analizzare (`y_min` header capitolo corrente, `y_max` header successivo). Nel range vengono processate tutte le righe `cursor-pointer`:

- Titolo ricavato da `div.mb-2` / `span.font-semibold`.
- Durata trovata tramite regex `mm:ss` o `h:mm:ss`.
- Percentuale da `div.w-1/12.text-xs.md:text-xs` o fallback dal testo della riga.
- Skip automatico per titoli contenenti "Test di fine lezione" o "Dispensa" (case-insensitive) e per progress >= soglia configurata.

Ogni click sulla riga è soggetto a retry (fino a 3 tentativi con backoff esponenziale) e il log riporta tentativi ed eventuali errori.

## Tempi di attesa

Per ogni lezione valida vengono loggati e rispettati:

- 20 secondi fissi post-click (`after-play`).
- L'eventuale residuo della durata (durata - `after-play`).
- Un buffer aggiuntivo configurabile (`buffer`).
- Limite massimo (`max_wait`) per evitare loop infiniti.

## Gestione profilo Chrome

Di default viene usato Playwright Chromium con `channel="chrome"` e il profilo persistente specificato in `--user-data-dir` (di default `~/.config/autoplay-lesson/chrome-profile`). Per riutilizzare il tuo profilo Windows imposta ad esempio:

```
--user-data-dir "C:/Users/<nome>/AppData/Local/Google/Chrome/User Data"
```

Puoi disattivare questo comportamento con `--no-chrome-profile` oppure togliendo la spunta dalla GUI.

## File di stato

Il file `.state.json` viene aggiornato dopo ogni lezione riprodotta con capitolo e titolo correnti. In caso di riavvio il bot continua dal capitolo/lezione salvati, saltando automaticamente ciò che risulta completato (progress >= soglia).

## Licenza e note etiche

Utilizzare lo strumento nel rispetto dei Termini di Servizio della piattaforma. L'automazione non esegue test o quiz e non aggira meccanismi di sicurezza.

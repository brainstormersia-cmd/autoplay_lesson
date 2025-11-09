# Autoplay Lessons

Script Python basato su Playwright per riprodurre in sequenza le lezioni di un corso online.

## Requisiti

- Python 3.10+
- [Playwright](https://playwright.dev/python/) installato e inizializzato (`pip install playwright` e `playwright install`)

## Utilizzo rapido

```bash
python autoplay_lessons.py \
  --url "https://lms.pegaso.multiversity.click/videolezioni/0501906IUS15/" \
  --after-play 20 \
  --buffer 5 \
  --start-chapter 18 \
  --end-chapter 22 \
  --log-file run.log
```

> Suggerimento: la soglia di default (`--progress-threshold 100`) salta esclusivamente le lezioni al 100%.
> Se vuoi ignorare anche quelle già avviate imposta `--progress-threshold 0`.

Opzioni principali:

- `--url`: URL della pagina corso.
- `--after-play`: secondi da attendere subito dopo il click sulla lezione (default 20).
- `--buffer`: buffer aggiuntivo a fine video (default 5).
- `--max-wait`: massima attesa per una singola lezione.
- `--headless`: esegue Playwright in headless mode.
- `--start-chapter` / `--end-chapter`: limita il range dei capitoli.
- `--whitelist` / `--blacklist`: regex (ripetibili) per includere o escludere lezioni.
- `--selectors-json`: file JSON con override dei selettori.
- `--state-file`: percorso del file di stato per la ripresa (`.state.json` di default).
- `--log-file`: abilita logging su file oltre che su console.
- `--mute`: prova a mutare il player dopo il click.
- `--progress-threshold`: salta le lezioni che mostrano un progresso percentuale maggiore o uguale alla soglia indicata (default 100 per saltare solo quelle al 100%).
- `--gui`: apre una mini interfaccia per scegliere i capitoli di inizio/fine prima di avviare Playwright.

Lanciare `python autoplay_lessons.py --help` per la lista completa delle opzioni.

## Modalità GUI

Esegui `python autoplay_lessons.py --gui` per aprire una finestra che permette di inserire subito l'URL del corso e l'intervallo dei capitoli. Dopo aver premuto **Avvia**, lo script apre la pagina, verifica da log di averla raggiunta e calcola la durata stimata prima di avviare l'autoplay.

## Pianificazione e durata stimata

All'avvio, lo script espande i capitoli disponibili, legge le durate delle lezioni e stampa un riepilogo del numero di lezioni da riprodurre, dei capitoli coinvolti e del tempo totale previsto. I log elencano anche il dettaglio capitolo per capitolo. Se non è stato scelto un intervallo a monte e il terminale è interattivo, dopo la scansione viene chiesto di selezionare l'intervallo desiderato prima di proseguire. Le lezioni già completate (div con classe `w-1/12 text-xs md:text-xs` che mostra `100%`) o oltre la soglia `--progress-threshold` vengono escluse automaticamente dal conteggio.

## File di stato

Dopo ogni lezione completata il bot aggiorna un file `.state.json` con capitolo e titolo dell'ultima lezione terminata. Alla successiva esecuzione il bot salterà automaticamente le lezioni già completate e riprenderà dalla successiva.

## Override dei selettori

È possibile fornire un file JSON con i selettori da sovrascrivere, ad esempio:

```json
{
  "chapter_title": "div.chapter-header",
  "lesson_title": "div.lesson-title",
  "duration": "span.lesson-duration"
}
```

Passare il percorso del file tramite `--selectors-json path/to/selectors.json`.

## Logging ed errori

Il logger stampa data/ora, livello, azione svolta e risultati. Se impostato `--log-file`, i messaggi vengono replicati anche su file. In caso di errore critico viene salvato uno screenshot in `./errors/` (nome `error_YYYYMMDD_HHMMSS.png`).

## Etica e limiti

Utilizzare lo script solo nel rispetto dei Termini di Servizio della piattaforma. Non automatizza test o quiz.

## Changelog sintetico

- Implementata CLI completa con configurazione centralizzata.
- Supporto a salvataggio stato e ripresa automatica.
- Logging strutturato con screenshot in caso di errore.
- Parsing robusto delle durate (h:mm:ss, mm:ss) e skip delle lezioni completate, inclusi gli indicatori Pegaso `100%`.
- Retry con backoff su click e apertura capitoli, auto-scroll progressivo.
- Modalità GUI opzionale e riepilogo preventivo della durata stimata prima dell'avvio.
- Prompt interattivo per URL e selezione capitoli con log dettagliato del piano per capitolo.

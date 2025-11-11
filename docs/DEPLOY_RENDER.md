# Distribuire Autoplay Lesson su Render

Questa guida spiega come eseguire il bot DarkPegaso/Autoplay Lesson su un server esterno gestito da [Render](https://render.com).
Le istruzioni valgono sia per un **Background Worker** (esecuzione continua) sia per un **Cron Job** (esecuzioni programmate).

## 1. Preparazione del repository

1. Clona il progetto o crea un fork su GitHub/GitLab.
2. Aggiorna `config.json` con le credenziali del portale e l'URL del corso da automatizzare (vedi esempio più sotto).
3. Effettua il commit dei file necessari al deploy (`requirements.txt`, script Python, eventuale `render.yaml`).

### Esempio di `config.json`

```json
{
  "url": "https://lms.pegaso.multiversity.click/videolezioni/0501906IUS15/",
  "username": "nome.cognome",
  "password": "password-super-segreta",
  "mode": "courses+quizzes",
  "after_play": 20,
  "buffer": 5,
  "headless": true
}
```

Nel deploy remoto è consigliabile:

- Tenere `headless` impostato su `true`.
- Usare percorsi temporanei per `user_data_dir` (Render cancella il filesystem a ogni build).
- Spostare le credenziali in **Environment Variables** invece di lasciarle nel repository.

## 2. Configurare le variabili d'ambiente

Su Render (Dashboard → Servizio → **Environment**), definisci almeno:

- `DARKPEGASO_URL`: URL del corso.
- `DARKPEGASO_USERNAME`: username Pegaso.
- `DARKPEGASO_PASSWORD`: password Pegaso.
- `DARKPEGASO_MODE`: `courses`, `quizzes` o `courses+quizzes`.
- `PLAYWRIGHT_BROWSERS_PATH`: impostalo a `0` per installare i browser Playwright nella directory del progetto.

Nel file `config.json` sostituisci i valori sensibili con placeholder, poi nel comando di avvio richiama le variabili:

```bash
python -m autoplay_lesson \
  --url "$DARKPEGASO_URL" \
  --username "$DARKPEGASO_USERNAME" \
  --password "$DARKPEGASO_PASSWORD" \
  --mode "$DARKPEGASO_MODE" \
  --headless \
  --no-chrome-profile
```

L'opzione `--no-chrome-profile` evita di cercare directory non presenti nel filesystem effimero di Render.

## 3. Creazione del servizio su Render

1. Nel dashboard Render clicca **New +** → **Background Worker** (oppure **Cron Job**).
2. Collega il repository Git dove hai pubblicato il progetto.
3. Imposta il **Runtime** su **Python** (versione 3.10+).
4. Inserisci i comandi di build ed esecuzione:

   - **Build Command**
     ```bash
     pip install --upgrade pip
     pip install -r requirements.txt
     playwright install --with-deps chromium
     ```

   - **Start Command**
     ```bash
     python -m autoplay_lesson \
       --url "$DARKPEGASO_URL" \
       --username "$DARKPEGASO_USERNAME" \
       --password "$DARKPEGASO_PASSWORD" \
       --mode "$DARKPEGASO_MODE" \
       --headless \
       --no-chrome-profile \
       --log-level info
     ```

5. (Opzionale) Attiva un **Persistent Disk** se vuoi conservare `state.json` tra le esecuzioni. Montalo, ad esempio, su `/data` e aggiungi l'opzione `--state-path /data/state.json` al comando di avvio.
6. Salva; Render effettuerà il primo deploy automatico.

## 4. Esecuzione programmata (Cron Job)

Se preferisci avviare il bot a orari specifici:

1. Scegli **Cron Job** al passo di creazione.
2. Specifica la schedulazione (es. `0 6 * * *` per lanciare ogni giorno alle 06:00 UTC).
3. Usa lo stesso Build/Start Command illustrato sopra.

## 5. Monitoraggio e troubleshooting

- Controlla la sezione **Logs** di Render per visualizzare il flusso generato da Autoplay Lesson.
- Se Playwright segnala dipendenze mancanti, assicurati che `playwright install --with-deps chromium` sia presente nel comando di build.
- Per debuggare localmente gli stessi comandi di Render puoi eseguire:

  ```bash
  pip install -r requirements.txt
  PLAYWRIGHT_BROWSERS_PATH=0 playwright install --with-deps chromium
  python -m autoplay_lesson --url "$DARKPEGASO_URL" --headless --no-chrome-profile
  ```

## 6. Variante con Docker personalizzato

Se preferisci controllare al 100% le dipendenze puoi creare un file `render.yaml` con un servizio Docker custom:

```yaml
services:
  - type: worker
    name: darkpegaso-worker
    env: docker
    dockerfilePath: ./Dockerfile
    autoDeploy: true
    envVars:
      - key: DARKPEGASO_URL
        sync: false
      - key: DARKPEGASO_USERNAME
        sync: false
      - key: DARKPEGASO_PASSWORD
        sync: false
      - key: DARKPEGASO_MODE
        value: courses+quizzes
```

Il `Dockerfile` può basarsi su `mcr.microsoft.com/playwright/python:v1.43.0-focal` (già completo di Chromium e dipendenze).

---

Seguendo questi passaggi il bot verrà eseguito in modo affidabile su Render, con credenziali protette tramite variabili d'ambiente e log accessibili dal pannello web.

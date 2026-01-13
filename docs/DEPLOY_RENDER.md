# Distribuire Autoplay Lesson su Render

Questa guida spiega come eseguire il bot DarkPegaso/Autoplay Lesson su un server esterno gestito da [Render](https://render.com).
Le istruzioni valgono sia per un **Background Worker** (esecuzione continua) sia per un **Cron Job** (esecuzioni programmate).

## 0. Esecuzione rapida da terminale (qualsiasi VPS/Linux)

Se vuoi provare il bot su un server remoto tradizionale (Hetzner, OVH, Aruba, ecc.) senza pannelli grafici, puoi usare i seguenti comandi da copiare e incollare. L'esempio presume una distribuzione Ubuntu/Debian già aggiornata.

```bash
# 1) Installa i pacchetti di base
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git

# 2) Clona il repository e crea un ambiente virtuale
git clone https://github.com/<tuo-account>/autoplay_lesson.git
cd autoplay_lesson
python3 -m venv .venv
source .venv/bin/activate

# 3) Installa dipendenze Python e browser Playwright
pip install --upgrade pip
pip install -r requirements.txt
PLAYWRIGHT_BROWSERS_PATH=0 playwright install --with-deps chromium

# 4) Esporta le variabili d'ambiente con le tue credenziali
export DARKPEGASO_URL="https://..."
export DARKPEGASO_USERNAME="nome.cognome"
export DARKPEGASO_PASSWORD="password-super-segreta"
export DARKPEGASO_MODE="courses+quizzes"

# 5) Avvia il bot in modalità headless
python -m autoplay_lesson \
  --url "$DARKPEGASO_URL" \
  --username "$DARKPEGASO_USERNAME" \
  --password "$DARKPEGASO_PASSWORD" \
  --mode "$DARKPEGASO_MODE" \
  --headless \
  --no-chrome-profile \
  --log-level info
```

Suggerimenti rapidi:

- Se vuoi che il processo continui anche dopo aver chiuso la sessione SSH, avvia il comando con `nohup` oppure utilizza `tmux`/`screen`.
- Per rendere permanenti le variabili puoi salvarle in `~/.bashrc` o, meglio, in un file `.env` da caricare con `source .env`.

---

## 0 bis. Setup dettagliato su Ubuntu Server (20.04/22.04)

La maggior parte dei provider (Hetzner, Aruba, OVH, IONOS, ecc.) offre VPS Ubuntu già pronte. Questa checklist ripete i passaggi principali con qualche accorgimento in più per ambienti produttivi.

1. **Aggiorna pacchetti di sistema e dipendenze fondamentali**:

   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install -y python3 python3-venv python3-pip git build-essential libnss3 libatk1.0-0 libatk-bridge2.0-0 libdrm2
   ```

   Le librerie aggiuntive (`libnss3`, `libatk*`, `libdrm2`) evitano errori di avvio di Chromium in headless.

2. **Crea un utente dedicato (facoltativo ma consigliato)**:

   ```bash
   sudo adduser darkpegaso
   sudo usermod -aG sudo darkpegaso
   sudo su - darkpegaso
   ```

3. **Clona il repository, prepara l'ambiente virtuale e installa Playwright**:

   ```bash
   git clone https://github.com/<tuo-account>/autoplay_lesson.git
   cd autoplay_lesson
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   PLAYWRIGHT_BROWSERS_PATH=0 playwright install --with-deps chromium
   ```

   L'opzione `--with-deps` installerà automaticamente eventuali pacchetti di sistema mancanti (ti verrà chiesta la password `sudo`).

4. **Prepara un file `.env` con le credenziali** (salvato nella home dell'utente):

   ```bash
   cat <<'EOF' > ~/.env.darkpegaso
   export DARKPEGASO_URL="https://..."
   export DARKPEGASO_USERNAME="nome.cognome"
   export DARKPEGASO_PASSWORD="password-super-segreta"
   export DARKPEGASO_MODE="courses+quizzes"
   EOF
   chmod 600 ~/.env.darkpegaso
   ```

5. **Avvia il bot in foreground per un test rapido**:

   ```bash
   cd ~/autoplay_lesson
   source .venv/bin/activate
   source ~/.env.darkpegaso
   python -m autoplay_lesson --url "$DARKPEGASO_URL" --username "$DARKPEGASO_USERNAME" \
     --password "$DARKPEGASO_PASSWORD" --mode "$DARKPEGASO_MODE" --headless --no-chrome-profile --log-level info
   ```

6. **(Opzionale) Registra un servizio `systemd`** per riavvia automatico e logging centralizzato:

   ```bash
   sudo tee /etc/systemd/system/darkpegaso.service > /dev/null <<'EOF'
   [Unit]
   Description=DarkPegaso Autoplay Lesson
   After=network.target

   [Service]
   WorkingDirectory=/home/darkpegaso/autoplay_lesson
   EnvironmentFile=/home/darkpegaso/.env.darkpegaso
   ExecStart=/home/darkpegaso/autoplay_lesson/.venv/bin/python -m autoplay_lesson \
     --url ${DARKPEGASO_URL} \
     --username ${DARKPEGASO_USERNAME} \
     --password ${DARKPEGASO_PASSWORD} \
     --mode ${DARKPEGASO_MODE} \
     --headless \
     --no-chrome-profile \
     --log-level info
   Restart=on-failure
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   EOF
   sudo systemctl daemon-reload
   sudo systemctl enable --now darkpegaso.service
   sudo journalctl -u darkpegaso.service -f
   ```

7. **Proteggi il server** (consigliato): abilita firewall UFW o regole cloud e genera chiavi SSH invece di usare password.

Con questo flusso ottieni un'installazione persistente e riavviabile automaticamente ogni volta che il server viene acceso.

---

## 1. Preparazione del repository

1. Clona il progetto o crea un fork su GitHub/GitLab.
2. Aggiorna `config.json` con le credenziali del portale e l'URL del corso da automatizzare (vedi esempio più sotto).
3. Effettua il commit dei file necessari al deploy (`requirements.txt`, script Python, eventuale `render.yaml`).

### Esempio di `config.json`

```json
{
  "url": "https://www.coursera.org/learn/high-stakes-leadership/lecture/xKTQO/deepwater-horizon-setting-the-stage",
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

## 7. Setup rapido su Hetzner Cloud (Ubuntu 22.04)

Questi passi riassumono come mettere online il bot su una VPS Hetzner appena creata con Ubuntu 22.04 LTS:

1. **Crea la macchina**: nel pannello Hetzner Cloud scegli l'immagine "Ubuntu 22.04" e crea un server CX (2 GB RAM sono sufficienti per Chromium headless).
2. **Accedi via SSH**: `ssh root@<ip-server>` (o con l'utente configurato).
3. **Aggiungi un utente dedicato (opzionale ma consigliato)**:
   ```bash
   adduser darkpegaso
   usermod -aG sudo darkpegaso
   su - darkpegaso
   ```
4. **Segui i comandi della sezione 0** per installare Python, clonare il repo e configurare l'ambiente virtuale.
5. **Crea un file `.env`** per conservare le credenziali in modo sicuro:
   ```bash
   cat <<'EOF' > ~/.env.darkpegaso
   export DARKPEGASO_URL="https://..."
   export DARKPEGASO_USERNAME="nome.cognome"
   export DARKPEGASO_PASSWORD="password-super-segreta"
   export DARKPEGASO_MODE="courses+quizzes"
   EOF
   chmod 600 ~/.env.darkpegaso
   ```
6. **Avvio manuale**:
   ```bash
   cd ~/autoplay_lesson
   source .venv/bin/activate
   source ~/.env.darkpegaso
   python -m autoplay_lesson --url "$DARKPEGASO_URL" --username "$DARKPEGASO_USERNAME" \
     --password "$DARKPEGASO_PASSWORD" --mode "$DARKPEGASO_MODE" --headless --no-chrome-profile
   ```
7. **Esecuzione come servizio systemd (facoltativa)**:
   ```bash
   sudo tee /etc/systemd/system/darkpegaso.service > /dev/null <<'EOF'
   [Unit]
   Description=DarkPegaso Autoplay Lesson
   After=network.target

   [Service]
   WorkingDirectory=/home/darkpegaso/autoplay_lesson
   EnvironmentFile=/home/darkpegaso/.env.darkpegaso
   ExecStart=/home/darkpegaso/autoplay_lesson/.venv/bin/python -m autoplay_lesson \
     --url ${DARKPEGASO_URL} \
     --username ${DARKPEGASO_USERNAME} \
     --password ${DARKPEGASO_PASSWORD} \
     --mode ${DARKPEGASO_MODE} \
     --headless \
     --no-chrome-profile \
     --log-level info
   Restart=on-failure
   User=darkpegaso

   [Install]
   WantedBy=multi-user.target
   EOF
   sudo systemctl daemon-reload
   sudo systemctl enable --now darkpegaso.service
   sudo journalctl -u darkpegaso.service -f
   ```

Con questa configurazione il bot parte automaticamente all'avvio del server e puoi monitorarne i log con `journalctl`. Ricorda di aggiornare Playwright (`playwright install --with-deps chromium`) dopo eventuali aggiornamenti del progetto.

---

Seguendo questi passaggi il bot verrà eseguito in modo affidabile su Render, con credenziali protette tramite variabili d'ambiente e log accessibili dal pannello web.

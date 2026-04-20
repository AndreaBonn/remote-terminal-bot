# TelegramTerminalBot — Documento di Specifica del Progetto

> **Versione:** 1.0  
> **Target:** Xubuntu (Linux)  
> **Linguaggio:** Python 3.10+  
> **Scopo:** Controllare terminali di più PC da remoto tramite un bot Telegram, con sessione persistente e gestione multi-PC.

---

## 1. Panoramica del Sistema

Il sistema permette all'utente di inviare comandi terminale da Telegram e ricevere l'output direttamente nella chat, in modo iterativo e con la directory corrente mantenuta tra un comando e l'altro. Più PC possono essere collegati allo stesso bot; l'utente seleziona il PC attivo tramite un comando dedicato.

### 1.1 Componenti principali

```
[Utente su Telegram]
        │
        ▼
[Bot Telegram (API Telegram)]
        │
        ├──► [Script Python — PC "desktop"]
        │         └── subprocess shell persistente
        │
        └──► [Script Python — PC "laptop"]
                  └── subprocess shell persistente
```

- **Un solo bot Telegram** condiviso da tutti i PC.
- **Uno script Python per PC**, ognuno con il proprio nome configurabile.
- **Nessun server intermedio**: la comunicazione avviene direttamente via API Telegram (long polling).
- **Stato "PC attivo"**: ogni PC riceve tutti i messaggi, ma esegue i comandi solo se è il PC attualmente selezionato.

---

## 2. Requisiti Funzionali

### 2.1 Comandi Telegram

| Comando | Descrizione |
|---|---|
| `/activate <nome_pc>` | Seleziona il PC su cui eseguire i comandi successivi |
| `/list` | Mostra la lista dei PC online con nome, hostname e timestamp ultimo heartbeat |
| `/status` | Mostra il PC attualmente attivo e la directory corrente su quel PC |
| `/cancel` | Termina il processo in esecuzione sul PC attivo (se bloccato o lento) |
| `/help` | Mostra l'elenco dei comandi disponibili |

### 2.2 Esecuzione comandi

- Qualsiasi messaggio che **non inizia con `/`** viene trattato come un comando shell da eseguire sul PC attivo.
- Se nessun PC è selezionato, il bot risponde con un messaggio di errore che invita a usare `/activate`.
- La **directory corrente è mantenuta** tra un comando e l'altro (sessione shell persistente).
- L'output viene restituito come messaggio Telegram, formattato in blocco di codice monospace.
- Se l'output supera i **4096 caratteri** (limite Telegram), viene spezzato in più messaggi consecutivi.
- Se il comando non produce output, viene risposto con `✅ Comando eseguito (nessun output)`.
- I comandi vengono eseguiti con un **timeout configurabile** (default: 30 secondi). Allo scadere del timeout il processo viene terminato e l'utente viene notificato.

### 2.3 Gestione multi-PC

- Ogni PC ha un **nome univoco** configurato nel file `.env` o in cima allo script (es. `MACHINE_NAME=desktop`).
- All'avvio, ogni PC invia un messaggio nella chat: `🟢 [desktop] è online`.
- Allo spegnimento (SIGTERM/SIGINT), ogni PC invia: `🔴 [desktop] è offline`.
- Ogni PC invia un **heartbeat silenzioso** ogni 60 secondi per aggiornare il proprio stato interno (non visibile nella chat, solo tracciato localmente).
- Il comando `/list` mostra tutti i PC che hanno inviato un heartbeat negli ultimi 120 secondi.
- Lo stato "PC attivo" è **globale per chat**: se l'utente seleziona `desktop`, tutti i comandi successivi vanno a `desktop` indipendentemente da quale dispositivo usa Telegram.

### 2.4 Sicurezza

- Il bot risponde **solo al `CHAT_ID` autorizzato**, configurato nel file `.env`.
- Qualsiasi messaggio proveniente da un `chat_id` diverso viene silenziosamente ignorato (nessuna risposta).
- I comandi vengono eseguiti con i **privilegi dell'utente che esegue lo script** (non root, a meno che lo script non sia lanciato come root).

---

## 3. Requisiti Non Funzionali

- **Affidabilità:** Lo script deve riavviarsi automaticamente in caso di errore non gestito (gestito tramite systemd, vedi sezione 7).
- **Latenza:** Il tempo tra l'invio del comando e la ricezione dell'output deve essere < 2 secondi per comandi rapidi (escluso il tempo di esecuzione del comando stesso).
- **Portabilità:** Il codice deve girare su qualsiasi distribuzione Linux con Python 3.10+ senza modifiche.
- **Manutenibilità:** Configurazione centralizzata in un file `.env`, nessuna costante hardcoded nel codice.

---

## 4. Architettura Tecnica

### 4.1 Struttura del progetto

```
telegram-terminal-bot/
├── bot.py                  # Entry point principale
├── config.py               # Lettura configurazione da .env
├── shell_session.py        # Gestione sessione shell persistente
├── state_manager.py        # Gestione stato "PC attivo" condiviso
├── handlers.py             # Handler dei comandi e messaggi Telegram
├── utils.py                # Funzioni di utilità (split messaggi, formattazione)
├── .env                    # Configurazione (NON committare su git)
├── .env.example            # Template configurazione
├── requirements.txt        # Dipendenze Python
├── install.sh              # Script di installazione automatica
└── systemd/
    └── telegram-terminal-bot.service  # Unit file systemd
```

### 4.2 Dipendenze Python

```
python-telegram-bot==20.x   # Libreria bot Telegram (versione async)
python-dotenv               # Lettura file .env
```

Nessuna altra dipendenza esterna. Tutto il resto usa librerie standard Python (`subprocess`, `asyncio`, `os`, `signal`, `logging`).

### 4.3 Sessione shell persistente (`shell_session.py`)

La sessione shell persistente è il cuore del sistema. Viene implementata aprendo **un processo `bash` che rimane vivo** per tutta la durata dello script, comunicando via `stdin`/`stdout`/`stderr`.

**Meccanismo:**

1. All'avvio viene aperto un processo `bash` con `subprocess.Popen`.
2. Per ogni comando ricevuto, si scrive su `stdin` del processo bash:
   ```
   <comando>\necho "___END_MARKER___$?"\n
   ```
3. Si legge `stdout` riga per riga finché non si incontra la riga contenente `___END_MARKER___`.
4. Il codice di uscita del comando viene estratto dalla marker line.
5. `stderr` viene letto e allegato all'output se presente.
6. La directory corrente viene aggiornata eseguendo `pwd` dopo ogni comando.

**Gestione timeout:**

- Ogni lettura dell'output ha un timeout (default 30s, configurabile).
- Allo scadere del timeout, il processo bash viene terminato (`SIGKILL`) e ricreato.
- L'utente riceve: `⚠️ Timeout: il comando ha superato i 30 secondi ed è stato terminato.`

**Gestione `/cancel`:**

- Invia `SIGINT` al gruppo di processi figlio del bash (`os.killpg`).
- Non termina la sessione bash stessa, solo il processo figlio in esecuzione.

### 4.4 Gestione stato multi-PC (`state_manager.py`)

Lo stato "quale PC è attivo" deve essere condiviso tra tutti gli script in esecuzione sui vari PC. Viene usato **Telegram stesso come stato condiviso**, senza server esterni.

**Approccio:** file JSON locale sincronizzato via **messaggio Telegram speciale**.

- Ogni PC mantiene localmente un file `state.json` con:
  ```json
  {
    "active_pc": "desktop",
    "last_updated": "2025-01-01T12:00:00"
  }
  ```
- Quando l'utente invia `/activate desktop`, **tutti i PC** ricevono il comando (sono tutti in long polling).
- Ogni PC aggiorna il proprio `state.json` locale.
- In questo modo non serve nessun server centrale: Telegram fa da broadcast.

**Heartbeat e `/list`:**

- Ogni PC mantiene localmente un dizionario `{nome_pc: ultimo_heartbeat}`.
- I heartbeat vengono scambiati tramite **messaggi speciali silenziosi** (non visibili all'utente) inviati al bot stesso con un prefisso speciale es. `__HB__desktop__`.
- Il bot li filtra e aggiorna il registro locale senza mostrarli in chat.
- `/list` legge il registro e mostra solo i PC con heartbeat recente (< 120s).

> **Nota implementativa:** Se la complessità del heartbeat via Telegram è eccessiva, una soluzione alternativa accettabile è che `/list` mostri solo i PC "noti" (configurati) senza indicazione di online/offline, e l'utente verifichi manualmente.

### 4.5 Handlers Telegram (`handlers.py`)

Implementati con `python-telegram-bot` v20 in modalità **async**.

```python
# Handler principali
async def handle_activate(update, context)   # /activate <nome>
async def handle_list(update, context)       # /list
async def handle_status(update, context)     # /status
async def handle_cancel(update, context)     # /cancel
async def handle_help(update, context)       # /help
async def handle_command(update, context)    # qualsiasi altro messaggio
```

Ogni handler verifica prima che `update.effective_chat.id == AUTHORIZED_CHAT_ID`.

### 4.6 Formattazione output (`utils.py`)

- Output wrappato in triple backtick per monospace: ` ```\n<output>\n``` `
- Se l'output supera 4096 caratteri, viene diviso in chunk da 4000 caratteri (con 96 caratteri di margine per la formattazione).
- Ogni chunk viene inviato come messaggio separato.
- Il codice di uscita viene mostrato solo se diverso da 0: `⚠️ Exit code: 1`

---

## 5. File di Configurazione

### 5.1 `.env`

```env
# Token del bot Telegram (ottenuto da @BotFather)
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ

# Chat ID autorizzato (il tuo account Telegram)
# Ottieni il tuo chat_id scrivendo a @userinfobot
AUTHORIZED_CHAT_ID=123456789

# Nome univoco di questo PC
MACHINE_NAME=desktop

# Timeout comandi in secondi
COMMAND_TIMEOUT=30

# Intervallo heartbeat in secondi
HEARTBEAT_INTERVAL=60
```

### 5.2 `.env.example`

Copia di `.env` con valori placeholder, da committare su git al posto del `.env` reale.

---

## 6. Flusso di Esecuzione — Diagramma

```
Avvio script
    │
    ├── Legge configurazione da .env
    ├── Avvia sessione bash persistente
    ├── Invia messaggio "🟢 [nome_pc] è online"
    ├── Avvia loop heartbeat (background task asyncio)
    └── Avvia bot Telegram (Application.run_polling)
            │
            ▼
    Messaggio ricevuto
            │
            ├── chat_id non autorizzato? → ignora silenziosamente
            │
            ├── /activate <nome>
            │       ├── Aggiorna state.json locale
            │       └── Risponde "✅ PC attivo: <nome>"
            │
            ├── /list
            │       └── Mostra PC con heartbeat recente
            │
            ├── /status
            │       └── Mostra PC attivo + directory corrente
            │
            ├── /cancel
            │       ├── Questo PC è attivo?
            │       │       ├── Sì → SIGINT al processo figlio
            │       │       └── No → ignora
            │       └── Risponde "🛑 Processo terminato"
            │
            └── Testo libero (comando shell)
                    ├── Nessun PC attivo? → "⚠️ Nessun PC selezionato. Usa /activate"
                    ├── Questo PC è attivo?
                    │       ├── No → ignora silenziosamente
                    │       └── Sì → esegui comando nella sessione bash
                    │               ├── Invia output (formattato, spezzato se lungo)
                    │               └── Aggiorna directory corrente
                    └── Fine
```

---

## 7. Installazione e Deployment

### 7.1 Script di installazione (`install.sh`)

Lo script deve:

1. Verificare che Python 3.10+ sia installato.
2. Creare un virtualenv in `~/.telegram-terminal-bot/venv`.
3. Installare le dipendenze da `requirements.txt`.
4. Copiare il file `.env.example` in `.env` se non esiste già.
5. Installare il service systemd (vedi 7.2).
6. Stampare istruzioni per configurare `.env`.

### 7.2 Systemd service (`systemd/telegram-terminal-bot.service`)

```ini
[Unit]
Description=Telegram Terminal Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=%i
WorkingDirectory=/home/%i/telegram-terminal-bot
ExecStart=/home/%i/.telegram-terminal-bot/venv/bin/python bot.py
Restart=always
RestartSec=10
EnvironmentFile=/home/%i/telegram-terminal-bot/.env

[Install]
WantedBy=multi-user.target
```

### 7.3 Comandi di gestione

```bash
# Abilitare e avviare
sudo systemctl enable telegram-terminal-bot@$USER
sudo systemctl start telegram-terminal-bot@$USER

# Verificare stato
sudo systemctl status telegram-terminal-bot@$USER

# Leggere log
journalctl -u telegram-terminal-bot@$USER -f
```

### 7.4 Setup iniziale (manuale, una volta sola)

```bash
# 1. Clonare/copiare il progetto
cd ~
git clone <repo> telegram-terminal-bot  # oppure copia manuale

# 2. Eseguire lo script di installazione
cd telegram-terminal-bot
chmod +x install.sh
./install.sh

# 3. Configurare .env
nano .env
# → Inserire TELEGRAM_BOT_TOKEN, AUTHORIZED_CHAT_ID, MACHINE_NAME

# 4. Avviare il servizio
sudo systemctl start telegram-terminal-bot@$USER

# 5. Ripetere su ogni PC con MACHINE_NAME diverso
```

---

## 8. Gestione degli Errori

| Scenario | Comportamento atteso |
|---|---|
| Comando con exit code != 0 | Output mostrato normalmente + `⚠️ Exit code: N` in fondo |
| Comando che supera il timeout | Processo terminato, messaggio di timeout all'utente, sessione bash ricreata |
| Sessione bash morta inaspettatamente | Rilevata al comando successivo, ricreata automaticamente, utente notificato |
| Errore di rete Telegram | `python-telegram-bot` gestisce il retry automaticamente |
| File `.env` mancante o incompleto | Lo script si interrompe con messaggio di errore chiaro |
| Messaggio Telegram > 4096 caratteri | Output spezzato in chunk e inviato in più messaggi |
| `/activate` con nome PC inesistente | Viene accettato comunque (il PC potrebbe essere offline temporaneamente) |

---

## 9. Logging

- Logging su `stdout` (catturato da journalctl se avviato via systemd).
- Livello default: `INFO`.
- Formato: `[2025-01-01 12:00:00] [INFO] [desktop] Comando ricevuto: ls -la`
- Ogni comando eseguito viene loggato con: chat_id, comando, exit code, durata.
- Gli errori critici vengono loggati a livello `ERROR` con traceback completo.

---

## 10. Considerazioni di Sicurezza

- **Il bot esegue comandi arbitrari** con i privilegi dell'utente che lo esegue. Non eseguire mai lo script come root.
- Il `AUTHORIZED_CHAT_ID` è l'unica barriera di sicurezza: deve essere configurato correttamente.
- Il token bot **non deve essere mai committato su git**. Usare `.gitignore` per escludere `.env`.
- Considerare di aggiungere il file `.env` a `.gitignore` nel repository.
- Per ambienti più sicuri, è possibile aggiungere una whitelist di comandi consentiti (opzionale, non richiesto in questa versione).

---

## 11. Esempio di Utilizzo

```
Utente:   /list
Bot:      🖥️ PC Online:
          • desktop  (ultimo heartbeat: 5s fa)
          • laptop   (ultimo heartbeat: 23s fa)

Utente:   /activate desktop
Bot:      ✅ PC attivo: desktop

Utente:   pwd
Bot:      /home/mario

Utente:   cd /var/log && ls -la
Bot:      ```
          total 1024
          drwxrwxr-x  12 root  syslog  4096 Jan  1 12:00 .
          ...
          ```

Utente:   /status
Bot:      🖥️ PC attivo: desktop
          📁 Directory corrente: /var/log

Utente:   /activate laptop
Bot:      ✅ PC attivo: laptop

Utente:   pwd
Bot:      /home/mario

Utente:   /cancel
Bot:      🛑 Processo terminato
```

---

## 12. Vincoli e Limitazioni Note

- Telegram ha un limite di **30 messaggi al secondo** per bot; non rilevante per uso personale.
- I messaggi Telegram hanno un limite di **4096 caratteri**: gestito con lo split automatico.
- Comandi interattivi che richiedono input da tastiera (es. `sudo`, `vim`, `htop`) **non funzionano** in questa architettura. Per questi casi, usare `sudo -S` con password nel comando o configurare `NOPASSWD` in sudoers.
- Il long polling di `python-telegram-bot` introduce una latenza minima di ~0.5-1s per messaggio.
- In caso di riavvio del PC, lo stato `state.json` viene perso: l'utente deve rifare `/activate`.

---

*Fine del documento di specifica — v1.0*

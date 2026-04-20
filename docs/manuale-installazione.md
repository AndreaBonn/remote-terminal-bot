# Manuale di Installazione — Guida Passo Passo

> Guida completa per mettere in funzione Telegram Terminal Bot sul tuo PC, anche se non sei uno sviluppatore.

**[🇬🇧 Read in English](how-to-install.md)**

---

## Cosa Ti Serve

Prima di iniziare, assicurati di avere:

- Un computer con **Linux** (Ubuntu, Xubuntu, Debian o simili)
- Una connessione internet
- Un account **Telegram** sul telefono
- Circa 10 minuti di tempo

---

## Passo 1: Crea il Tuo Bot Telegram

1. Apri Telegram sul telefono
2. Cerca **@BotFather** e apri la chat
3. Invia il messaggio: `/newbot`
4. Scegli un **nome** per il bot (es. "Il Mio Terminale")
5. Scegli un **username** che finisca con `bot` (es. `il_mio_terminale_bot`)
6. BotFather risponde con un **token** — ha questo formato: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`
7. **Copia e salva questo token** — ti servirà al Passo 4

---

## Passo 2: Ottieni il Tuo Chat ID

1. Apri Telegram sul telefono
2. Cerca **@userinfobot** e apri la chat
3. Invia il messaggio: `/start`
4. Il bot risponde con il tuo **ID** — è un numero tipo `123456789`
5. **Copia e salva questo numero** — ti servirà al Passo 4

---

## Passo 3: Installa il Bot sul PC

Apri un terminale sul PC e lancia questi comandi uno alla volta:

### 3.1 Installa uv (gestore pacchetti Python)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Chiudi e riapri il terminale, poi verifica che funzioni:

```bash
uv --version
```

Dovresti vedere qualcosa come `uv 0.x.x`.

### 3.2 Scarica il bot

```bash
git clone https://github.com/AndreaBonn/remote-terminal-bot.git
cd remote-terminal-bot
```

### 3.3 Installa le dipendenze

```bash
uv sync
```

---

## Passo 4: Configura il Bot

### 4.1 Crea il file di configurazione

```bash
cp .env.example .env
```

### 4.2 Modifica la configurazione

```bash
nano .env
```

Compila i valori:

```env
TELEGRAM_BOT_TOKEN=incolla_il_token_del_passo_1
AUTHORIZED_CHAT_ID=incolla_il_tuo_id_del_passo_2
MACHINE_NAME=desktop
COMMAND_TIMEOUT=120
HEARTBEAT_INTERVAL=86400
```

**Spiegazione di ogni campo:**

| Campo | Cosa significa | Esempio |
|-------|---------------|---------|
| `TELEGRAM_BOT_TOKEN` | Il token che ti ha dato BotFather | `123456789:ABCdef...` |
| `AUTHORIZED_CHAT_ID` | Il tuo ID personale Telegram | `123456789` |
| `MACHINE_NAME` | Un nome breve per questo PC (minuscolo, senza spazi) | `desktop`, `laptop`, `server` |
| `COMMAND_TIMEOUT` | Secondi massimi di esecuzione per un comando | `120` (2 minuti) |
| `HEARTBEAT_INTERVAL` | Ogni quanti secondi il bot segnala di essere vivo | `86400` (una volta al giorno, praticamente disabilitato) |

### 4.3 Salva ed esci

- Premi `Ctrl+O` poi `Invio` per salvare
- Premi `Ctrl+X` per uscire

### 4.4 Proteggi il file

```bash
chmod 600 .env
```

---

## Passo 5: Testa il Bot

```bash
uv run python -m src.bot
```

Dovresti vedere un messaggio di log che dice che il bot è partito. Ora apri Telegram e invia `/status` al tuo bot.

Se risponde — funziona! Premi `Ctrl+C` nel terminale per fermarlo.

Se non risponde, verifica:
- Hai copiato il token correttamente?
- Hai copiato il tuo chat ID correttamente?
- La connessione internet funziona?

---

## Passo 6: Installa come Servizio di Sistema (Avvio Automatico)

Questo fa partire il bot automaticamente quando accendi il PC.

### 6.1 Installa il servizio

```bash
sudo cp systemd/telegram-terminal-bot@.service /etc/systemd/system/
```

### 6.2 Correggi il percorso

Il file del servizio deve puntare alla cartella dove hai installato il bot. Lancia questo comando (funziona se sei dentro la cartella del progetto):

```bash
sudo sed -i "s|/home/%i/telegram-terminal-bot|$(pwd)|g" /etc/systemd/system/telegram-terminal-bot@.service
```

### 6.3 Attiva e avvia

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-terminal-bot@$USER
```

### 6.4 Verifica che sia attivo

```bash
sudo systemctl status telegram-terminal-bot@$USER
```

Dovresti vedere **active (running)** in verde.

---

## Passo 7: Usare il Bot

Apri Telegram e scrivi messaggi al tuo bot:

| Cosa scrivere | Cosa succede |
|--------------|-------------|
| `/status` | Mostra quale PC è attivo e la directory corrente |
| `/activate desktop` | Passa a un PC specifico |
| `/list` | Mostra tutti i PC online |
| `/cancel` | Ferma un comando in esecuzione |
| `pwd` | Esegue un qualsiasi comando shell |
| `ls -la` | Esegue un qualsiasi comando shell |
| `git pull` | Esegue un qualsiasi comando shell |

Qualsiasi testo che non è un `/comando` viene eseguito come comando shell sul PC attivo.

---

## Risoluzione Problemi

### Il bot non risponde
```bash
sudo systemctl status telegram-terminal-bot@$USER
journalctl -u telegram-terminal-bot@$USER --no-pager | tail -20
```

### Il bot si è fermato dopo il riavvio
```bash
sudo systemctl enable telegram-terminal-bot@$USER
```

### Voglio fermare il bot
```bash
sudo systemctl stop telegram-terminal-bot@$USER
```

### Voglio vedere i log in tempo reale
```bash
journalctl -u telegram-terminal-bot@$USER -f
```

---

## Installare su un Secondo PC

Ripeti i Passi 3–6 sull'altro PC, usando:
- Lo **stesso** `TELEGRAM_BOT_TOKEN`
- Lo **stesso** `AUTHORIZED_CHAT_ID`
- Un **diverso** `MACHINE_NAME` (es. `laptop`)

Poi usa `/activate laptop` o `/activate desktop` da Telegram per passare da uno all'altro.

---

## Note sulla Sicurezza

- Solo **tu** puoi controllare il bot (limitato dal tuo Chat ID)
- Il token del bot è salvato localmente e mai condiviso
- Il servizio di sistema gira con permessi limitati
- Attiva sempre il **2FA su Telegram** per maggiore sicurezza

---

## Ti Piace Questo Progetto?

Se questo bot ti è stato utile, lascia una stella su GitHub — aiuta davvero!

[![Star on GitHub](https://img.shields.io/github/stars/AndreaBonn/remote-terminal-bot?style=social)](https://github.com/AndreaBonn/remote-terminal-bot)

---

*Creato da [Andrea Bonacci](https://github.com/AndreaBonn) — [Licenza MIT](../LICENSE)*

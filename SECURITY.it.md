# Politica di Sicurezza

**[🇬🇧 Read in English](SECURITY.md)**

## Versioni Supportate

| Versione | Supportata |
|----------|-----------|
| 1.x      | Sì        |

## Segnalare una Vulnerabilità

Se scopri una vulnerabilità di sicurezza, segnalala responsabilmente:

1. **NON** aprire una issue pubblica su GitHub
2. Scrivi al maintainer con i dettagli della vulnerabilità
3. Includi i passi per riprodurre il problema e una valutazione dell'impatto

Riceverai un riscontro entro 48 ore. La correzione sarà prioritizzata in base alla gravità.

---

## Architettura di Sicurezza

Questo bot fornisce accesso shell remoto — la sicurezza è presa molto seriamente. Di seguito una panoramica completa di ogni livello di protezione implementato.

### Autenticazione & Autorizzazione

| Protezione | Come funziona |
|-----------|---------------|
| **Chat autorizzata singola** | Solo un Chat ID Telegram può inviare comandi. Tutti gli altri vengono rifiutati silenziosamente. |
| **Solo chat private** | I messaggi di gruppo vengono ignorati — il bot risponde solo in chat private. |
| **Log accessi non autorizzati** | Ogni tentativo di accesso rifiutato viene registrato con il chat ID per audit. |

### Rate Limiting & Controllo Risorse

| Protezione | Come funziona |
|-----------|---------------|
| **Limite comandi** | Massimo 30 comandi al minuto. I comandi in eccesso vengono rifiutati. |
| **Limite lunghezza comando** | Comandi più lunghi di 2048 caratteri vengono rifiutati. |
| **Cap output** | L'output dei comandi è troncato a 512 KB per prevenire esaurimento memoria. |
| **Timeout comandi** | I comandi vengono terminati (SIGTERM → SIGKILL) dopo il timeout configurato (default: 30s, max: 300s). |
| **Reset sessione inattiva** | La sessione shell si resetta dopo 30 minuti di inattività per limitare la finestra di esposizione. |
| **Limite memoria** | systemd impone un massimo di 512 MB di memoria per il servizio. |
| **Limite CPU** | systemd limita il bot al 50% di CPU. |
| **Limite task** | Massimo 64 task (processi) consentiti. |

### Isolamento Processi

| Protezione | Come funziona |
|-----------|---------------|
| **Nessun `shell=True`** | Tutte le chiamate subprocess usano `exec` con lista argomenti — nessuna shell injection possibile. |
| **Isolamento process group** | `start_new_session=True` assicura che interi alberi di processi vengano terminati al timeout. |
| **Ambiente bash pulito** | Shell avviata con `--norc --noprofile` — nessuno script utente caricato. |
| **Marker crittografici** | Ogni comando usa `secrets.token_hex(16)` come delimitatore — previene attacchi di marker injection. |

### Hardening systemd

Il servizio gira con restrizioni rigide a livello kernel:

| Direttiva | Effetto |
|-----------|---------|
| `NoNewPrivileges=true` | Il processo non può acquisire nuovi privilegi (no setuid, no capabilities) |
| `ProtectSystem=strict` | L'intero filesystem è in sola lettura tranne i percorsi esplicitamente consentiti |
| `ProtectHome=read-only` | La home directory è in sola lettura tranne la directory di lavoro del bot |
| `PrivateTmp=true` | `/tmp` privato non condiviso con altri servizi |
| `ProtectKernelTunables=true` | Non può modificare parametri kernel via `/proc` o `/sys` |
| `ProtectKernelModules=true` | Non può caricare moduli kernel |
| `ProtectControlGroups=true` | Non può modificare i cgroups |
| `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX` | Solo socket di rete e Unix consentiti |
| `RestrictNamespaces=true` | Non può creare nuovi namespace |
| `LockPersonality=true` | Non può cambiare dominio di esecuzione |
| `SystemCallFilter=@system-service` | Solo system call standard consentite |
| `CapabilityBoundingSet=` | Tutte le Linux capabilities rimosse |
| `UMask=0077` | I file creati sono leggibili solo dal proprietario |

### Gestione Segreti

| Protezione | Come funziona |
|-----------|---------------|
| **File `.env` con `chmod 600`** | Token leggibile solo dal proprietario |
| **Token mai loggato** | `Settings.__repr__()` oscura il token |
| **`.env` nel `.gitignore`** | Token mai committato nel version control |
| **Nessun segreto hardcodato** | Tutti i valori sensibili vengono da variabili d'ambiente |

### Sicurezza di Rete

| Protezione | Come funziona |
|-----------|---------------|
| **Solo long polling Telegram** | Nessuna porta aperta, nessuna connessione in ingresso necessaria |
| **Nessun server centrale** | Telegram stesso è l'unico intermediario — nessuna infrastruttura di terze parti |
| **Socket families ristrette** | systemd consente solo IPv4, IPv6 e socket Unix |

---

## Modello di Minaccia

Questa sezione esplicita le assunzioni, i rischi nel perimetro e i limiti noti del modello di sicurezza — in modo che chi installa il bot possa valutare se i trade-off sono compatibili con il proprio contesto.

### Perimetro di fiducia

| Livello | Cosa è considerato fidato | Cosa non lo è |
|---------|---------------------------|---------------|
| Account Telegram | Le credenziali e il secondo fattore 2FA | L'infrastruttura Telegram stessa (fuori scope) |
| `AUTHORIZED_CHAT_ID` | L'unico chat ID configurato in `.env` | Qualsiasi altra chat, anche dello stesso account |
| Macchina locale | L'utente che esegue il bot (`User=%i` in systemd) | Altri utenti sullo stesso host |
| File `.env` | Permessi `0600` con accesso solo al proprietario | Backup, snapshot, o filesystem condivisi |

### Modello a token condiviso e conseguenze

**Lo stesso `TELEGRAM_BOT_TOKEN` viene replicato su ogni PC che esegue il bot.** È una scelta architetturale deliberata (Telegram fa da bus di messaggistica) ma ha due conseguenze che vanno dichiarate:

1. **Il compromesso di un PC compromette tutti i PC**
   Un attaccante con accesso in lettura a `.env` su una qualsiasi macchina ottiene il token del bot e può impersonarlo da ovunque. Una volta autenticato come bot può leggere tutti i messaggi inviati alla chat autorizzata e rinviare comandi attraverso qualsiasi PC online.

2. **Non esiste revoca per singolo PC**
   I token bot di Telegram non sono scoping per dispositivo. Revocare il token tramite BotFather lo invalida su ogni PC simultaneamente. Un controllo accessi granulare non è possibile senza riarchitettare abbandonando "Telegram come bus".

### Procedura di rotazione del token

Se sospetti che un token sia stato esposto (es. un backup di `.env` reso pubblico, un PC rubato, o uno sviluppatore che lascia il team), ruota il token con questa sequenza esatta:

```bash
# 1. Revoca il vecchio token su BotFather
#    Invia /revoke a @BotFather, seleziona il bot, conferma.
#    BotFather restituirà un nuovo token; copialo.

# 2. Su OGNI PC che esegue il bot, in parallelo:
sudo systemctl stop telegram-terminal-bot@$USER
nano ~/telegram-terminal-bot/.env       # incolla il nuovo TELEGRAM_BOT_TOKEN
sudo systemctl start telegram-terminal-bot@$USER

# 3. Verifica su ciascun PC:
journalctl -u telegram-terminal-bot@$USER -n 20
#    Dovresti vedere la notifica "🟢 [hostname] è online" su Telegram.
```

Non esiste una propagazione automatica. Più breve è l'intervallo tra la revoca e l'ultimo PC aggiornato, più piccola è la finestra di downtime — ma non si introducono rischi di sicurezza con aggiornamenti scaglionati, perché il vecchio token è morto subito dopo lo step 1.

### Fuori scope

Il modello di minaccia non copre intenzionalmente:

- Un titolare malintenzionato dell'account Telegram in possesso sia della password sia del secondo fattore 2FA (assunto equivalente a "te")
- Compromissione del servizio Telegram stesso (coercizione governativa, breach dell'infrastruttura)
- Attacchi side-channel sull'host (memory dump, exploit kernel sotto l'hardening di `systemd`)
- Attacchi di supply-chain sulle dipendenze Python transitive — mitigati dal `pip-audit` in CI, non eliminati

Se il tuo modello di minaccia include uno di questi punti, questo bot non è lo strumento giusto. Usa un bastion SSH con MFA hardware-key.

---

## Cosa Dovresti Fare Tu

Per massimizzare la sicurezza dal tuo lato:

1. **Attiva il 2FA su Telegram** — il tuo account Telegram è il perimetro di accesso
2. **Mantieni i permessi di `.env` ristretti** — `chmod 600 .env`
3. **Usa un token bot dedicato** — non riutilizzare token tra progetti diversi
4. **Imposta un timeout ragionevole** — valori più bassi limitano i danni da comandi accidentalmente lunghi
5. **Monitora i log** — `journalctl -u telegram-terminal-bot@$USER -f`

---

## In Sintesi

Questo bot non ha **porte aperte**, **nessuna interfaccia web**, **nessuna dipendenza di terze parti oltre Telegram**, e gira in una **sandbox hardened a livello kernel**. L'unico vettore di attacco è il tuo account Telegram stesso — proteggilo con il 2FA.

---

*Mantenuto da [Andrea Bonacci](https://github.com/AndreaBonn)*

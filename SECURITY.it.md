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

# Security Policy

**[🇮🇹 Leggi in italiano](SECURITY.it.md)**

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x     | Yes       |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT** open a public GitHub issue
2. Email the maintainer directly with details of the vulnerability
3. Include steps to reproduce and potential impact assessment

You should receive an acknowledgment within 48 hours. A fix will be prioritized based on severity.

---

## Security Architecture

This bot provides remote shell access — security is taken very seriously. Below is a complete overview of every protection layer implemented.

### Authentication & Authorization

| Protection | How it works |
|-----------|-------------|
| **Single authorized chat** | Only one Telegram Chat ID can send commands. All others are silently rejected. |
| **Private chat only** | Group messages are ignored — the bot only responds in private chats. |
| **Unauthorized access logging** | Every rejected access attempt is logged with the chat ID for auditing. |

### Rate Limiting & Resource Control

| Protection | How it works |
|-----------|-------------|
| **Command rate limit** | Maximum 30 commands per minute. Excess commands are rejected. |
| **Command length limit** | Commands longer than 2048 characters are rejected. |
| **Output cap** | Command output is truncated at 512 KB to prevent memory exhaustion. |
| **Command timeout** | Commands are killed (SIGTERM → SIGKILL) after the configured timeout (default: 30s, max: 300s). |
| **Idle session reset** | Shell session resets after 30 minutes of inactivity to limit exposure window. |
| **Memory limit** | systemd enforces 512 MB max memory for the service. |
| **CPU limit** | systemd limits the bot to 50% CPU. |
| **Task limit** | Maximum 64 tasks (processes) allowed. |

### Process Isolation

| Protection | How it works |
|-----------|-------------|
| **No `shell=True`** | All subprocess calls use `exec` with argument lists — no shell injection possible. |
| **Process group isolation** | `start_new_session=True` ensures entire process trees are killed on timeout. |
| **Clean bash environment** | Shell spawned with `--norc --noprofile` — no user scripts loaded. |
| **Cryptographic end markers** | Each command uses `secrets.token_hex(16)` as delimiter — prevents marker injection attacks. |

### systemd Hardening

The service runs with strict kernel-level restrictions:

| Directive | Effect |
|-----------|--------|
| `NoNewPrivileges=true` | Process cannot gain new privileges (no setuid, no capabilities) |
| `ProtectSystem=strict` | Entire filesystem is read-only except explicitly allowed paths |
| `ProtectHome=read-only` | Home directory is read-only except the bot's working directory |
| `PrivateTmp=true` | Private `/tmp` not shared with other services |
| `ProtectKernelTunables=true` | Cannot modify kernel parameters via `/proc` or `/sys` |
| `ProtectKernelModules=true` | Cannot load kernel modules |
| `ProtectControlGroups=true` | Cannot modify cgroups |
| `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX` | Only network and Unix sockets allowed |
| `RestrictNamespaces=true` | Cannot create new namespaces |
| `LockPersonality=true` | Cannot change execution domain |
| `SystemCallFilter=@system-service` | Only standard system calls allowed |
| `CapabilityBoundingSet=` | All Linux capabilities removed |
| `UMask=0077` | Files created are only readable by the owner |

### Secret Management

| Protection | How it works |
|-----------|-------------|
| **`.env` file with `chmod 600`** | Token readable only by the owner |
| **Token never logged** | `Settings.__repr__()` redacts the token |
| **`.env` in `.gitignore`** | Token never committed to version control |
| **No hardcoded secrets** | All sensitive values come from environment variables |

### Network Security

| Protection | How it works |
|-----------|-------------|
| **Telegram long polling only** | No open ports, no incoming connections needed |
| **No central server** | Telegram itself is the only intermediary — no third-party infrastructure |
| **Restricted socket families** | systemd only allows IPv4, IPv6, and Unix sockets |

---

## Threat Model

This section makes explicit the assumptions, the in-scope risks, and the known limitations of the security model — so deployers can decide whether the trade-offs match their environment.

### Trust boundary

| Layer | What is trusted | What is not |
|-------|-----------------|-------------|
| Telegram account | Your account credentials and 2FA factor | Telegram infrastructure itself (out of scope) |
| `AUTHORIZED_CHAT_ID` | The single chat ID configured in `.env` | Any other chat, even from the same account |
| Local machine | The user running the bot (`User=%i` in systemd) | Other users on the same host |
| `.env` file | File permissions `0600` on owner-only access | Backups, snapshots, or shared filesystems |

### Shared-token model and its consequences

**The same `TELEGRAM_BOT_TOKEN` is replicated across every PC running the bot.** This is a deliberate design choice (Telegram is the message bus) but it has two consequences that must be acknowledged:

1. **Compromise of one PC compromises all PCs**
   An attacker with read access to `.env` on any single machine obtains the bot token and can impersonate the bot from anywhere. Once authenticated as the bot, they can read all messages sent to the authorized chat and send commands back through any of the PCs that are online.

2. **No per-PC revocation exists**
   Telegram bot tokens cannot be scoped per-device. Revoking the token via BotFather invalidates it on every PC simultaneously. Granular access control is not possible without re-architecting away from "Telegram as bus".

### Token rotation procedure

If you suspect a token has leaked (e.g., a backup of `.env` was exposed, a PC was stolen, or a developer left the team), rotate the token using this exact sequence:

```bash
# 1. Revoke the old token in BotFather
#    Send /revoke to @BotFather, select the bot, confirm.
#    BotFather will issue a new token; copy it.

# 2. On EVERY PC running the bot, in parallel:
sudo systemctl stop telegram-terminal-bot@$USER
nano ~/telegram-terminal-bot/.env       # paste the new TELEGRAM_BOT_TOKEN
sudo systemctl start telegram-terminal-bot@$USER

# 3. Verify on each PC:
journalctl -u telegram-terminal-bot@$USER -n 20
#    You should see the "🟢 [hostname] è online" notification on Telegram.
```

There is no automated propagation. The shorter the wall-clock gap between revoke and the last PC update, the smaller the downtime window — but no security risk arises from staggered updates, because the old token is dead immediately after step 1.

### Out of scope

The threat model intentionally does **not** cover:

- A malicious Telegram account holder who possesses both the password and the 2FA second factor (assumed equivalent to "you")
- Compromise of the Telegram service itself (governmental coercion, infrastructure breach)
- Side-channel attacks on the host (memory dumps, kernel exploits below `systemd` hardening)
- Supply-chain attacks on the bot's transitive Python dependencies — mitigated by CI `pip-audit`, not eliminated

If your threat model includes any of the above, this bot is not the right tool. Use a properly authenticated SSH bastion with hardware-key MFA instead.

---

## What You Should Do

To maximize security on your end:

1. **Enable 2FA on Telegram** — your Telegram account is the access boundary
2. **Keep `.env` permissions restricted** — `chmod 600 .env`
3. **Use a dedicated bot token** — don't reuse tokens across projects
4. **Set a reasonable timeout** — lower values limit damage from accidental long-running commands
5. **Monitor logs** — `journalctl -u telegram-terminal-bot@$USER -f`

---

## Summary

This bot has **no open ports**, **no web interface**, **no third-party dependencies beyond Telegram**, and runs in a **kernel-hardened sandbox**. The only attack vector is your Telegram account itself — protect it with 2FA.

---

*Maintained by [Andrea Bonacci](https://github.com/AndreaBonn)*

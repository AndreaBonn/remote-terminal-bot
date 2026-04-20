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

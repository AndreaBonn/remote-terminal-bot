# Security Policy

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

## Security Model

This bot provides remote shell access — security is critical:

- **Authentication**: Commands only accepted from a single authorized Telegram chat ID
- **Chat type restriction**: Only private chats accepted (group messages rejected)
- **Sandboxing**: systemd service runs with strict security directives (NoNewPrivileges, ProtectSystem=strict, CapabilityBoundingSet=)
- **Rate limiting**: 30 commands/minute maximum
- **No shell=True**: All subprocess calls use exec with argument lists
- **Token protection**: Bot token never logged or exposed in repr()

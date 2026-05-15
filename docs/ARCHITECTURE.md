# Architecture

Technical reference for the Telegram Terminal Bot internals. For usage and setup, see [README](../README.md).

## System Overview

The bot runs as a long-polling Telegram client. Multiple instances share the same bot token, but only one (the **active** PC) executes shell commands. Others stay in standby, tracking peers via heartbeat messages.

```mermaid
%%{init: {'theme': 'default'}}%%
graph LR
    user["You (phone)"]
    tg_api["Telegram API"]

    subgraph active_bot["Active Bot (PC-1)"]
        direction TB
        handlers["Handlers"]
        shell["ShellSession"]
        state_mgr["StateManager"]
        audit["AuditLog"]
        config["Config (.env)"]
    end

    subgraph standby["Standby Bots"]
        direction TB
        pc2["Bot PC-2"]
        pcn["Bot PC-N"]
    end

    bash_proc["bash subprocess"]

    user -->|commands| tg_api
    tg_api -->|long polling| handlers
    tg_api -.->|heartbeat| pc2
    tg_api -.->|heartbeat| pcn
    handlers --> shell
    handlers --> state_mgr
    handlers --> audit
    shell --> bash_proc
    config -.-> handlers

    classDef core fill:#2563eb,stroke:#1d4ed8,color:#fff
    classDef data fill:#d97706,stroke:#b45309,color:#fff
    classDef ext fill:#6b7280,stroke:#4b5563,color:#fff
    classDef engine fill:#059669,stroke:#047857,color:#fff

    class user,tg_api ext
    class handlers,shell core
    class state_mgr,audit,config data
    class bash_proc engine
    class pc2,pcn ext
```

**Color legend:** blue = core logic, amber = data/config, green = external process, grey = external services.

## Command Execution Flow

Every text message (non-command) goes through this pipeline. The handler validates authorization, checks rate limits, confirms this PC is the active one, then delegates to `ShellSession`. The session writes the command plus a cryptographic end marker to the bash subprocess stdin, reads stdout until the marker appears, and parses the exit code.

```mermaid
sequenceDiagram
    actor user as User
    participant tg as Telegram
    participant hdl as Handlers
    participant ss as ShellSession
    participant bash as bash subprocess

    user->>tg: Send text command
    tg->>hdl: Update (long polling)
    hdl->>hdl: Check auth + rate limit
    hdl->>hdl: Check is_active

    hdl->>+ss: execute(command)
    ss->>ss: Acquire lock
    ss->>bash: Write cmd + marker to stdin

    alt command completes
        bash-->>ss: stdout + marker + exit code
        ss->>ss: Parse output and exit code
        ss-->>-hdl: CommandResult
        hdl->>hdl: format_output()
        hdl->>tg: reply_text (1..N chunks)
        tg-->>user: Formatted response
    else timeout
        ss->>bash: SIGTERM then SIGKILL
        ss->>ss: Respawn shell
        ss-->>hdl: CommandResult (timed_out=true)
        hdl->>tg: Timeout warning
        tg-->>user: Timeout message
    end
```

Key details:
- The `asyncio.Lock` prevents concurrent command execution on the same session
- Output exceeding 512KB is truncated
- Responses longer than 4000 chars are split into multiple Telegram messages
- On timeout, the entire process group is killed (`os.killpg`) and the shell is respawned

## Shell Session Lifecycle

The bash subprocess follows this state machine. It spawns on startup, sits idle between commands, and auto-resets after 30 minutes of inactivity to limit the exposure window.

```mermaid
stateDiagram-v2
    [*] --> Spawning : start()

    Spawning --> Idle : bash ready

    Idle --> Executing : execute()
    Idle --> IdleReset : 30min inactivity
    Idle --> Terminated : shutdown()

    Executing --> Idle : command completes
    Executing --> TimedOut : timeout exceeded

    TimedOut --> Spawning : kill + respawn

    IdleReset --> Spawning : kill + respawn

    Terminated --> [*] : SIGTERM / SIGKILL
```

The shell is spawned with `--norc --noprofile` in its own process group (`start_new_session=True`). This ensures clean signal delivery and prevents user RC scripts from interfering.

## Multi-PC Coordination

Multiple bots share the same Telegram bot token. Coordination happens through Telegram itself: heartbeat messages for peer discovery, `/activate` for switching the active PC. No external infrastructure needed.

```mermaid
sequenceDiagram
    actor user as User
    participant tg as Telegram
    participant pc1 as Bot PC-1
    participant pc2 as Bot PC-2

    Note over pc1,pc2: Both bots poll Telegram

    pc1->>tg: __HB__pc1__
    tg->>pc1: Receive heartbeat
    pc1->>pc1: register_heartbeat + delete msg
    tg->>pc2: Receive heartbeat
    pc2->>pc2: register_heartbeat + delete msg

    user->>tg: /activate pc2
    tg->>pc1: Update
    pc1->>pc1: state.activate("pc2")
    tg->>pc2: Update
    pc2->>pc2: state.activate("pc2")

    user->>tg: ls -la
    tg->>pc1: Update
    pc1->>pc1: is_active=false, ignore
    tg->>pc2: Update
    pc2->>pc2: is_active=true, execute
    pc2-->>tg: Command output
    tg-->>user: Response from PC-2
```

Key details:
- Heartbeat messages use the format `__HB__<machine_name>__` and are deleted after processing
- Peers with no heartbeat for >120 seconds are considered offline
- State is persisted to `~/.local/share/telegram-terminal-bot/state.json` via atomic write (tmp + rename)
- When a PC receives a command but `is_active=false`, it silently ignores it

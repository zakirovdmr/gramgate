# Lando

Lightweight Telegram gateway — exposes a real Telegram user account as REST API + MCP server.

## Architecture

```
Telegram MTProto ←→ Pyrogram Client (telegram.py)
                         ↕
                    MessageStore (store.py)     ← in-memory feed buffer
                         ↕
                 ┌───────┴────────┐
           REST API (api.py)   MCP Server (mcp_server.py)
           :18791 Starlette    :18793 SSE/FastMCP
                 └───────┬────────┘
                         ↕
              Optional: OpenClaw bridge (openclaw.py)
```

Single async process. All modules share one `LandoTelegram` instance.

## Modules

| File | Purpose |
|------|---------|
| `__main__.py` | Entry point, wires everything, starts uvicorn servers |
| `config.py` | Pydantic settings from `.env` |
| `telegram.py` | Pyrogram MTProto client, message bridge, 40+ account methods |
| `api.py` | Starlette REST API, auth/rate-limit/error middleware |
| `mcp_server.py` | FastMCP server with 51 tools mirroring REST endpoints |
| `openclaw.py` | Optional HTTP client for forwarding messages to OpenClaw |
| `store.py` | In-memory sliding window message store for live feed |
| `ratelimit.py` | Sliding window rate limiter (per-chat, global, join, API) |

## Running

```bash
pip install -e .
cp .env.example .env  # fill in Telegram credentials
lando                 # or: python -m lando
```

First run requires interactive Telegram auth code in terminal.

## Key conventions

- All chat_id parsing goes through `_parse_chat_id()` (api.py) or `_parse_id()` (mcp_server.py)
- OpenClaw bridge is optional — disabled when `OPENCLAW_TOKEN` is empty
- MCP server is optional — disabled when `LANDO_MCP_PORT=0`
- REST API auth is optional — disabled when `LANDO_API_TOKEN` is empty
- Rate limits protect the Telegram account from flood bans, not from malicious users
- Error replies are suppressed for bot chats to prevent infinite loops
- Messages over 4096 chars are auto-split at newline/space boundaries

## Config (env vars)

| Var | Default | Required |
|-----|---------|----------|
| `TELEGRAM_API_ID` | — | yes |
| `TELEGRAM_API_HASH` | — | yes |
| `TELEGRAM_PHONE` | — | yes |
| `LANDO_API_PORT` | 18791 | no |
| `LANDO_API_HOST` | 127.0.0.1 | no |
| `LANDO_API_TOKEN` | (empty) | no |
| `LANDO_MCP_PORT` | 18793 | no |
| `LANDO_RATE_SEND_PER_CHAT` | 20 | no |
| `LANDO_RATE_SEND_GLOBAL` | 30 | no |
| `LANDO_RATE_JOIN` | 5 | no |
| `LANDO_RATE_API_GLOBAL` | 25 | no |
| `OPENCLAW_URL` | http://127.0.0.1:18789 | no |
| `OPENCLAW_TOKEN` | (empty) | no |

## Testing

No test suite yet. Verify manually:

```bash
curl http://127.0.0.1:18791/health
curl http://127.0.0.1:18791/api/me
curl -s --max-time 2 http://127.0.0.1:18793/sse  # MCP SSE
```

## Ports

- **18791** — REST API (Starlette + uvicorn)
- **18793** — MCP SSE server (FastMCP + uvicorn)
- **18789** — OpenClaw gateway (external, not managed by Lando)
- **18792** — Reserved (used by OpenClaw MCP on this server)

## Dependencies

- `pyrofork` (Pyrogram fork) — MTProto client
- `tgcrypto` — crypto accelerator for Pyrogram
- `starlette` + `uvicorn` — REST API
- `mcp` (FastMCP) — MCP server
- `httpx` — async HTTP client for OpenClaw bridge
- `pydantic-settings` — config management

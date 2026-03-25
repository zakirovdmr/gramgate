# Lando

Lightweight Telegram gateway that exposes your account as a **REST API** and **MCP server**.

Give any HTTP client, AI agent, or automation tool full programmatic access to Telegram — send messages, read history, click inline buttons, manage groups, and more.

## Features

- **40+ API endpoints** — messages, history, inline buttons, polls, pins, groups, channels, media, contacts, reactions, search
- **Two interfaces** — REST API (any HTTP client) + MCP server (AI agents like Claude, GPT, etc.)
- **Real Telegram account** — uses MTProto via Pyrogram, not the limited Bot API
- **AI agent bridge** — optionally forward incoming messages to an AI backend for automated replies
- **Lightweight** — single Python process, ~2000 lines, no database

## Quick Start

### 1. Get Telegram API credentials

Go to [my.telegram.org/apps](https://my.telegram.org/apps) and create an application. You'll get an `api_id` and `api_hash`.

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your Telegram credentials
```

### 3. Install & run

```bash
pip install -e .
lando
```

On first run, Pyrogram will ask for your phone number verification code in the terminal. After that, a session file is saved and subsequent runs are automatic.

### 4. Use the API

```bash
# Health check
curl http://127.0.0.1:18791/health

# Get your account info
curl http://127.0.0.1:18791/api/me

# List recent chats
curl http://127.0.0.1:18791/api/dialogs

# Send a message
curl -X POST http://127.0.0.1:18791/api/message/send \
  -H "Content-Type: application/json" \
  -d '{"recipient": "@username", "text": "Hello from Lando!"}'

# Read chat history with inline buttons
curl -X POST http://127.0.0.1:18791/api/chat/history/rich \
  -H "Content-Type: application/json" \
  -d '{"chat_id": 123456789, "limit": 10}'

# Click an inline button
curl -X POST http://127.0.0.1:18791/api/button/click \
  -H "Content-Type: application/json" \
  -d '{"chat_id": 123456789, "message_id": 42, "callback_data": "btn_action"}'
```

## API Reference

### Account
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/me` | Current account info |
| GET | `/api/contacts` | Contact list |
| POST | `/api/users` | Get user details by IDs |

### Chats
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/dialogs` | List all chats |
| POST | `/api/chat/info` | Chat details |
| POST | `/api/chat/history` | Message history |
| POST | `/api/chat/history/rich` | History with inline buttons |
| POST | `/api/chat/members` | Chat members |
| POST | `/api/chat/join` | Join by link/username |
| POST | `/api/chat/leave` | Leave a chat |
| POST | `/api/chat/read` | Mark as read |
| POST | `/api/chat/create/group` | Create group |
| POST | `/api/chat/create/channel` | Create channel |
| POST | `/api/chat/create/supergroup` | Create supergroup |

### Messages
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/message/send` | Send message |
| POST | `/api/message/edit` | Edit message |
| POST | `/api/message/delete` | Delete messages |
| POST | `/api/message/forward` | Forward messages |
| POST | `/api/message/copy` | Copy without "forwarded" header |
| POST | `/api/message/pin` | Pin message |
| POST | `/api/message/unpin` | Unpin message |
| POST | `/api/message/react` | Add reaction |
| POST | `/api/message/search` | Search in chat |
| POST | `/api/message/get` | Get messages by ID |
| POST | `/api/message/scheduled` | Send scheduled message |
| POST | `/api/message/media/download` | Download media (base64) |
| POST | `/api/search/global` | Global search |
| POST | `/api/button/click` | Click inline button |

### Members
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/member/ban` | Ban user |
| POST | `/api/member/unban` | Unban user |
| POST | `/api/member/restrict` | Restrict user |
| POST | `/api/member/promote` | Promote to admin |
| POST | `/api/member/add` | Add members |

### Polls
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/poll/send` | Create poll |
| POST | `/api/poll/stop` | Stop poll |
| POST | `/api/poll/vote` | Vote in poll |

### Other
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/send/location` | Send location |
| POST | `/api/send/contact` | Send contact card |
| POST | `/api/typing` | Send typing indicator |
| GET | `/api/feed/new` | New messages from monitored chats |
| POST | `/api/feed/chat` | Messages from specific chat |
| GET | `/api/feed/chats` | All monitored chats |

## Authentication

Set `LANDO_API_TOKEN` in `.env` to require bearer token auth:

```bash
LANDO_API_TOKEN=your-secret-token
```

Then include the header in all requests:

```bash
curl -H "Authorization: Bearer your-secret-token" http://127.0.0.1:18791/api/me
```

The `/health` endpoint is always accessible without auth.

## AI Agent Bridge (Optional)

Lando can forward incoming messages to an AI backend (OpenAI-compatible API) and send responses back to Telegram. Set `OPENCLAW_TOKEN` in `.env` to enable.

Without it, Lando works as a pure gateway — API and MCP tools only, no auto-replies.

## MCP Server

Lando runs a built-in MCP (Model Context Protocol) server on port `18793` (configurable via `LANDO_MCP_PORT`). It exposes 51 Telegram tools that any MCP-compatible agent can use natively.

### Connect from Claude Desktop / Claude Code

Add to your MCP config (`claude_desktop_config.json` or `.claude/settings.json`):

```json
{
  "mcpServers": {
    "lando-telegram": {
      "url": "http://127.0.0.1:18793/sse"
    }
  }
}
```

Set `LANDO_MCP_PORT=0` to disable the MCP server.

## Use with OpenClaw

Lando ships with a ready-made OpenClaw skill in `extras/openclaw/`.

### Quick install

```bash
# From the Lando repo directory:
./extras/openclaw/install.sh

# Or manually:
cp -r extras/openclaw/SKILL.md ~/.openclaw/skills/lando-telegram/SKILL.md
```

Restart the OpenClaw gateway after installing. The agent will be able to call Lando's REST API endpoints via `curl` commands described in the skill.

### OpenClaw bridge mode

Optionally, set `OPENCLAW_TOKEN` in `.env` to enable two-way integration: incoming Telegram messages are forwarded to OpenClaw, and AI responses are sent back to the chat automatically.

## Rate Limiting

Lando includes built-in rate limiting to protect your Telegram account from flood bans. Limits are enabled by default and tuned below Telegram's thresholds:

| Limit | Default | Env var |
|-------|---------|---------|
| Messages per chat | 20/min | `LANDO_RATE_SEND_PER_CHAT` |
| Messages global | 30/min | `LANDO_RATE_SEND_GLOBAL` |
| Join/leave/create | 5/hour | `LANDO_RATE_JOIN` |
| API requests | 25/sec | `LANDO_RATE_API_GLOBAL` |

When a limit is exceeded, the API returns `429 Too Many Requests` with a `Retry-After` header. Set any limit to `0` to disable it.

> **Why this matters:** Telegram actively monitors user account automation. Exceeding their (unpublished) thresholds results in `FloodWait` errors, temporary bans, or permanent account deletion. These limits exist to keep your account safe — disabling them is at your own risk.

## Security

- By default, the API binds to `127.0.0.1` (localhost only)
- Set `LANDO_API_TOKEN` for authentication when exposing to a network
- **Never expose Lando to the public internet without authentication**
- Session files in `sessions/` contain your Telegram credentials — keep them private

## Disclaimer

This project uses Telegram's MTProto API through a user account. Use responsibly and in accordance with [Telegram's Terms of Service](https://telegram.org/tos). The authors are not responsible for any misuse or account restrictions.

**Do not use Lando for spam, unsolicited messaging, or any form of abuse.** Built-in rate limits are designed to protect your account from accidental overuse — they are not a substitute for responsible usage. Telegram will permanently ban accounts that violate their terms, regardless of which tool was used.

## License

MIT

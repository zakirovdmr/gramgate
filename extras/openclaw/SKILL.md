---
name: lando-telegram
description: Full Telegram account access via Lando MTProto bridge. Read channels, send/edit/delete/pin messages, manage chats and members, send polls/locations/contacts, monitor live feed from all subscribed channels and groups.
metadata:
  {
    "openclaw":
      {
        "emoji": "📱",
      },
  }
---

# Lando — Telegram Account (MTProto)

Lando provides full Telegram account capabilities via MTProto (not Bot API).
All endpoints are on `http://127.0.0.1:18791`.

Use `curl -s` to call these endpoints. All POST endpoints accept JSON body.

## Quick Reference

### Account

```bash
# Get current account info
curl -s http://127.0.0.1:18791/api/me

# Get contact list
curl -s http://127.0.0.1:18791/api/contacts

# Get user info by IDs
curl -s -X POST http://127.0.0.1:18791/api/users -H 'Content-Type: application/json' -d '{"user_ids": [123456789]}'

# Get profile photos
curl -s -X POST http://127.0.0.1:18791/api/users/photos -H 'Content-Type: application/json' -d '{"chat_id": "123456789", "limit": 10}'
```

### Chats & Channels

```bash
# List all dialogs (chats, groups, channels)
curl -s http://127.0.0.1:18791/api/dialogs?limit=30

# Get info about a chat (by ID or @username)
curl -s -X POST http://127.0.0.1:18791/api/chat/info -H 'Content-Type: application/json' -d '{"chat_id": "@durov"}'

# Read message history from any chat/channel
curl -s -X POST http://127.0.0.1:18791/api/chat/history -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "limit": 20}'

# Get chat members
curl -s -X POST http://127.0.0.1:18791/api/chat/members -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "limit": 50}'

# Join a channel or group
curl -s -X POST http://127.0.0.1:18791/api/chat/join -H 'Content-Type: application/json' -d '{"link": "@channel_name"}'

# Leave a channel or group
curl -s -X POST http://127.0.0.1:18791/api/chat/leave -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890"}'

# Mark all messages as read
curl -s -X POST http://127.0.0.1:18791/api/chat/read -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890"}'
```

### Chat Management (NEW)

```bash
# Create a group
curl -s -X POST http://127.0.0.1:18791/api/chat/create/group -H 'Content-Type: application/json' -d '{"title": "My Group", "users": [123456789]}'

# Create a channel
curl -s -X POST http://127.0.0.1:18791/api/chat/create/channel -H 'Content-Type: application/json' -d '{"title": "My Channel", "description": "About this channel"}'

# Create a supergroup
curl -s -X POST http://127.0.0.1:18791/api/chat/create/supergroup -H 'Content-Type: application/json' -d '{"title": "My Supergroup", "description": "About this group"}'

# Set chat title
curl -s -X POST http://127.0.0.1:18791/api/chat/title -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "title": "New Title"}'

# Set chat description
curl -s -X POST http://127.0.0.1:18791/api/chat/description -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "description": "New description"}'

# Delete chat photo
curl -s -X POST http://127.0.0.1:18791/api/chat/photo/delete -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890"}'

# Archive / unarchive chats
curl -s -X POST http://127.0.0.1:18791/api/chat/archive -H 'Content-Type: application/json' -d '{"chat_ids": ["-1001234567890"]}'
curl -s -X POST http://127.0.0.1:18791/api/chat/unarchive -H 'Content-Type: application/json' -d '{"chat_ids": ["-1001234567890"]}'

# Export invite link (permanent)
curl -s -X POST http://127.0.0.1:18791/api/chat/invite/export -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890"}'

# Create new invite link (with optional name, expiry, member limit)
curl -s -X POST http://127.0.0.1:18791/api/chat/invite/create -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "name": "link1", "member_limit": 100}'
```

### Messages

```bash
# Send message to any user/chat
curl -s -X POST http://127.0.0.1:18791/api/message/send -H 'Content-Type: application/json' -d '{"recipient": "@username", "text": "Hello!"}'

# Edit a message
curl -s -X POST http://127.0.0.1:18791/api/message/edit -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "message_id": 42, "text": "Updated text"}'

# Delete messages
curl -s -X POST http://127.0.0.1:18791/api/message/delete -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "message_ids": [42, 43]}'

# Pin / unpin / unpin all
curl -s -X POST http://127.0.0.1:18791/api/message/pin -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "message_id": 42}'
curl -s -X POST http://127.0.0.1:18791/api/message/unpin -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "message_id": 42}'
curl -s -X POST http://127.0.0.1:18791/api/message/unpin/all -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890"}'

# Search messages in a chat
curl -s -X POST http://127.0.0.1:18791/api/message/search -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "query": "keyword", "limit": 20}'

# Forward messages
curl -s -X POST http://127.0.0.1:18791/api/message/forward -H 'Content-Type: application/json' -d '{"to_chat_id": "123456", "from_chat_id": "-1001234567890", "message_ids": [100, 101]}'

# Copy message (no forward header)
curl -s -X POST http://127.0.0.1:18791/api/message/copy -H 'Content-Type: application/json' -d '{"to_chat_id": "123456", "from_chat_id": "-1001234567890", "message_id": 100}'

# React to a message
curl -s -X POST http://127.0.0.1:18791/api/message/react -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "message_id": 42, "emoji": "🔥"}'

# Get messages by ID
curl -s -X POST http://127.0.0.1:18791/api/message/get -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "message_ids": [42, 43]}'

# Send scheduled message (schedule_date is Unix timestamp)
curl -s -X POST http://127.0.0.1:18791/api/message/scheduled -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "text": "Hello later!", "schedule_date": 1740500000}'

# Download media from a message
curl -s -X POST http://127.0.0.1:18791/api/message/media/download -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "message_id": 42}'

# Global search (find public channels/users)
curl -s -X POST http://127.0.0.1:18791/api/search/global -H 'Content-Type: application/json' -d '{"query": "crypto news", "limit": 10}'
```

### Member Management (NEW)

```bash
# Ban / unban a user from chat
curl -s -X POST http://127.0.0.1:18791/api/member/ban -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "user_id": 123456789}'
curl -s -X POST http://127.0.0.1:18791/api/member/unban -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "user_id": 123456789}'

# Restrict a member (mute)
curl -s -X POST http://127.0.0.1:18791/api/member/restrict -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "user_id": 123456789, "permissions": {}}'

# Promote to admin
curl -s -X POST http://127.0.0.1:18791/api/member/promote -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "user_id": 123456789, "privileges": {}}'

# Add members to chat
curl -s -X POST http://127.0.0.1:18791/api/member/add -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "user_ids": [123456789]}'
```

### User Actions (NEW)

```bash
# Block / unblock a user
curl -s -X POST http://127.0.0.1:18791/api/user/block -H 'Content-Type: application/json' -d '{"user_id": 123456789}'
curl -s -X POST http://127.0.0.1:18791/api/user/unblock -H 'Content-Type: application/json' -d '{"user_id": 123456789}'
```

### Polls (NEW)

```bash
# Send a poll
curl -s -X POST http://127.0.0.1:18791/api/poll/send -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "question": "Best language?", "options": ["Python", "Rust", "Go"], "is_anonymous": true, "poll_type": "regular"}'

# Stop a poll
curl -s -X POST http://127.0.0.1:18791/api/poll/stop -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "message_id": 42}'

# Vote on a poll
curl -s -X POST http://127.0.0.1:18791/api/poll/vote -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "message_id": 42, "option_ids": [0]}'
```

### Location & Contact (NEW)

```bash
# Send location
curl -s -X POST http://127.0.0.1:18791/api/send/location -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "latitude": 55.7558, "longitude": 37.6173}'

# Send contact
curl -s -X POST http://127.0.0.1:18791/api/send/contact -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "phone_number": "+79991234567", "first_name": "John", "last_name": "Doe"}'
```

### Misc (NEW)

```bash
# Set typing indicator (action: typing, upload_photo, record_video, etc.)
curl -s -X POST http://127.0.0.1:18791/api/typing -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "action": "typing"}'
```

### Live Feed (Real-time Channel/Group Monitoring)

Lando monitors ALL channels and groups the account is subscribed to. New messages are stored in memory.

```bash
# Get NEW messages since last check (incremental — each call returns only unseen messages)
curl -s http://127.0.0.1:18791/api/feed/new?limit=100

# Get stored messages from a specific chat
curl -s -X POST http://127.0.0.1:18791/api/feed/chat -H 'Content-Type: application/json' -d '{"chat_id": "-1001234567890", "limit": 50}'

# List all chats that received messages since Lando started
curl -s http://127.0.0.1:18791/api/feed/chats
```

## Notes

- `chat_id` for groups/channels is negative (e.g. `-1001234567890`)
- `chat_id` for users is positive (e.g. `123456789`)
- Long messages are automatically split at 4096 chars
- Markdown formatting is supported in sent messages
- The live feed only contains messages received while Lando is running
- Use `api/chat/history` to read older messages from any chat

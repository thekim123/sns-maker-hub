# Telegram ID Verification Guide

## Goal
Bind exactly one Telegram account (`telegram_user_id`) to one hub user after proof-of-ownership.

## Server Policy
- Nonce TTL: 300 seconds (5 minutes)
- Max failures per nonce: 5
- On success/expiry/max-fail: nonce row is removed
- `hub_users.telegram_id` must be unique across users

## Hub Endpoints
1. `POST /profile/telegram/challenge`
- Auth: `Authorization: Bearer <hub_access_token>`
- Purpose: create a one-time nonce for the logged-in user

2. `POST /telegram/verify/complete`
- Auth: `X-API-KEY`
- Purpose: bot confirms ownership with nonce + Telegram sender id

## End-to-End Flow
1. Dashboard calls `POST /profile/telegram/challenge`.
2. Hub returns `start_command` (`/start <nonce>`) and optional `bot_link`.
3. User sends `/start <nonce>` to the Telegram bot in 1:1 chat.
4. Bot validates message context and extracts nonce.
5. Bot calls `POST /telegram/verify/complete` with:
- `nonce`
- `telegram_user_id` (from Telegram update `from.id`)
- `telegram_username` (optional, from `from.username`)
6. Hub verifies nonce policy and stores `telegram_user_id` into the user profile.

## Bot-Side Required Checks
- Only accept `message.chat.type == "private"`.
- Only accept `/start <nonce>` format.
- Never trust user-submitted "telegram id" text; use Telegram update `from.id`.
- Use HTTPS to call hub.

## BotFather Settings
- Set `/setjoingroups` to `Disable` so the bot cannot be invited to group chats.

## Failure Codes from Hub
- `400 invalid_nonce`: nonce does not exist or already consumed
- `400 expired_nonce`: nonce is expired
- `400 max_attempts_reached`: nonce failed too many times (5)
- `409 telegram_id_already_linked`: Telegram account already linked to another user

## Example: Complete Verification
```bash
curl -X POST http://localhost:8000/telegram/verify/complete \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: <hub_api_key>" \
  -d '{
    "nonce": "NONCE_FROM_START_COMMAND",
    "telegram_user_id": "123456789",
    "telegram_username": "sample_user"
  }'
```

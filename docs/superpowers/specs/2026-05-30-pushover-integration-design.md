# Pushover Integration Design

**Date:** 2026-05-30
**Status:** Approved

## Summary

Replace all existing notification channels (Twilio SMS, Twilio WhatsApp, Meta WhatsApp) with Pushover as the primary channel, retaining SES email as the fallback. The result is a two-channel priority chain: Pushover → Email.

## Channel Priority

```
Pushover (if PUSHOVER_ENABLED) → SES Email
```

All Twilio and Meta WhatsApp code paths are removed entirely.

## Python Changes (`src/handlers/app.py`)

### Removed

- `_send_sms()` — Twilio SMS
- `_send_nudge_sms()` — SMS nudge accompanying the Sunday email
- `_send_whatsapp_twilio()` — Twilio WhatsApp
- `_send_whatsapp()` — Meta Cloud API WhatsApp
- Twilio client initialisation (`TwilioClient`, `_TWILIO_SID`, `_TWILIO_TOKEN`, `_TWILIO_CLIENT`)
- All `TWILIO_*` and `WHATSAPP_*` environment variable reads
- Meta WhatsApp SSM parameter load (`PARAM_WHATSAPP_ACCESS_TOKEN`)

### Added

`_send_pushover(message, title, url=None, url_title=None, priority=0)` — plain `urllib.request` POST to `https://api.pushover.net/1/messages.json`. No new library dependency.

Parameters posted:
- `token` — app token (from SSM)
- `user` — user key (from SSM)
- `message`, `title`, `url`, `url_title`
- `priority` (integer)
- `retry=30`, `expire=3600` added automatically when `priority=2` (emergency)

Errors are caught (`URLError`, `OSError`) and logged via `_log()` without crashing the handler.

### Priority Escalation

Used in `_notify_reminder` based on reminder count:

| Reminder count | Pushover priority | Behaviour |
|---|---|---|
| 0–1 | 0 (normal) | Standard delivery |
| 2–4 | 1 (high) | Bypasses quiet hours |
| 5+ | 2 (emergency) | Retries every 30s until acknowledged |

### Dispatcher Updates

Each of the three dispatchers becomes a clean two-branch if/else:

**`_notify_initial`**
- Pushover: `priority=0`, `url=confirm_url`, `url_title="Confirm filter cleaned ✓"`
- Else: `_send_email()` (no SMS nudge)

**`_notify_reminder`**
- Pushover: priority per escalation table above, no URL
- Else: `_send_sms()` removed; email-only fallback is not applicable here (reminders are push/SMS only) — if Pushover is not configured, this is a no-op with a log warning

**`_notify_congratulations`**
- Pushover: `priority=0`, no URL
- Else: `_send_congratulations_email()`

> Note: In email-only mode, daily reminders cannot be delivered (no SMS). This is acceptable — Pushover is expected to be the active channel in production.

### New Environment Variables

| Variable | Source | Purpose |
|---|---|---|
| `PARAM_PUSHOVER_APP_TOKEN` | Lambda env | SSM path for app token |
| `PARAM_PUSHOVER_USER_KEY` | Lambda env | SSM path for user key |

Both secrets loaded at cold start via `_load_parameters()`. `PUSHOVER_ENABLED` is then derived in Python (no separate env var needed):

```python
PUSHOVER_APP_TOKEN = _PARAMS.get("pushover_app_token", "")
PUSHOVER_USER_KEY  = _PARAMS.get("pushover_user_key", "")
PUSHOVER_ENABLED   = bool(PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY)
```

## Terraform Changes

### Variables (`variables.tf`)

Removed:
- `twilio_enabled`, `twilio_account_sid`, `twilio_auth_token`, `twilio_from_number`
- `twilio_whatsapp_enabled`, `twilio_whatsapp_from`
- `whatsapp_phone_number_id`, `whatsapp_access_token`
- `whatsapp_reminder_template`, `whatsapp_escalation_template`, `whatsapp_congrats_template`

Added:
- `pushover_app_token` (sensitive string)
- `pushover_user_key` (sensitive string)

### SSM Parameters (`main.tf`)

Remove: `aws_ssm_parameter.twilio_auth_token`, `aws_ssm_parameter.whatsapp_access_token`

Add: `aws_ssm_parameter.pushover_app_token`, `aws_ssm_parameter.pushover_user_key` (both `SecureString`)

### Locals (`locals.tf`)

Remove all `TWILIO_*` and `WHATSAPP_*` entries from `lambda_env`. Replace with:

```hcl
PARAM_PUSHOVER_APP_TOKEN = aws_ssm_parameter.pushover_app_token.name
PARAM_PUSHOVER_USER_KEY  = aws_ssm_parameter.pushover_user_key.name
```

### IAM

Update `ssm:GetParameter` policy to reference the two new Pushover parameter ARNs instead of the old Twilio/WhatsApp ones.

### `terraform.tfvars.example`

Replace Twilio/WhatsApp example values with:
```hcl
pushover_app_token = "your_app_token_here"
pushover_user_key  = "your_user_key_here"
```

## Tests (`tests/`)

### Removed
- Tests mocking Twilio client calls
- Tests mocking Meta WhatsApp HTTP calls

### Added

`_send_pushover` unit tests:
- Happy path: correct POST body, token, user key, message, url, priority
- Priority escalation: `priority=0` at count 0, `priority=1` at count 2, `priority=2` at count 5; emergency adds `retry`/`expire`
- Disabled path: `PUSHOVER_ENABLED=False` logs and returns without HTTP call
- Error handling: `URLError` caught and logged, handler does not raise

Dispatcher tests updated:
- Assert `_send_pushover` called when `PUSHOVER_ENABLED=True`
- Assert SES called when `PUSHOVER_ENABLED=False`

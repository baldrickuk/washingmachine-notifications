# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`washingmachine-notifications` — an AWS serverless solution that emails a weekly reminder to clean the washing machine filter every Sunday at 09:00 UK time, then sends daily SMS reminders at 08:00 UK time until the task is confirmed via a link in the email.

## Architecture

- **Lambda (Python 3.12)** — three handlers in `src/handlers/app.py`
- **DynamoDB** — one record per week (`WEEK#YYYY-MM-DD`), tracks status (`PENDING`/`CONFIRMED`) and which days SMS was sent
- **SES** — sends the weekly email with a confirmation link
- **SNS** — sends SMS directly to a phone number (no topic)
- **API Gateway (HTTP API)** — serves `GET /confirm?week=...&token=...`
- **EventBridge** — two schedule rules per trigger to cover GMT and BST (Lambda checks actual UK hour and skips if wrong)

## Build & Deploy

Prerequisites: AWS CLI configured, SAM CLI installed.

```bash
# First deploy only: copy the example config and fill in your values
cp samconfig.toml.example samconfig.toml
# Edit samconfig.toml: set WifeEmail, WifePhone (+44...), FromEmail

sam build
sam deploy        # --guided on first run if you skip samconfig.toml
```

## AWS one-time setup (before first deploy)

1. **SES — verify sender email**: AWS Console → SES → Verified identities → Create identity
2. **SES production access**: by default SES is in sandbox (can only send to verified addresses). Request production access if needed, or also verify the recipient email.
3. **SNS SMS**: check your SNS account spend limit in AWS Console → SNS → Text messaging (SMS). Default $1/month limit — raise it for production use.

## Key conventions

- `samconfig.toml` is gitignored (contains personal email/phone). Use `samconfig.toml.example` as the template.
- DST handling: EventBridge fires at both possible UTC times (e.g. 08:00 and 09:00 UTC for 09:00 UK). The Lambda checks `datetime.now(ZoneInfo("Europe/London")).hour` and exits early if it's not the right hour.
- DynamoDB TTL: records auto-expire after 30 days.

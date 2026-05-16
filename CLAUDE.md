# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`washingmachine-notifications` — an AWS serverless solution that emails a weekly reminder to clean the washing machine filter every Sunday at 09:00 UK time, then sends daily escalating reminders until the task is confirmed via a link.

## Architecture

- **Lambda (Python 3.12, arm64)** — four handlers in `src/handlers/app.py`
- **DynamoDB** — one record per week (`WEEK#YYYY-MM-DD`), tracks status (`PENDING`/`CONFIRMED`) and reminder history
- **SES** — sends the weekly reminder email and congratulations
- **API Gateway (HTTP API v2)** — serves `GET /confirm?week=...&token=...` (throttled 5 req/s)
- **CloudFront** — GB-only geo restriction in front of API Gateway
- **EventBridge** — two schedule rules per trigger to cover GMT and BST
- **Secrets Manager** — stores credentials and recipient PII
- **SQS DLQ** — catches Lambda failures after retries
- **SNS** — alert topic for CloudWatch alarms and delivery verification failures
- **CloudTrail** — DynamoDB data event audit log

## Infrastructure

Managed with **Terraform / OpenTofu** (`terraform/` directory).

## Build & Deploy

Prerequisites: OpenTofu (`tofu`) or Terraform (`terraform`), AWS CLI configured, Python 3.

```bash
# First deploy only: copy example vars and fill in your values
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
# Edit terraform/terraform.tfvars — set wife_email, wife_phone, from_email, alert_email

# Build the Lambda package (must run before plan/apply when source changes)
bash terraform/build.sh

# Deploy
cd terraform
tofu init
tofu apply
```

## Tests

```bash
pip install -r tests/requirements.txt
python -m pytest tests/ -v
```

## Key conventions

- `terraform/terraform.tfvars` is gitignored (contains personal email/phone).
- DST handling: EventBridge fires at both possible UTC times. Lambda checks `datetime.now(ZoneInfo("Europe/London")).hour` and exits early if wrong.
- DynamoDB TTL: records auto-expire after 30 days.
- Structured logging: use `_log(message, **context)` — emits JSON to CloudWatch.
- All print() is banned; use `_log()` to keep pylint 10/10.

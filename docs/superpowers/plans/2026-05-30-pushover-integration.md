# Pushover Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all Twilio SMS / WhatsApp channels with Pushover as the primary notification channel, retaining SES email as fallback.

**Architecture:** Add `_send_pushover()` using plain `urllib.request` (no new dependency). Dispatchers become clean two-branch if/else: Pushover when `PUSHOVER_ENABLED`, else SES email. All Twilio and Meta WhatsApp code is deleted entirely.

**Tech Stack:** Python 3.12, `urllib.request` + `urllib.parse` (stdlib), OpenTofu / Terraform, SSM Parameter Store (SecureString for tokens).

---

## File Map

| File | Action | What changes |
|---|---|---|
| `tests/conftest.py` | Modify | Remove Twilio/WhatsApp env vars; add empty Pushover param env vars |
| `tests/test_handlers.py` | Modify | Remove Twilio/WhatsApp tests; add `TestSendPushover` + `TestNotifyDispatchersPushover` |
| `src/handlers/app.py` | Modify | Remove Twilio/WhatsApp code; add `_send_pushover`; update dispatchers |
| `terraform/variables.tf` | Modify | Remove Twilio/WhatsApp vars; add `pushover_app_token`, `pushover_user_key` |
| `terraform/main.tf` | Modify | Remove Twilio/WhatsApp SSM params; add Pushover SSM params |
| `terraform/locals.tf` | Modify | Remove Twilio/WhatsApp `lambda_env` entries; add Pushover entries |
| `terraform/terraform.tfvars.example` | Modify | Replace Twilio/WhatsApp examples with Pushover |
| `terraform/build.sh` | Modify | Remove conditional Twilio SDK install block |
| `src/handlers/requirements.txt` | Modify | Remove Twilio comment |

---

## Task 1: Write failing tests

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/test_handlers.py`

- [ ] **Step 1: Update conftest.py — remove Twilio/WhatsApp env vars, add Pushover**

Replace the existing `os.environ.setdefault` block in `tests/conftest.py` so it reads:

```python
os.environ.setdefault("TABLE_NAME", "test-reminders")
os.environ.setdefault("FROM_EMAIL", "test@example.com")
os.environ.setdefault("ANIMAL_TYPE", "bunny")
os.environ.setdefault("API_BASE_URL", "https://test.example.com")
os.environ.setdefault("SECRETS_ARN", "")
os.environ.setdefault("ALERT_TOPIC_ARN", "")
os.environ.setdefault("PARAM_PUSHOVER_APP_TOKEN", "")
os.environ.setdefault("PARAM_PUSHOVER_USER_KEY", "")
```

(Remove: `TWILIO_ENABLED`, `TWILIO_ACCOUNT_SID`, `TWILIO_FROM_NUMBER`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_REMINDER_TEMPLATE`, `WHATSAPP_ESCALATION_TEMPLATE`, `WHATSAPP_CONGRATS_TEMPLATE`.)

Setting `PARAM_PUSHOVER_APP_TOKEN=""` and `PARAM_PUSHOVER_USER_KEY=""` means `_load_parameters` will skip SSM for these params, so `PUSHOVER_ENABLED` defaults to `False` in all tests — correct. Tests that need it `True` use `patch.object`.

- [ ] **Step 2: Add `TestSendPushover` to `tests/test_handlers.py`**

Add the following class **after** the existing `TestLog` class:

```python
import urllib.parse as _urllib_parse

class TestSendPushover:
    def _enabled_patches(self):
        return [
            patch.object(app, "PUSHOVER_ENABLED", True),
            patch.object(app, "PUSHOVER_APP_TOKEN", "app-token"),
            patch.object(app, "PUSHOVER_USER_KEY", "user-key"),
        ]

    def test_happy_path_posts_correct_body(self):
        with patch.object(app, "PUSHOVER_ENABLED", True), \
             patch.object(app, "PUSHOVER_APP_TOKEN", "app-token"), \
             patch.object(app, "PUSHOVER_USER_KEY", "user-key"), \
             patch("urllib.request.urlopen", return_value=MagicMock()) as mock_urlopen:
            app._send_pushover("Hello", "Title", url="https://example.com", url_title="Click", priority=0)
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        body = _urllib_parse.parse_qs(req.data.decode())
        assert body["token"] == ["app-token"]
        assert body["user"] == ["user-key"]
        assert body["message"] == ["Hello"]
        assert body["title"] == ["Title"]
        assert body["url"] == ["https://example.com"]
        assert body["url_title"] == ["Click"]
        assert body["priority"] == ["0"]
        assert "retry" not in body
        assert "expire" not in body

    def test_disabled_no_http_call(self):
        with patch.object(app, "PUSHOVER_ENABLED", False), \
             patch("urllib.request.urlopen") as mock_urlopen:
            app._send_pushover("Hello", "Title")
        mock_urlopen.assert_not_called()

    def test_emergency_priority_adds_retry_expire(self):
        with patch.object(app, "PUSHOVER_ENABLED", True), \
             patch.object(app, "PUSHOVER_APP_TOKEN", "app-token"), \
             patch.object(app, "PUSHOVER_USER_KEY", "user-key"), \
             patch("urllib.request.urlopen", return_value=MagicMock()) as mock_urlopen:
            app._send_pushover("Alert!", "Title", priority=2)
        req = mock_urlopen.call_args[0][0]
        body = _urllib_parse.parse_qs(req.data.decode())
        assert body["priority"] == ["2"]
        assert body["retry"] == ["30"]
        assert body["expire"] == ["3600"]

    def test_high_priority_no_retry_expire(self):
        with patch.object(app, "PUSHOVER_ENABLED", True), \
             patch.object(app, "PUSHOVER_APP_TOKEN", "app-token"), \
             patch.object(app, "PUSHOVER_USER_KEY", "user-key"), \
             patch("urllib.request.urlopen", return_value=MagicMock()) as mock_urlopen:
            app._send_pushover("Hello", "Title", priority=1)
        req = mock_urlopen.call_args[0][0]
        body = _urllib_parse.parse_qs(req.data.decode())
        assert "retry" not in body
        assert "expire" not in body

    def test_url_error_caught_no_raise(self):
        import urllib.error as _ue
        with patch.object(app, "PUSHOVER_ENABLED", True), \
             patch.object(app, "PUSHOVER_APP_TOKEN", "app-token"), \
             patch.object(app, "PUSHOVER_USER_KEY", "user-key"), \
             patch("urllib.request.urlopen", side_effect=_ue.URLError("network error")):
            app._send_pushover("Hello", "Title")  # must not raise

    def test_url_omitted_when_not_provided(self):
        with patch.object(app, "PUSHOVER_ENABLED", True), \
             patch.object(app, "PUSHOVER_APP_TOKEN", "app-token"), \
             patch.object(app, "PUSHOVER_USER_KEY", "user-key"), \
             patch("urllib.request.urlopen", return_value=MagicMock()) as mock_urlopen:
            app._send_pushover("Hello", "Title")
        req = mock_urlopen.call_args[0][0]
        body = _urllib_parse.parse_qs(req.data.decode())
        assert "url" not in body
        assert "url_title" not in body
```

- [ ] **Step 3: Add `TestNotifyDispatchersPushover` to `tests/test_handlers.py`**

Add the following class after `TestSendPushover`:

```python
class TestNotifyDispatchersPushover:
    def test_notify_initial_calls_pushover_when_enabled(self):
        with patch.object(app, "PUSHOVER_ENABLED", True), \
             patch.object(app, "_send_pushover") as mock_push:
            app._notify_initial("https://example.com/confirm?week=2026-05-17&token=abc", False)
        mock_push.assert_called_once()
        kwargs = mock_push.call_args.kwargs
        assert kwargs["url"] == "https://example.com/confirm?week=2026-05-17&token=abc"
        assert kwargs["url_title"] == "Confirm filter cleaned ✓"

    def test_notify_initial_calls_email_when_disabled(self):
        with patch.object(app, "PUSHOVER_ENABLED", False), \
             patch.object(app, "_send_email") as mock_email:
            app._notify_initial("https://example.com/confirm", False)
        mock_email.assert_called_once_with("https://example.com/confirm", False)

    def test_notify_reminder_priority_normal(self):
        with patch.object(app, "PUSHOVER_ENABLED", True), \
             patch.object(app, "_send_pushover") as mock_push:
            app._notify_reminder(0, date(2026, 5, 17))
        assert mock_push.call_args.kwargs["priority"] == 0

    def test_notify_reminder_priority_normal_count1(self):
        with patch.object(app, "PUSHOVER_ENABLED", True), \
             patch.object(app, "_send_pushover") as mock_push:
            app._notify_reminder(1, date(2026, 5, 17))
        assert mock_push.call_args.kwargs["priority"] == 0

    def test_notify_reminder_priority_high(self):
        with patch.object(app, "PUSHOVER_ENABLED", True), \
             patch.object(app, "_send_pushover") as mock_push:
            app._notify_reminder(2, date(2026, 5, 17))
        assert mock_push.call_args.kwargs["priority"] == 1

    def test_notify_reminder_priority_high_count4(self):
        with patch.object(app, "PUSHOVER_ENABLED", True), \
             patch.object(app, "_send_pushover") as mock_push:
            app._notify_reminder(4, date(2026, 5, 17))
        assert mock_push.call_args.kwargs["priority"] == 1

    def test_notify_reminder_priority_emergency(self):
        with patch.object(app, "PUSHOVER_ENABLED", True), \
             patch.object(app, "_send_pushover") as mock_push:
            app._notify_reminder(5, date(2026, 5, 17))
        assert mock_push.call_args.kwargs["priority"] == 2

    def test_notify_reminder_noop_when_disabled(self, capsys):
        import json as _json
        with patch.object(app, "PUSHOVER_ENABLED", False), \
             patch.object(app, "_send_pushover") as mock_push:
            app._notify_reminder(0, date(2026, 5, 17))
        mock_push.assert_not_called()
        out = capsys.readouterr().out.strip()
        assert _json.loads(out)["level"] == "WARNING"

    def test_notify_congratulations_calls_pushover_when_enabled(self):
        with patch.object(app, "PUSHOVER_ENABLED", True), \
             patch.object(app, "_send_pushover") as mock_push, \
             patch.object(app, "_fetch_animal_image", return_value=""):
            app._notify_congratulations(0, "bunny")
        mock_push.assert_called_once()

    def test_notify_congratulations_calls_email_when_disabled(self):
        with patch.object(app, "PUSHOVER_ENABLED", False), \
             patch.object(app, "_send_congratulations_email") as mock_email:
            app._notify_congratulations(0, "bunny")
        mock_email.assert_called_once_with(0, "bunny")
```

- [ ] **Step 4: Run tests — confirm new tests fail**

```bash
cd /home/bob/projects/washingmachine-notifications
python -m pytest tests/ -v -k "Pushover" 2>&1 | head -40
```

Expected: `AttributeError: module 'app' has no attribute '_send_pushover'` (or similar). All `TestSendPushover` and `TestNotifyDispatchersPushover` tests should fail.

- [ ] **Step 5: Confirm existing tests still pass**

```bash
python -m pytest tests/ -v -k "not Pushover" 2>&1 | tail -20
```

Expected: all existing tests PASS (conftest changes don't break them because the removed env vars had safe defaults in app.py code).

---

## Task 2: Implement Pushover in `app.py`

**Files:**
- Modify: `src/handlers/app.py`

- [ ] **Step 1: Replace imports block — add `urllib.parse`**

Change the imports at the top of `src/handlers/app.py`:

```python
"""Lambda handlers for the washing machine filter reminder system."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

import boto3
from botocore.exceptions import ClientError
```

- [ ] **Step 2: Replace `_load_parameters` — swap Twilio/WhatsApp for Pushover**

Replace the entire `_load_parameters` function (lines 23–40 of the original):

```python
def _load_parameters() -> dict:
    """Fetch sensitive credentials from SSM Parameter Store."""
    client = boto3.client("ssm")
    params = {}
    for env_key, param_name in [
        ("PARAM_PUSHOVER_APP_TOKEN", "pushover_app_token"),
        ("PARAM_PUSHOVER_USER_KEY", "pushover_user_key"),
        ("PARAM_WIFE_EMAIL", "wife_email"),
        ("PARAM_WIFE_PHONE", "wife_phone"),
    ]:
        param_path = os.environ.get(env_key, "")
        if param_path:
            try:
                response = client.get_parameter(Name=param_path, WithDecryption=True)
                params[param_name] = response["Parameter"]["Value"]
            except ClientError as exc:
                _log(f"Failed to load parameter {param_path}", level="WARNING", error=str(exc))
    return params
```

- [ ] **Step 3: Replace module-level credential vars — remove Twilio/WhatsApp, add Pushover**

Replace everything from `_PARAMS = _load_parameters()` down to (and including) the `_TWILIO_CLIENT = None` line and the entire WhatsApp block, so that section reads:

```python
_PARAMS = _load_parameters()

WIFE_EMAIL = _PARAMS.get("wife_email") or os.environ.get("WIFE_EMAIL", "")
WIFE_PHONE = _PARAMS.get("wife_phone") or os.environ.get("WIFE_PHONE", "")

# --- Pushover (optional push notification provider) ---
PUSHOVER_APP_TOKEN = _PARAMS.get("pushover_app_token", "")
PUSHOVER_USER_KEY  = _PARAMS.get("pushover_user_key", "")
PUSHOVER_ENABLED   = bool(PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY)

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)
ses = boto3.client("ses")
sns = boto3.client("sns")
```

- [ ] **Step 4: Replace `_notify_initial`**

Replace the entire `_notify_initial` function:

```python
def _notify_initial(confirm_url: str, is_test: bool):
    """Send the initial weekly reminder via the configured channel."""
    if PUSHOVER_ENABLED:
        prefix = "[TEST] " if is_test else ""
        _send_pushover(
            message=f"{prefix}It's time to clean the washing machine filter!",
            title="Washing Machine Filter Reminder",
            url=confirm_url,
            url_title="Confirm filter cleaned ✓",
        )
    else:
        _send_email(confirm_url, is_test)
```

- [ ] **Step 5: Replace `_notify_reminder`**

Replace the entire `_notify_reminder` function:

```python
def _notify_reminder(sms_count: int, sunday: date):
    """Send an escalating reminder via the configured channel."""
    if PUSHOVER_ENABLED:
        if sms_count <= 1:
            priority = 0
        elif sms_count <= 4:
            priority = 1
        else:
            priority = 2
        _send_pushover(
            message=_escalating_sms(sms_count, sunday),
            title="Washing Machine Filter Reminder",
            priority=priority,
        )
    else:
        _log("Reminder skipped", reason="Pushover not configured", level="WARNING")
```

- [ ] **Step 6: Replace `_notify_congratulations`**

Replace the entire `_notify_congratulations` function:

```python
def _notify_congratulations(sms_count: int, animal: str):
    """Send a congratulations message via the configured channel."""
    if PUSHOVER_ENABLED:
        image_url = _fetch_animal_image(animal)
        body = (
            f"🎉 {_sms_commentary(sms_count)}\n\nAs your reward: {image_url}"
            if image_url
            else f"🎉 {_sms_commentary(sms_count)}"
        )
        _send_pushover(
            message=body,
            title="Filter cleaned! 🎉",
        )
    else:
        _send_congratulations_email(sms_count, animal)
```

- [ ] **Step 7: Delete `_send_whatsapp` (Meta Cloud API section)**

Delete the entire section from the `# ---------------------------------------------------------------------------` comment above `_send_whatsapp` through the closing of that function (the `_log("WhatsApp sent", ...)` line and its closing brace).

The deleted block is:
```python
# ---------------------------------------------------------------------------
# WhatsApp — Meta Cloud API
# ---------------------------------------------------------------------------

def _send_whatsapp(template_name: str, body_params: list):
    ...entire function body...
```

- [ ] **Step 8: Delete `_send_sms`, `_send_whatsapp_twilio`, and the SMS section header**

Delete the entire section:
```python
# ---------------------------------------------------------------------------
# SMS (Twilio only — opt-in)
# ---------------------------------------------------------------------------

def _send_sms(body: str):
    ...

def _send_whatsapp_twilio(message: str, is_test: bool = False):
    ...
```

- [ ] **Step 9: Delete `_send_nudge_sms`**

Delete the entire section:
```python
# ---------------------------------------------------------------------------
# Initial SMS nudge — used in email+SMS mode only
# ---------------------------------------------------------------------------

def _send_nudge_sms(is_test: bool = False):
    ...
```

- [ ] **Step 10: Add `_send_pushover` function**

Insert the following new section **after the `_log` function** and **before the `_notify_initial` dispatcher**:

```python
# ---------------------------------------------------------------------------
# Pushover push notifications
# ---------------------------------------------------------------------------

def _send_pushover(
    message: str,
    title: str,
    url: str = None,
    url_title: str = None,
    priority: int = 0,
) -> None:
    """POST a push notification to the Pushover API."""
    if not PUSHOVER_ENABLED:
        _log("Pushover skipped", reason="not configured")
        return
    payload = {
        "token": PUSHOVER_APP_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "message": message,
        "title": title,
        "priority": priority,
    }
    if url:
        payload["url"] = url
    if url_title:
        payload["url_title"] = url_title
    if priority == 2:
        payload["retry"] = 30
        payload["expire"] = 3600
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(
        "https://api.pushover.net/1/messages.json",
        data=data,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            _log("Pushover sent", title=title, priority=priority, status=r.status)
    except (urllib.error.URLError, OSError) as exc:
        _log("Pushover send failed", error=str(exc), level="WARNING")
```

- [ ] **Step 11: Run all tests — confirm pass**

```bash
cd /home/bob/projects/washingmachine-notifications
python -m pytest tests/ -v 2>&1 | tail -30
```

Expected: all tests PASS including the new `TestSendPushover` and `TestNotifyDispatchersPushover` classes.

- [ ] **Step 12: Commit Python changes**

```bash
git add src/handlers/app.py tests/conftest.py tests/test_handlers.py
git commit -m "feat: replace Twilio/WhatsApp with Pushover notifications

Two-channel priority chain: Pushover (push) → SES email fallback.
Removes Twilio SMS, Twilio WhatsApp, and Meta Cloud API WhatsApp.
_send_pushover uses stdlib urllib.request — no new dependency.
Priority escalates: normal (0–1 reminders), high (2–4), emergency (5+).

Co-Authored-By: claude[bot] <claude[bot]@users.noreply.github.com>"
```

---

## Task 3: Terraform changes

**Files:**
- Modify: `terraform/variables.tf`
- Modify: `terraform/main.tf`
- Modify: `terraform/locals.tf`
- Modify: `terraform/terraform.tfvars.example`

- [ ] **Step 1: Replace Twilio/WhatsApp vars with Pushover in `variables.tf`**

Delete all of these variable blocks:
- `variable "twilio_enabled"` (lines 41–45)
- `variable "twilio_account_sid"` (lines 47–51)
- `variable "twilio_auth_token"` (lines 53–58)
- `variable "twilio_from_number"` (lines 60–64)
- `variable "twilio_whatsapp_enabled"` (lines 66–70)
- `variable "twilio_whatsapp_from"` (lines 72–76)
- `variable "whatsapp_phone_number_id"` (lines 78–82)
- `variable "whatsapp_access_token"` (lines 84–89)
- `variable "whatsapp_reminder_template"` (lines 91–95)
- `variable "whatsapp_escalation_template"` (lines 97–101)
- `variable "whatsapp_congrats_template"` (lines 103–107)

Add in their place:

```hcl
variable "pushover_app_token" {
  description = "Pushover application token (stored in SSM SecureString)"
  type        = string
  sensitive   = true
}

variable "pushover_user_key" {
  description = "Pushover user key (stored in SSM SecureString)"
  type        = string
  sensitive   = true
}
```

- [ ] **Step 2: Replace Twilio/WhatsApp SSM params with Pushover in `main.tf`**

Delete the `aws_ssm_parameter.twilio_auth_token` resource:
```hcl
resource "aws_ssm_parameter" "twilio_auth_token" {
  name  = "/${var.stack_name}/twilio_auth_token"
  type  = "SecureString"
  value = var.twilio_auth_token

  lifecycle {
    ignore_changes = [value]
  }
}
```

Delete the `aws_ssm_parameter.whatsapp_access_token` resource:
```hcl
resource "aws_ssm_parameter" "whatsapp_access_token" {
  count = var.whatsapp_access_token != "" ? 1 : 0

  name  = "/${var.stack_name}/whatsapp_access_token"
  type  = "SecureString"
  value = var.whatsapp_access_token

  lifecycle {
    ignore_changes = [value]
  }
}
```

Add in their place:

```hcl
resource "aws_ssm_parameter" "pushover_app_token" {
  name  = "/${var.stack_name}/pushover_app_token"
  type  = "SecureString"
  value = var.pushover_app_token

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "pushover_user_key" {
  name  = "/${var.stack_name}/pushover_user_key"
  type  = "SecureString"
  value = var.pushover_user_key

  lifecycle {
    ignore_changes = [value]
  }
}
```

- [ ] **Step 3: Replace `lambda_env` Twilio/WhatsApp entries in `locals.tf`**

Replace the entire `locals` block content with:

```hcl
locals {
  lambda_zip = "${path.module}/.lambda.zip"

  lambda_env = {
    TABLE_NAME               = aws_dynamodb_table.reminders.name
    FROM_EMAIL               = var.from_email
    ANIMAL_TYPE              = var.animal_type
    PARAM_PUSHOVER_APP_TOKEN = aws_ssm_parameter.pushover_app_token.name
    PARAM_PUSHOVER_USER_KEY  = aws_ssm_parameter.pushover_user_key.name
    PARAM_WIFE_EMAIL         = aws_ssm_parameter.wife_email.name
    PARAM_WIFE_PHONE         = aws_ssm_parameter.wife_phone.name
    ALERT_TOPIC_ARN          = aws_sns_topic.alerts.arn
  }

  common_tags = {
    Project     = var.stack_name
    Environment = "production"
    ManagedBy   = "opentofu"
  }
}
```

- [ ] **Step 4: Update `terraform.tfvars.example`**

Replace the entire file contents with:

```hcl
aws_region  = "eu-west-2"
stack_name  = "washingmachine-notifications"

# Recipient details (stored in SSM on deploy — never in Lambda env vars)
wife_email  = "recipient@example.com"
wife_phone  = "+447700000000"

# Email configuration
from_email  = "reminders@yourdomain.com"
alert_email = "ops@yourdomain.com"

# Reward animal (bunny, cat, dog, fox)
animal_type = "bunny"

# Pushover credentials (https://pushover.net — create an application to get app token)
pushover_app_token = "your_app_token_here"
pushover_user_key  = "your_user_key_here"
```

- [ ] **Step 5: Commit Terraform changes**

```bash
git add terraform/variables.tf terraform/main.tf terraform/locals.tf terraform/terraform.tfvars.example
git commit -m "feat(terraform): replace Twilio/WhatsApp with Pushover SSM params

Remove twilio_auth_token and whatsapp_access_token SSM parameters.
Add pushover_app_token and pushover_user_key as SecureString params.
Update lambda_env to pass new PARAM_PUSHOVER_* paths to functions.

Co-Authored-By: claude[bot] <claude[bot]@users.noreply.github.com>"
```

---

## Task 4: Build script and Lambda requirements cleanup

**Files:**
- Modify: `terraform/build.sh`
- Modify: `src/handlers/requirements.txt`

- [ ] **Step 1: Remove Twilio conditional install block from `build.sh`**

Delete these lines from `terraform/build.sh`:

```bash
# Install Twilio only when enabled — it adds ~29 MB to the package
if [ "${TWILIO_ENABLED:-false}" = "true" ]; then
  echo "Installing Twilio SDK (TWILIO_ENABLED=true)..."
  pip3 install "twilio>=9.0" -t "${BUILD_DIR}" --quiet --no-cache-dir
fi
```

- [ ] **Step 2: Clean up `src/handlers/requirements.txt`**

Replace the entire file with:

```
# boto3 is provided by the Lambda Python 3.12 runtime.
# No additional runtime dependencies are needed.
boto3>=1.34
```

- [ ] **Step 3: Run tests one final time to confirm everything is clean**

```bash
cd /home/bob/projects/washingmachine-notifications
python -m pytest tests/ -v 2>&1 | tail -15
```

Expected: all tests PASS, zero failures.

- [ ] **Step 4: Commit build script changes**

```bash
git add terraform/build.sh src/handlers/requirements.txt
git commit -m "chore: remove Twilio build dependency from build script

Twilio SDK conditional install removed — no longer needed.
Lambda package now relies only on stdlib and the AWS runtime boto3.

Co-Authored-By: claude[bot] <claude[bot]@users.noreply.github.com>"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] `_send_pushover()` added with `urllib.request` POST — Task 2 Step 10
- [x] `token`, `user`, `message`, `title`, `url`, `url_title`, `priority` in POST body — Task 2 Step 10
- [x] `retry=30`, `expire=3600` added when `priority=2` — Task 2 Step 10
- [x] `URLError`/`OSError` caught, logged, not re-raised — Task 2 Step 10
- [x] `PUSHOVER_ENABLED` derived from `bool(PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY)` — Task 2 Step 3
- [x] Priority escalation: 0–1→0, 2–4→1, 5+→2 — Task 2 Steps 5
- [x] `_notify_initial` sends Pushover with URL+url_title, else email — Task 2 Steps 4
- [x] `_notify_reminder` sends Pushover with priority, else logs WARNING — Task 2 Step 5
- [x] `_notify_congratulations` sends Pushover, else congratulations email — Task 2 Step 6
- [x] All Twilio functions removed — Task 2 Steps 7–9
- [x] WhatsApp function removed — Task 2 Step 7
- [x] `TWILIO_*` and `WHATSAPP_*` env var reads removed — Task 2 Steps 2–3
- [x] `PARAM_WHATSAPP_ACCESS_TOKEN` SSM load removed — Task 2 Step 2
- [x] Twilio client init removed — Task 2 Step 3
- [x] `PARAM_PUSHOVER_APP_TOKEN` + `PARAM_PUSHOVER_USER_KEY` env vars in Terraform — Task 3 Steps 1–3
- [x] Pushover SSM params as `SecureString` — Task 3 Step 2
- [x] IAM: no change needed (wildcard already covers `/${var.stack_name}/*`)
- [x] `terraform.tfvars.example` updated — Task 3 Step 4
- [x] Tests: happy path, disabled path, error handling, priority escalation, dispatcher dispatch — Task 1 Steps 2–3
- [x] No new library dependency (stdlib only) — Task 2 Step 10

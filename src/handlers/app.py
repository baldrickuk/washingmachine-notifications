"""Lambda handlers for the washing machine filter reminder system."""
import hmac
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

LONDON_TZ = ZoneInfo("Europe/London")
TEST_SMS_INTERVAL_SECONDS = int(os.environ.get("TEST_SMS_INTERVAL_SECONDS", "30"))

TABLE_NAME = os.environ["TABLE_NAME"]
FROM_EMAIL = os.environ["FROM_EMAIL"]
API_BASE_URL = os.environ.get("API_BASE_URL", "")
ANIMAL_TYPE = os.environ.get("ANIMAL_TYPE", "bunny")
ALERT_TOPIC_ARN = os.environ.get("ALERT_TOPIC_ARN", "")

# --- SSM Parameter Store (fetched once at cold start, cached for Lambda lifetime) ---
def _load_parameters() -> dict:
    """Fetch sensitive credentials from SSM Parameter Store."""
    client = boto3.client("ssm")
    params = {}
    for env_key, param_name in [
        ("PARAM_PUSHOVER_APP_TOKEN", "pushover_app_token"),
        ("PARAM_PUSHOVER_USER_KEY", "pushover_user_key"),
        ("PARAM_ORIGIN_VERIFY_TOKEN", "origin_verify_token"),
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

_PARAMS = _load_parameters()

WIFE_EMAIL = _PARAMS.get("wife_email") or os.environ.get("WIFE_EMAIL", "")
WIFE_PHONE = _PARAMS.get("wife_phone") or os.environ.get("WIFE_PHONE", "")

# --- Pushover (optional push notification provider) ---
PUSHOVER_APP_TOKEN = _PARAMS.get("pushover_app_token", "")
PUSHOVER_USER_KEY  = _PARAMS.get("pushover_user_key", "")
PUSHOVER_ENABLED   = bool(PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY)

# --- Origin verify (CloudFront shared secret — blocks direct execute-api access) ---
ORIGIN_VERIFY_TOKEN   = _PARAMS.get("origin_verify_token", "")
ORIGIN_VERIFY_ENABLED = bool(ORIGIN_VERIFY_TOKEN)

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)
ses = boto3.client("ses")
sns = boto3.client("sns")


# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------

def _log(message: str, level: str = "INFO", **context) -> None:
    """Emit a structured JSON log entry captured by CloudWatch Logs."""
    print(json.dumps({"level": level, "message": message, **context}))


# ---------------------------------------------------------------------------
# Pushover push notifications
# ---------------------------------------------------------------------------

def _send_pushover(
    message: str,
    title: str,
    url: str = None,
    url_title: str = None,
    priority: int = 0,
    html: bool = False,
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
    if html:
        payload["html"] = 1
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
            _log("Pushover sent", title=title, priority=priority, status=str(r.status))
    except (urllib.error.URLError, OSError) as exc:
        _log("Pushover send failed", error=str(exc), level="WARNING")


# ---------------------------------------------------------------------------
# Channel-agnostic notification dispatchers
# ---------------------------------------------------------------------------

def _notify_initial(confirm_url: str, is_test: bool):
    """Send the initial weekly reminder via the configured channel."""
    if PUSHOVER_ENABLED:
        title = "[TEST] 🧺 Sunday. You know what that means." if is_test else "🧺 Sunday. You know what that means."
        _send_pushover(
            message=(
                "<b>The washing machine filter requires your attention.</b>\n\n"
                "Tap to confirm once done — or tomorrow begins "
                "<i>Day 1</i> of what will become an increasingly dramatic escalation sequence.\n\n"
                f"<a href=\"{confirm_url}\"><b>✓ Done — confirm here</b></a>\n\n"
                "<font color=\"#888888\">The filter is watching. It has all week.</font>"
            ),
            title=title,
            html=True,
        )
    else:
        _send_email(confirm_url, is_test)


def _notify_reminder(sms_count: int, sunday: date):
    """Send an escalating reminder via the configured channel."""
    if PUSHOVER_ENABLED:
        if sms_count <= 1:
            priority = 0
        elif sms_count <= 4:
            priority = 1
        else:
            priority = 2
        if sms_count <= 1:
            reminder_title = "🧺 Friendly reminder"
            plain = _escalating_sms(sms_count, sunday)
            message = plain
        elif sms_count <= 4:
            reminder_title = "⚠️ Still waiting…"
            plain = _escalating_sms(sms_count, sunday)
            message = f"<font color=\"#E67E00\">{plain}</font>"
        else:
            reminder_title = "🚨 FILTER EMERGENCY"
            plain = _escalating_sms(sms_count, sunday)
            message = f"<font color=\"#C0392B\"><b>{plain}</b></font>"
        _send_pushover(
            message=message,
            title=reminder_title,
            priority=priority,
            html=sms_count > 1,
        )
    else:
        _log("Reminder skipped", reason="Pushover not configured", level="WARNING")


def _notify_congratulations(sms_count: int, animal: str):
    """Send a congratulations message via the configured channel."""
    if PUSHOVER_ENABLED:
        image_url = _fetch_animal_image(animal)
        commentary = _sms_commentary(sms_count)
        if image_url:
            body = (
                f"<font color=\"#27AE60\"><b>{commentary}</b></font>"
                f"\n\nAs your reward: <a href=\"{image_url}\">your {animal} awaits →</a>"
            )
        else:
            body = f"<font color=\"#27AE60\"><b>{commentary}</b></font>"
        _send_pushover(
            message=body,
            title="🎉 The filter has been cleaned. Peace is restored.",
            html=True,
        )
    else:
        _send_congratulations_email(sms_count, animal)


def _now_london() -> datetime:
    return datetime.now(LONDON_TZ)


def _this_weeks_sunday(reference: datetime) -> date:
    d = reference.date()
    return d if d.weekday() == 6 else d - timedelta(days=d.weekday() + 1)


def _week_pk(sunday: date, test: bool = False) -> str:
    prefix = "TEST" if test else "WEEK"
    return f"{prefix}#{sunday.isoformat()}"


# ---------------------------------------------------------------------------
# Handler: send weekly email (Sunday 09:00 UK time)
# ---------------------------------------------------------------------------

def send_weekly_email(event, _context):
    """Send the initial weekly filter-cleaning reminder via the configured channel."""
    is_test = bool(event.get("test"))
    now = _now_london()

    if not is_test and (now.weekday() != 6 or now.hour != 9):
        _log("DST guard: skipping", weekday=now.strftime("%A"), hour=now.hour)
        return

    sunday = now.date()
    pk = _week_pk(sunday, is_test)

    existing = table.get_item(Key={"PK": pk}).get("Item")
    if existing:
        if is_test:
            table.delete_item(Key={"PK": pk})
            _log("Cleared previous test record", pk=pk)
        else:
            _log("Notification already sent", pk=pk)
            return

    token = str(uuid.uuid4())
    ttl = int((now + timedelta(days=30)).timestamp())

    table.put_item(Item={
        "PK": pk,
        "status": "PENDING",
        "token": token,
        "email_sent_at": now.isoformat(),
        "sms_dates": [],
        "ttl": ttl,
    })

    confirm_url = (
        f"{API_BASE_URL}/confirm"
        f"?week={sunday.isoformat()}&token={token}"
        + ("&test=1" if is_test else "")
    )
    _notify_initial(confirm_url, is_test)
    _log("Notification sent", pk=pk, test=is_test)


def _send_email(confirm_url: str, is_test: bool = False):
    subject = (
        "[TEST] Weekly reminder: clean the washing machine filter"
        if is_test
        else "Weekly reminder: clean the washing machine filter"
    )
    ses.send_email(
        Source=FROM_EMAIL,
        Destination={"ToAddresses": [WIFE_EMAIL]},
        Message={
            "Subject": {"Data": subject},
            "Body": {
                "Html": {"Data": _email_html(confirm_url, is_test)},
                "Text": {"Data": _email_text(confirm_url)},
            },
        },
    )


def _email_html(confirm_url: str, is_test: bool = False) -> str:
    test_banner = (
        '<div style="background:#ff9800;color:#fff;padding:10px;text-align:center;'
        'font-weight:bold;border-radius:6px 6px 0 0;">'
        "TEST MODE — SMS reminders every 10 minutes</div>"
        if is_test else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:30px 0;">
    <tr><td align="center">
      <table width="100%" style="max-width:560px;background:#ffffff;border-radius:8px;box-sizing:border-box;overflow:hidden;">
        <tr><td>{test_banner}
          <div style="padding:40px;">
            <h2 style="margin:0 0 16px;color:#333;">Washing Machine Filter Reminder</h2>
            <p style="color:#555;line-height:1.6;">Hi! This is your weekly reminder to clean the washing machine filter.</p>
            <p style="color:#555;line-height:1.6;">Once you've done it, please tap the button below to confirm — otherwise you'll get a daily text reminder at 08:00.</p>
            <div style="text-align:center;margin:32px 0;">
              <a href="{confirm_url}"
                 style="display:inline-block;background:#2e7d32;color:#ffffff;padding:14px 32px;
                        border-radius:6px;text-decoration:none;font-size:16px;font-weight:bold;">
                I've cleaned the filter ✓
              </a>
            </div>
            <p style="color:#999;font-size:12px;line-height:1.5;">
              If the button doesn't work, copy and paste this link:<br>
              <a href="{confirm_url}" style="color:#1565c0;word-break:break-all;">{confirm_url}</a>
            </p>
          </div>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _email_text(confirm_url: str) -> str:
    return (
        "Washing Machine Filter Reminder\n\n"
        "Hi! This is your weekly reminder to clean the washing machine filter.\n\n"
        "Once you've done it, please visit the link below to confirm — otherwise "
        "you'll get a daily text reminder at 08:00.\n\n"
        f"Confirm here: {confirm_url}\n"
    )


# ---------------------------------------------------------------------------
# Escalating SMS/WhatsApp messages
# ---------------------------------------------------------------------------

_SMS_MESSAGES = [
    # 1 — gentle
    "Morning! Just a reminder to clean the washing machine filter. "
    "Check your email for the confirmation link once done.",

    # 2 — friendly nudge
    "Day 2: Still waiting on that filter! It won't clean itself "
    "(believe me, we checked). Email has the link.",

    # 3 — mildly dramatic
    "Day 3: The filter is starting to feel forgotten. It stares sadly "
    "at the drum every cycle. Please clean it and confirm via the link in your email.",

    # 4 — filter gains sentience
    "Day 4: The filter has begun keeping a journal. Entry 1: 'Still unclean. "
    "Still unloved.' Please end its suffering. Email has the link.",

    # 5 — legal threats emerge
    "Day 5: The filter has engaged legal counsel and is exploring its options. "
    "A strongly-worded letter is being drafted. PLEASE clean it. Email has the link.",

    # 6 — industrial action
    "Day 6: The washing machine has announced a work-to-rule in solidarity "
    "with the filter. Laundry production is at risk. Clean. The. Filter. Email has the link.",

    # 7 — full crisis
    "Day 7: ONE WEEK. The filter has gone to the press. The headline reads: "
    "'NEGLECTED FILTER SUFFERS IN SILENCE'. This is now a household emergency. "
    "Check your email. Confirm. IMMEDIATELY.",

    # 8 — existential
    "Day 8: At this point the filter has accepted its fate and is making peace "
    "with the universe. We have not. Clean it NOW. The link is in your email. "
    "There will be consequences.",

    # 9+ — maximum stern (repeats)
    "ANOTHER DAY. STILL UNCLEAN. The filter has written its will and left "
    "everything to the spin cycle. This is your FINAL warning (again). "
    "Email. Link. Filter. NOW.",
]


def _escalating_sms(sms_count: int, sunday: date) -> str:
    index = min(sms_count, len(_SMS_MESSAGES) - 1)
    msg = _SMS_MESSAGES[index]
    if sms_count == 0:
        sunday_fmt = sunday.strftime("%-d %B")
        return f"Washing machine filter reminder (requested {sunday_fmt}): {msg}"
    return msg


# ---------------------------------------------------------------------------
# Handler: send daily reminder (08:00 UK time) while unconfirmed
# ---------------------------------------------------------------------------

def send_daily_sms(event, _context):
    """Send an escalating reminder if this week's task is still pending."""
    is_test = bool(event.get("test"))
    now = _now_london()

    if not is_test and now.hour != 8:
        _log("DST guard: skipping", hour=now.hour)
        return

    sunday = now.date() if is_test else _this_weeks_sunday(now)
    pk = _week_pk(sunday, is_test)

    response = table.get_item(Key={"PK": pk})
    if "Item" not in response:
        _log("No record found", pk=pk)
        return

    item = response["Item"]

    if item["status"] == "CONFIRMED":
        _log("Already confirmed", pk=pk)
        return

    if is_test:
        last_sms_at = item.get("last_sms_at")
        if last_sms_at:
            elapsed = (now - datetime.fromisoformat(last_sms_at)).total_seconds()
            if elapsed < TEST_SMS_INTERVAL_SECONDS:
                _log("Test reminder throttled", elapsed_seconds=int(elapsed))
                return
    else:
        today_str = now.date().isoformat()
        if today_str in item.get("sms_dates", []):
            _log("Reminder already sent today", date=today_str, pk=pk)
            return

    sms_count = len(item.get("sms_dates", []))
    _notify_reminder(sms_count, sunday)

    dedup_value = now.isoformat() if is_test else now.date().isoformat()
    update_expr = "SET sms_dates = :dates" + (", last_sms_at = :last" if is_test else "")
    expr_values: dict = {":dates": list(item.get("sms_dates", [])) + [dedup_value]}
    if is_test:
        expr_values[":last"] = now.isoformat()

    table.update_item(
        Key={"PK": pk},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_values,
    )
    _log("Reminder sent", pk=pk, reminder_number=sms_count + 1, test=is_test)


# ---------------------------------------------------------------------------
# Handler: Monday post-deploy verification (09:01 UK time)
# ---------------------------------------------------------------------------

def verify_delivery(event, _context):
    """Check that last Sunday's reminder was sent; alert via SNS if not."""
    is_test = bool(event.get("test"))
    now = _now_london()

    if not is_test and (now.weekday() != 0 or now.hour != 9):
        _log("DST guard: skipping", weekday=now.strftime("%A"), hour=now.hour)
        return

    last_sunday = now.date() - timedelta(days=now.weekday() + 1)
    pk = _week_pk(last_sunday)

    response = table.get_item(Key={"PK": pk})
    if "Item" in response and response["Item"].get("email_sent_at"):
        _log("Delivery verified", pk=pk, status=response["Item"].get("status"))
        return

    message = (
        f"ALERT: No reminder record found for {pk}. "
        "The Sunday notification may not have been sent. "
        "Check CloudWatch logs and the DLQ."
    )
    _log("Delivery verification FAILED", pk=pk, level="ERROR")

    if ALERT_TOPIC_ARN:
        sns.publish(
            TopicArn=ALERT_TOPIC_ARN,
            Subject="washingmachine-notifications: Sunday reminder not sent",
            Message=message,
        )


# ---------------------------------------------------------------------------
# Animal image fetching
# ---------------------------------------------------------------------------

def _fetch_animal_image(animal: str) -> str:
    """Return a direct image URL for the given animal. Falls back to empty string on any error."""
    animal = animal.lower().strip()
    try:
        if animal == "cat":
            with urllib.request.urlopen(
                "https://api.thecatapi.com/v1/images/search?limit=1&mime_types=jpg,png",
                timeout=5,
            ) as r:
                return json.loads(r.read())[0]["url"]

        if animal == "dog":
            with urllib.request.urlopen(
                "https://dog.ceo/api/breeds/image/random", timeout=5
            ) as r:
                return json.loads(r.read())["message"]

        if animal == "fox":
            with urllib.request.urlopen(
                "https://randomfox.ca/floof/", timeout=5
            ) as r:
                return json.loads(r.read())["image"]

        if animal == "bunny":
            with urllib.request.urlopen(
                "https://api.bunnies.io/v2/loop/random/?media=gif,png", timeout=5
            ) as r:
                return json.loads(r.read())["media"]["poster"]

        search_term = animal
        req = urllib.request.Request(
            f"https://loremflickr.com/640/480/{search_term}/all",
            headers={"User-Agent": "WashingMachineReminder/1.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.url

    except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError) as exc:
        _log("Could not fetch animal image", animal=animal, error=str(exc), level="WARNING")
        return ""


def _animal_caption(animal: str) -> str:
    captions = {
        "cat": "This cat is… mildly impressed. For a cat, that is basically a standing ovation.",
        "dog": "This dog is SO PROUD OF YOU. They have been waiting for this moment all week.",
        "fox": "This fox respects your hustle.",
        "bunny": "This bunny is beaming with pride. Look at that face. Pure, uncut pride.",
    }
    return captions.get(animal.lower(), f"This {animal} salutes you.")


def _sms_commentary(sms_count: int) -> str:
    if sms_count == 0:
        return (
            "You actioned this on the very first email. "
            "An absolute titan of domestic responsibility. "
            "A legend in your own lifetime."
        )
    if sms_count == 1:
        return "It took one gentle nudge. Honestly, practically immediate. Well done."
    if sms_count == 2:
        return (
            "Two reminders. That is basically the same as doing it "
            "straight away. We respect the process."
        )
    if sms_count <= 4:
        return (
            f"After {sms_count} reminders, the deed is done. "
            "The filter exhales. The household is at peace."
        )
    if sms_count <= 6:
        return (
            f"It took {sms_count} increasingly concerned messages, but justice has prevailed. "
            "The filter's legal team has been stood down. "
            "The washing machine has called off the work-to-rule."
        )
    return (
        f"After {sms_count} days of escalating crisis — including industrial action, "
        "a press conference, and the filter writing its will — the task is complete. "
        "The filter has dropped all charges. History will remember this day."
    )


# ---------------------------------------------------------------------------
# Handler: confirm task via link click
# ---------------------------------------------------------------------------

def confirm_task(event, _context):
    """Handle confirmation link click — mark task done and send congratulations."""
    params = event.get("queryStringParameters") or {}
    week = params.get("week")
    token = params.get("token")
    is_test = params.get("test") == "1"

    if ORIGIN_VERIFY_ENABLED:
        presented = (event.get("headers") or {}).get("x-origin-verify", "")
        if not hmac.compare_digest(presented, ORIGIN_VERIFY_TOKEN):
            _log("Origin verify failed", level="WARNING")
            return _html_response(403, _error_page("Access denied."))

    if not week or not token:
        return _html_response(400, _error_page("Invalid confirmation link — missing parameters."))

    try:
        pk = _week_pk(date.fromisoformat(week), is_test)
    except ValueError:
        return _html_response(400, _error_page("Invalid confirmation link — malformed date."))
    response = table.get_item(Key={"PK": pk})

    if "Item" not in response:
        return _html_response(404, _error_page("Confirmation link not found or has expired."))

    item = response["Item"]

    if item["status"] == "CONFIRMED":
        return _html_response(200, _already_confirmed_page())

    if item["token"] != token:
        _log("Invalid token presented", pk=pk, level="WARNING")
        return _html_response(403, _error_page("Invalid confirmation token."))

    now = _now_london()

    email_sent_at_str = item.get("email_sent_at", "")
    if email_sent_at_str:
        sent_at = datetime.fromisoformat(email_sent_at_str)
        elapsed = (now - sent_at).total_seconds()
        if elapsed < 120:
            _log("Confirmation too fast", pk=pk, elapsed_seconds=int(elapsed), level="WARNING")
            return _html_response(200, _too_fast_page(int(elapsed)))

    sms_count = len(item.get("sms_dates", []))

    table.update_item(
        Key={"PK": pk},
        UpdateExpression="SET #s = :status, confirmed_at = :confirmed_at",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":status": "CONFIRMED",
            ":confirmed_at": now.isoformat(),
        },
    )

    _log("Task confirmed", pk=pk, reminders_sent=sms_count)
    _notify_congratulations(sms_count, ANIMAL_TYPE)

    return _html_response(200, _success_page())


def _send_congratulations_email(sms_count: int, animal: str):
    image_url = _fetch_animal_image(animal)
    ses.send_email(
        Source=FROM_EMAIL,
        Destination={"ToAddresses": [WIFE_EMAIL]},
        Message={
            "Subject": {"Data": "Filter cleaned! Here is your reward 🎉"},
            "Body": {
                "Html": {"Data": _congratulations_html(
                    _sms_commentary(sms_count),
                    _animal_caption(animal),
                    image_url,
                    animal,
                )},
                "Text": {"Data": (
                    f"Congratulations! {_sms_commentary(sms_count)} Your reward: {image_url}"
                )},
            },
        },
    )


def _html_response(status_code: int, body: str) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": body,
    }


def _congratulations_html(commentary: str, caption: str, image_url: str, animal: str) -> str:
    image_block = (
        f"""
        <div style="text-align:center;margin:24px 0 8px;">
          <img src="{image_url}" alt="A celebratory {animal}"
               style="max-width:100%;border-radius:10px;box-shadow:0 4px 16px rgba(0,0,0,0.2);">
        </div>
        <p style="text-align:center;color:#888;font-size:13px;font-style:italic;">{caption}</p>
        """
        if image_url
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:30px 0;">
    <tr><td align="center">
      <table width="100%" style="max-width:560px;background:#ffffff;border-radius:8px;overflow:hidden;box-sizing:border-box;">
        <tr><td>
          <div style="background:linear-gradient(135deg,#2e7d32,#43a047);padding:32px;text-align:center;">
            <div style="font-size:52px;">🎉</div>
            <h1 style="margin:12px 0 0;color:#ffffff;font-size:26px;letter-spacing:-0.5px;">
              Congratulations!
            </h1>
            <p style="margin:8px 0 0;color:#c8e6c9;font-size:15px;">
              The filter has been cleaned.
            </p>
          </div>
          <div style="padding:32px;">
            <p style="color:#333;line-height:1.7;font-size:15px;">{commentary}</p>
            <p style="color:#555;line-height:1.7;font-size:15px;">
              As a token of gratitude from the household — and from the filter itself,
              who has asked us to pass on its sincerest thanks — please accept this {animal}:
            </p>
            {image_block}
            <p style="color:#555;line-height:1.7;font-size:15px;">
              No further reminders will be sent this week.
            </p>
            <p style="color:#555;line-height:1.7;font-size:15px;">
              Until next Sunday.
            </p>
            <p style="color:#aaa;font-size:13px;margin-top:24px;border-top:1px solid #eee;padding-top:16px;">
              The Washing Machine Notification System™ — keeping filters clean since 2026.
            </p>
          </div>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _too_fast_page(elapsed_seconds: int) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nice try</title></head>
<body style="margin:0;padding:40px 20px;font-family:Arial,sans-serif;text-align:center;background:#f5f5f5;">
  <div style="max-width:400px;margin:0 auto;background:#fff;border-radius:8px;padding:40px;">
    <div style="font-size:48px;">🤨</div>
    <h2 style="color:#c62828;">Nice try.</h2>
    <p style="color:#555;">That was <strong>{elapsed_seconds} seconds</strong>.</p>
    <p style="color:#555;">The filter has not been cleaned in {elapsed_seconds} seconds.
    It takes longer than that to find the washing machine.</p>
    <p style="color:#555;">Go and do a proper job and come back when you've actually done it.
    The link will still be there.</p>
    <p style="color:#999;font-size:12px;margin-top:24px;">
      The system is watching. It has timestamps.
    </p>
  </div>
</body>
</html>"""


def _success_page() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Confirmed</title></head>
<body style="margin:0;padding:40px 20px;font-family:Arial,sans-serif;text-align:center;background:#f5f5f5;">
  <div style="max-width:400px;margin:0 auto;background:#fff;border-radius:8px;padding:40px;">
    <div style="font-size:48px;">✅</div>
    <h2 style="color:#2e7d32;">All done!</h2>
    <p style="color:#555;">Thank you for cleaning the filter. No further reminders this week.</p>
  </div>
</body>
</html>"""


def _already_confirmed_page() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Already confirmed</title></head>
<body style="margin:0;padding:40px 20px;font-family:Arial,sans-serif;text-align:center;background:#f5f5f5;">
  <div style="max-width:400px;margin:0 auto;background:#fff;border-radius:8px;padding:40px;">
    <div style="font-size:48px;">👍</div>
    <h2 style="color:#1565c0;">Already confirmed</h2>
    <p style="color:#555;">You've already confirmed cleaning the filter this week. Thanks!</p>
  </div>
</body>
</html>"""


def _error_page(message: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Error</title></head>
<body style="margin:0;padding:40px 20px;font-family:Arial,sans-serif;text-align:center;background:#f5f5f5;">
  <div style="max-width:400px;margin:0 auto;background:#fff;border-radius:8px;padding:40px;">
    <div style="font-size:48px;">❌</div>
    <h2 style="color:#c62828;">Something went wrong</h2>
    <p style="color:#555;">{message}</p>
  </div>
</body>
</html>"""

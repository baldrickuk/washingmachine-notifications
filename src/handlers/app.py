import os
import uuid
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

import boto3

LONDON_TZ = ZoneInfo("Europe/London")
TEST_SMS_INTERVAL_SECONDS = 600  # 10 minutes

TABLE_NAME = os.environ["TABLE_NAME"]
WIFE_EMAIL = os.environ["WIFE_EMAIL"]
WIFE_PHONE = os.environ["WIFE_PHONE"]
FROM_EMAIL = os.environ["FROM_EMAIL"]
API_BASE_URL = os.environ.get("API_BASE_URL", "")

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)
ses = boto3.client("ses")
sns = boto3.client("sns")


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

def send_weekly_email(event, context):
    is_test = bool(event.get("test"))
    now = _now_london()

    if not is_test and (now.weekday() != 6 or now.hour != 9):
        print(f"Not Sunday 09:xx UK time ({now.strftime('%A %H:%M')}), skipping")
        return

    sunday = now.date()
    pk = _week_pk(sunday, is_test)

    existing = table.get_item(Key={"PK": pk}).get("Item")
    if existing:
        if is_test:
            # Reset test state so each test run starts from SMS #1
            table.delete_item(Key={"PK": pk})
            print(f"Cleared previous test record {pk}")
        else:
            print(f"Email already sent for {pk}")
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
    _send_email(confirm_url, is_test)
    print(f"{'TEST ' if is_test else ''}Email sent for {pk}")


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
        'font-weight:bold;border-radius:6px 6px 0 0;">TEST MODE — SMS reminders every 10 minutes</div>'
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
# Escalating SMS messages (index = number of SMSes already sent this week)
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
# Handler: send daily SMS (08:00 UK time) while unconfirmed
# ---------------------------------------------------------------------------

def send_daily_sms(event, context):
    is_test = bool(event.get("test"))
    now = _now_london()

    if not is_test and now.hour != 8:
        print(f"Not 08:xx UK time ({now.hour}:xx), skipping")
        return

    sunday = now.date() if is_test else _this_weeks_sunday(now)
    pk = _week_pk(sunday, is_test)

    response = table.get_item(Key={"PK": pk})
    if "Item" not in response:
        print(f"No record for {pk}, nothing to remind about")
        return

    item = response["Item"]

    if item["status"] == "CONFIRMED":
        print(f"Already confirmed for {pk}")
        return

    if is_test:
        last_sms_at = item.get("last_sms_at")
        if last_sms_at:
            elapsed = (now - datetime.fromisoformat(last_sms_at)).total_seconds()
            if elapsed < TEST_SMS_INTERVAL_SECONDS:
                print(f"Test SMS sent {elapsed:.0f}s ago (<10 min), skipping")
                return
    else:
        today_str = now.date().isoformat()
        if today_str in item.get("sms_dates", []):
            print(f"SMS already sent today ({today_str}) for {pk}")
            return

    sms_count = len(item.get("sms_dates", []))
    message = _escalating_sms(sms_count, sunday)

    sns.publish(
        PhoneNumber=WIFE_PHONE,
        Message=message,
        MessageAttributes={
            "AWS.SNS.SMS.SMSType": {"DataType": "String", "StringValue": "Transactional"},
        },
    )

    dedup_value = now.isoformat() if is_test else now.date().isoformat()
    update_expr = "SET sms_dates = :dates"
    expr_values: dict = {":dates": list(item.get("sms_dates", [])) + [dedup_value]}
    if is_test:
        update_expr += ", last_sms_at = :last"
        expr_values[":last"] = now.isoformat()

    table.update_item(
        Key={"PK": pk},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_values,
    )
    print(f"{'TEST ' if is_test else ''}SMS #{sms_count + 1} sent for {pk}")


# ---------------------------------------------------------------------------
# Handler: confirm task via link click
# ---------------------------------------------------------------------------

def confirm_task(event, context):
    params = event.get("queryStringParameters") or {}
    week = params.get("week")
    token = params.get("token")
    is_test = params.get("test") == "1"

    if not week or not token:
        return _html_response(400, _error_page("Invalid confirmation link — missing parameters."))

    pk = _week_pk(date.fromisoformat(week), is_test)
    response = table.get_item(Key={"PK": pk})

    if "Item" not in response:
        return _html_response(404, _error_page("Confirmation link not found or has expired."))

    item = response["Item"]

    if item["status"] == "CONFIRMED":
        return _html_response(200, _already_confirmed_page())

    if item["token"] != token:
        return _html_response(403, _error_page("Invalid confirmation token."))

    now = _now_london()
    table.update_item(
        Key={"PK": pk},
        UpdateExpression="SET #s = :status, confirmed_at = :confirmed_at",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":status": "CONFIRMED",
            ":confirmed_at": now.isoformat(),
        },
    )

    return _html_response(200, _success_page())


def _html_response(status_code: int, body: str) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": body,
    }


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

"""Unit tests for Lambda handler logic."""
import sys
import os
import urllib.error
import urllib.parse
from datetime import date, datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "handlers"))
import app  # noqa: E402  (import after path setup)

LONDON_TZ = ZoneInfo("Europe/London")


# ---------------------------------------------------------------------------
# Pure function tests — no mocking needed
# ---------------------------------------------------------------------------

class TestWeekPk:
    def test_production_prefix(self):
        assert app._week_pk(date(2026, 5, 17)) == "WEEK#2026-05-17"

    def test_test_prefix(self):
        assert app._week_pk(date(2026, 5, 17), test=True) == "TEST#2026-05-17"


class TestThisWeeksSunday:
    def test_returns_same_day_on_sunday(self):
        sunday = datetime(2026, 5, 17, 9, 0, tzinfo=LONDON_TZ)
        assert app._this_weeks_sunday(sunday) == date(2026, 5, 17)

    def test_returns_previous_sunday_on_monday(self):
        monday = datetime(2026, 5, 18, 8, 0, tzinfo=LONDON_TZ)
        assert app._this_weeks_sunday(monday) == date(2026, 5, 17)

    def test_returns_previous_sunday_on_saturday(self):
        saturday = datetime(2026, 5, 23, 8, 0, tzinfo=LONDON_TZ)
        assert app._this_weeks_sunday(saturday) == date(2026, 5, 17)


class TestEscalatingSms:
    def test_first_message_includes_date(self):
        msg = app._escalating_sms(0, date(2026, 5, 17))
        assert "17 May" in msg
        assert "Morning!" in msg

    def test_second_message_no_date(self):
        msg = app._escalating_sms(1, date(2026, 5, 17))
        assert "Day 2" in msg
        assert "17 May" not in msg

    def test_escalates_through_all_stages(self):
        messages = [app._escalating_sms(i, date(2026, 5, 17)) for i in range(9)]
        assert len(set(messages)) == 9  # all distinct

    def test_caps_at_final_message(self):
        msg_8 = app._escalating_sms(8, date(2026, 5, 17))
        msg_99 = app._escalating_sms(99, date(2026, 5, 17))
        assert msg_8 == msg_99

    def test_final_message_is_stern(self):
        msg = app._escalating_sms(99, date(2026, 5, 17))
        assert "ANOTHER DAY" in msg


class TestSmsCommentary:
    def test_zero_reminders(self):
        assert "very first email" in app._sms_commentary(0)

    def test_one_reminder(self):
        assert "one gentle nudge" in app._sms_commentary(1)

    def test_two_reminders(self):
        assert "Two reminders" in app._sms_commentary(2)

    def test_three_to_four(self):
        assert "3 reminders" in app._sms_commentary(3)
        assert "4 reminders" in app._sms_commentary(4)

    def test_five_to_six(self):
        assert "5 increasingly" in app._sms_commentary(5)

    def test_seven_plus(self):
        assert "days of escalating crisis" in app._sms_commentary(7)

    def test_returns_string_for_all_counts(self):
        for i in range(20):
            result = app._sms_commentary(i)
            assert isinstance(result, str)
            assert len(result) > 0


class TestAnimalCaption:
    def test_known_animals(self):
        assert "bunny" in app._animal_caption("bunny").lower()
        assert "cat" in app._animal_caption("cat").lower()
        assert "dog" in app._animal_caption("dog").lower()
        assert "fox" in app._animal_caption("fox").lower()

    def test_unknown_animal_fallback(self):
        assert "salamander" in app._animal_caption("salamander")


class TestLog:
    def test_outputs_valid_json(self, capsys):
        import json
        app._log("test message", key="value")
        out = capsys.readouterr().out.strip()
        parsed = json.loads(out)
        assert parsed["message"] == "test message"
        assert parsed["key"] == "value"
        assert parsed["level"] == "INFO"

    def test_custom_level(self, capsys):
        import json
        app._log("warning message", level="WARNING")
        out = capsys.readouterr().out.strip()
        assert json.loads(out)["level"] == "WARNING"


class TestSendPushover:
    def test_happy_path_posts_correct_body(self):
        with patch.object(app, "PUSHOVER_ENABLED", True), \
             patch.object(app, "PUSHOVER_APP_TOKEN", "app-token"), \
             patch.object(app, "PUSHOVER_USER_KEY", "user-key"), \
             patch("urllib.request.urlopen", return_value=MagicMock()) as mock_urlopen:
            app._send_pushover("Hello", "Title", url="https://example.com", url_title="Click", priority=0)
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        body = urllib.parse.parse_qs(req.data.decode())
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
        body = urllib.parse.parse_qs(req.data.decode())
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
        body = urllib.parse.parse_qs(req.data.decode())
        assert "retry" not in body
        assert "expire" not in body

    def test_url_error_caught_no_raise(self, capsys):
        import json as _json
        with patch.object(app, "PUSHOVER_ENABLED", True), \
             patch.object(app, "PUSHOVER_APP_TOKEN", "app-token"), \
             patch.object(app, "PUSHOVER_USER_KEY", "user-key"), \
             patch("urllib.request.urlopen", side_effect=urllib.error.URLError("network error")):
            app._send_pushover("Hello", "Title")  # must not raise
        out = capsys.readouterr().out.strip()
        assert _json.loads(out)["level"] == "WARNING"

    def test_url_omitted_when_not_provided(self):
        with patch.object(app, "PUSHOVER_ENABLED", True), \
             patch.object(app, "PUSHOVER_APP_TOKEN", "app-token"), \
             patch.object(app, "PUSHOVER_USER_KEY", "user-key"), \
             patch("urllib.request.urlopen", return_value=MagicMock()) as mock_urlopen:
            app._send_pushover("Hello", "Title")
        req = mock_urlopen.call_args[0][0]
        body = urllib.parse.parse_qs(req.data.decode())
        assert "url" not in body
        assert "url_title" not in body


class TestNotifyDispatchersPushover:
    def test_notify_initial_calls_pushover_when_enabled(self):
        with patch.object(app, "PUSHOVER_ENABLED", True), \
             patch.object(app, "_send_pushover") as mock_push:
            app._notify_initial("https://example.com/confirm?week=2026-05-17&token=abc", False)
        mock_push.assert_called_once()
        kwargs = mock_push.call_args.kwargs
        assert "https://example.com/confirm?week=2026-05-17&token=abc" in kwargs["message"]
        assert "url" not in kwargs

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
        assert mock_push.call_args.kwargs.get("priority", 0) == 0

    def test_notify_congratulations_calls_email_when_disabled(self):
        with patch.object(app, "PUSHOVER_ENABLED", False), \
             patch.object(app, "_send_congratulations_email") as mock_email:
            app._notify_congratulations(0, "bunny")
        mock_email.assert_called_once_with(0, "bunny")


# ---------------------------------------------------------------------------
# Handler tests — mock AWS interactions
# ---------------------------------------------------------------------------

class TestSendWeeklyEmail:
    def _make_event(self, test=False):
        return {"test": test} if test else {}

    def test_skips_on_wrong_weekday(self):
        # Simulate a Tuesday
        tuesday = datetime(2026, 5, 19, 9, 0, tzinfo=LONDON_TZ)
        with patch.object(app, "_now_london", return_value=tuesday):
            app.send_weekly_email(self._make_event(), None)
        # No DynamoDB interaction expected
        app.table.get_item.assert_not_called()

    def test_skips_on_wrong_hour(self):
        # Sunday but wrong hour
        sunday_8am = datetime(2026, 5, 17, 8, 0, tzinfo=LONDON_TZ)
        with patch.object(app, "_now_london", return_value=sunday_8am):
            app.send_weekly_email(self._make_event(), None)
        app.table.get_item.assert_not_called()

    def test_skips_if_record_exists(self):
        sunday = datetime(2026, 5, 17, 9, 0, tzinfo=LONDON_TZ)
        app.table.get_item.return_value = {"Item": {"PK": "WEEK#2026-05-17"}}
        with patch.object(app, "_now_london", return_value=sunday), \
             patch.object(app, "_notify_initial") as mock_notify:
            app.send_weekly_email(self._make_event(), None)
        mock_notify.assert_not_called()

    def test_sends_notification_when_no_record(self):
        sunday = datetime(2026, 5, 17, 9, 0, tzinfo=LONDON_TZ)
        app.table.get_item.return_value = {}
        with patch.object(app, "_now_london", return_value=sunday), \
             patch.object(app, "_notify_initial") as mock_notify:
            app.send_weekly_email(self._make_event(), None)
        mock_notify.assert_called_once()

    def test_test_mode_bypasses_weekday_check(self):
        tuesday = datetime(2026, 5, 19, 14, 0, tzinfo=LONDON_TZ)
        app.table.get_item.return_value = {}
        with patch.object(app, "_now_london", return_value=tuesday), \
             patch.object(app, "_notify_initial") as mock_notify:
            app.send_weekly_email(self._make_event(test=True), None)
        mock_notify.assert_called_once()


class TestSendDailySms:
    def setup_method(self):
        app.table.reset_mock()

    def test_skips_on_wrong_hour(self):
        wrong_hour = datetime(2026, 5, 18, 10, 0, tzinfo=LONDON_TZ)
        with patch.object(app, "_now_london", return_value=wrong_hour):
            app.send_daily_sms({}, None)
        app.table.get_item.assert_not_called()

    def test_skips_if_no_record(self):
        monday_8am = datetime(2026, 5, 18, 8, 0, tzinfo=LONDON_TZ)
        app.table.get_item.return_value = {}
        with patch.object(app, "_now_london", return_value=monday_8am), \
             patch.object(app, "_notify_reminder") as mock_notify:
            app.send_daily_sms({}, None)
        mock_notify.assert_not_called()

    def test_skips_if_already_confirmed(self):
        monday_8am = datetime(2026, 5, 18, 8, 0, tzinfo=LONDON_TZ)
        app.table.get_item.return_value = {"Item": {
            "status": "CONFIRMED", "sms_dates": []
        }}
        with patch.object(app, "_now_london", return_value=monday_8am), \
             patch.object(app, "_notify_reminder") as mock_notify:
            app.send_daily_sms({}, None)
        mock_notify.assert_not_called()

    def test_skips_if_already_sent_today(self):
        monday_8am = datetime(2026, 5, 18, 8, 0, tzinfo=LONDON_TZ)
        app.table.get_item.return_value = {"Item": {
            "status": "PENDING", "sms_dates": ["2026-05-18"]
        }}
        with patch.object(app, "_now_london", return_value=monday_8am), \
             patch.object(app, "_notify_reminder") as mock_notify:
            app.send_daily_sms({}, None)
        mock_notify.assert_not_called()

    def test_sends_reminder_when_pending(self):
        monday_8am = datetime(2026, 5, 18, 8, 0, tzinfo=LONDON_TZ)
        app.table.get_item.return_value = {"Item": {
            "status": "PENDING", "sms_dates": []
        }}
        with patch.object(app, "_now_london", return_value=monday_8am), \
             patch.object(app, "_notify_reminder") as mock_notify:
            app.send_daily_sms({}, None)
        mock_notify.assert_called_once()


class TestConfirmTask:
    def _event(self, week="2026-05-17", token="test-token", test="0"):
        return {"queryStringParameters": {"week": week, "token": token, "test": test}}

    def test_missing_params_returns_400(self):
        result = app.confirm_task({"queryStringParameters": {}}, None)
        assert result["statusCode"] == 400

    def test_missing_query_string_returns_400(self):
        result = app.confirm_task({}, None)
        assert result["statusCode"] == 400

    def test_malformed_week_returns_400(self):
        result = app.confirm_task(
            {"queryStringParameters": {"week": "not-a-date", "token": "test-token"}}, None
        )
        assert result["statusCode"] == 400

    def test_out_of_range_week_returns_400(self):
        result = app.confirm_task(
            {"queryStringParameters": {"week": "2026-13-99", "token": "test-token"}}, None
        )
        assert result["statusCode"] == 400

    def test_unknown_record_returns_404(self):
        app.table.get_item.return_value = {}
        result = app.confirm_task(self._event(), None)
        assert result["statusCode"] == 404

    def test_already_confirmed_returns_200(self):
        app.table.get_item.return_value = {"Item": {
            "status": "CONFIRMED", "token": "test-token", "sms_dates": []
        }}
        result = app.confirm_task(self._event(), None)
        assert result["statusCode"] == 200
        assert "Already confirmed" in result["body"]

    def test_invalid_token_returns_403(self):
        app.table.get_item.return_value = {"Item": {
            "status": "PENDING", "token": "correct-token", "sms_dates": []
        }}
        result = app.confirm_task(self._event(token="wrong-token"), None)
        assert result["statusCode"] == 403

    def test_valid_confirmation_returns_200(self):
        app.table.get_item.return_value = {"Item": {
            "status": "PENDING", "token": "test-token", "sms_dates": []
        }}
        with patch.object(app, "_notify_congratulations"):
            result = app.confirm_task(self._event(), None)
        assert result["statusCode"] == 200
        assert "All done" in result["body"]

    def test_valid_confirmation_updates_dynamodb(self):
        app.table.get_item.return_value = {"Item": {
            "status": "PENDING", "token": "test-token", "sms_dates": []
        }}
        app.table.update_item.reset_mock()
        with patch.object(app, "_notify_congratulations"):
            app.confirm_task(self._event(), None)
        app.table.update_item.assert_called_once()
        call_kwargs = app.table.update_item.call_args[1]
        assert call_kwargs["ExpressionAttributeValues"][":status"] == "CONFIRMED"

    def test_too_fast_confirmation_returns_cheeky_page(self):
        sent_at = datetime(2026, 5, 17, 9, 0, 0, tzinfo=LONDON_TZ)
        confirmed_at = datetime(2026, 5, 17, 9, 1, 30, tzinfo=LONDON_TZ)  # 90s later
        app.table.get_item.return_value = {"Item": {
            "status": "PENDING", "token": "test-token", "sms_dates": [],
            "email_sent_at": sent_at.isoformat(),
        }}
        with patch.object(app, "_now_london", return_value=confirmed_at):
            result = app.confirm_task(self._event(), None)
        assert result["statusCode"] == 200
        assert "All done" not in result["body"]
        assert "Already confirmed" not in result["body"]

    def test_too_fast_confirmation_does_not_mark_confirmed(self):
        sent_at = datetime(2026, 5, 17, 9, 0, 0, tzinfo=LONDON_TZ)
        confirmed_at = datetime(2026, 5, 17, 9, 1, 30, tzinfo=LONDON_TZ)  # 90s later
        app.table.get_item.return_value = {"Item": {
            "status": "PENDING", "token": "test-token", "sms_dates": [],
            "email_sent_at": sent_at.isoformat(),
        }}
        app.table.update_item.reset_mock()
        with patch.object(app, "_now_london", return_value=confirmed_at):
            app.confirm_task(self._event(), None)
        app.table.update_item.assert_not_called()

    def test_exactly_120s_confirmation_proceeds_normally(self):
        sent_at = datetime(2026, 5, 17, 9, 0, 0, tzinfo=LONDON_TZ)
        confirmed_at = datetime(2026, 5, 17, 9, 2, 0, tzinfo=LONDON_TZ)  # exactly 120s
        app.table.get_item.return_value = {"Item": {
            "status": "PENDING", "token": "test-token", "sms_dates": [],
            "email_sent_at": sent_at.isoformat(),
        }}
        with patch.object(app, "_now_london", return_value=confirmed_at), \
             patch.object(app, "_notify_congratulations"):
            result = app.confirm_task(self._event(), None)
        assert result["statusCode"] == 200
        assert "All done" in result["body"]

    def test_test_mode_also_enforces_too_fast_check(self):
        sent_at = datetime(2026, 5, 17, 9, 0, 0, tzinfo=LONDON_TZ)
        confirmed_at = datetime(2026, 5, 17, 9, 0, 5, tzinfo=LONDON_TZ)  # 5s later
        app.table.get_item.return_value = {"Item": {
            "status": "PENDING", "token": "test-token", "sms_dates": [],
            "email_sent_at": sent_at.isoformat(),
        }}
        with patch.object(app, "_now_london", return_value=confirmed_at):
            result = app.confirm_task(self._event(test="1"), None)
        assert result["statusCode"] == 200
        assert "All done" not in result["body"]

    def test_missing_email_sent_at_skips_timing_check(self):
        app.table.get_item.return_value = {"Item": {
            "status": "PENDING", "token": "test-token", "sms_dates": [],
        }}
        with patch.object(app, "_notify_congratulations"):
            result = app.confirm_task(self._event(), None)
        assert result["statusCode"] == 200
        assert "All done" in result["body"]


class TestOriginVerify:
    def _event(self, week="2026-05-17", token="test-token", test="0", headers=None):
        return {
            "queryStringParameters": {"week": week, "token": token, "test": test},
            "headers": headers or {},
        }

    def setup_method(self):
        app.table.reset_mock()
        app.table.get_item.return_value = {"Item": {
            "status": "PENDING", "token": "test-token", "sms_dates": [],
        }}

    def test_missing_header_returns_403_when_enabled(self):
        with patch.object(app, "ORIGIN_VERIFY_ENABLED", True), \
             patch.object(app, "ORIGIN_VERIFY_TOKEN", "correct-secret"):
            result = app.confirm_task(self._event(), None)
        assert result["statusCode"] == 403

    def test_wrong_header_returns_403(self):
        with patch.object(app, "ORIGIN_VERIFY_ENABLED", True), \
             patch.object(app, "ORIGIN_VERIFY_TOKEN", "correct-secret"):
            result = app.confirm_task(
                self._event(headers={"x-origin-verify": "wrong-secret"}), None
            )
        assert result["statusCode"] == 403

    def test_correct_header_proceeds(self):
        with patch.object(app, "ORIGIN_VERIFY_ENABLED", True), \
             patch.object(app, "ORIGIN_VERIFY_TOKEN", "correct-secret"), \
             patch.object(app, "_notify_congratulations"):
            result = app.confirm_task(
                self._event(headers={"x-origin-verify": "correct-secret"}), None
            )
        assert result["statusCode"] == 200

    def test_disabled_skips_check(self):
        with patch.object(app, "ORIGIN_VERIFY_ENABLED", False), \
             patch.object(app, "_notify_congratulations"):
            result = app.confirm_task(self._event(), None)
        assert result["statusCode"] == 200

    def test_test_mode_without_header_still_returns_403(self):
        with patch.object(app, "ORIGIN_VERIFY_ENABLED", True), \
             patch.object(app, "ORIGIN_VERIFY_TOKEN", "correct-secret"):
            result = app.confirm_task(self._event(test="1"), None)
        assert result["statusCode"] == 403

    def test_test_mode_with_correct_header_proceeds(self):
        with patch.object(app, "ORIGIN_VERIFY_ENABLED", True), \
             patch.object(app, "ORIGIN_VERIFY_TOKEN", "correct-secret"), \
             patch.object(app, "_notify_congratulations"):
            result = app.confirm_task(
                self._event(test="1", headers={"x-origin-verify": "correct-secret"}), None
            )
        assert result["statusCode"] == 200


class TestVerifyDelivery:
    def setup_method(self):
        app.table.reset_mock()
        app.sns.reset_mock()

    def test_skips_on_wrong_weekday(self):
        sunday = datetime(2026, 5, 17, 9, 1, tzinfo=LONDON_TZ)
        with patch.object(app, "_now_london", return_value=sunday):
            app.verify_delivery({}, None)
        app.table.get_item.assert_not_called()

    def test_no_alert_when_record_exists(self):
        monday = datetime(2026, 5, 18, 9, 1, tzinfo=LONDON_TZ)
        app.table.get_item.return_value = {"Item": {
            "email_sent_at": "2026-05-17T09:00:00"
        }}
        app.sns.publish.reset_mock()
        with patch.object(app, "_now_london", return_value=monday):
            app.verify_delivery({}, None)
        app.sns.publish.assert_not_called()

    def test_publishes_alert_when_record_missing(self):
        monday = datetime(2026, 5, 18, 9, 1, tzinfo=LONDON_TZ)
        app.table.get_item.return_value = {}
        app.sns.publish.reset_mock()
        with patch.object(app, "_now_london", return_value=monday), \
             patch.object(app, "ALERT_TOPIC_ARN", "arn:aws:sns:eu-west-2:123:test"):
            app.verify_delivery({}, None)
        app.sns.publish.assert_called_once()

    def test_test_mode_bypasses_weekday_check(self):
        tuesday = datetime(2026, 5, 19, 14, 0, tzinfo=LONDON_TZ)
        app.table.get_item.return_value = {"Item": {"email_sent_at": "2026-05-17T09:00:00"}}
        with patch.object(app, "_now_london", return_value=tuesday):
            app.verify_delivery({"test": True}, None)
        app.table.get_item.assert_called_once()

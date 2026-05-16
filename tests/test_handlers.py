"""Unit tests for Lambda handler logic."""
import sys
import os
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

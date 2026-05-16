"""Pytest configuration — stubs environment and AWS SDK before app import."""
import os
import sys
from unittest.mock import MagicMock

# Environment must be set before the app module is imported
os.environ.setdefault("TABLE_NAME", "test-reminders")
os.environ.setdefault("FROM_EMAIL", "test@example.com")
os.environ.setdefault("ANIMAL_TYPE", "bunny")
os.environ.setdefault("TWILIO_ENABLED", "false")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "unused")
os.environ.setdefault("TWILIO_FROM_NUMBER", "unused")
os.environ.setdefault("WHATSAPP_PHONE_NUMBER_ID", "")
os.environ.setdefault("WHATSAPP_REMINDER_TEMPLATE", "filter_reminder")
os.environ.setdefault("WHATSAPP_ESCALATION_TEMPLATE", "filter_escalation")
os.environ.setdefault("WHATSAPP_CONGRATS_TEMPLATE", "filter_confirmed")
os.environ.setdefault("API_BASE_URL", "https://test.example.com")
os.environ.setdefault("SECRETS_ARN", "")
os.environ.setdefault("ALERT_TOPIC_ARN", "")

# Stub the AWS SDK so module-level boto3 calls don't hit real AWS
_boto3_stub = MagicMock()
_boto3_stub.resource.return_value.Table.return_value = MagicMock()
_boto3_stub.client.return_value = MagicMock()

_botocore_stub = MagicMock()

class _ClientError(Exception):
    """Stub for botocore.exceptions.ClientError."""

_botocore_stub.exceptions.ClientError = _ClientError

sys.modules.setdefault("boto3", _boto3_stub)
sys.modules.setdefault("botocore", _botocore_stub)
sys.modules.setdefault("botocore.exceptions", _botocore_stub.exceptions)

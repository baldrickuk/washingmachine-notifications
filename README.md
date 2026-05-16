# 🧺 washingmachine-notifications

> *"I could have just asked."*
> *— Me, after spending a weekend building a serverless AWS reminder system*

A production-grade, enterprise-ready, cloud-native, infinitely-scalable solution to the age-old problem of getting someone to clean the washing machine filter.

Yes. This is real. No, I'm not sorry.

---

## The Problem

The washing machine filter needs cleaning once a week. This is a known fact. It has been a known fact for some time. Gentle reminders were issued. Sticky notes were deployed. Hope was maintained.

Hope was not enough.

---

## The Solution

Rather than have a single, normal conversation like a well-adjusted adult, I built a serverless AWS notification pipeline with:

- **Automated weekly emails** with a confirmation link and an SMS nudge to actually open it
- **Daily escalating reminders** that grow progressively more unhinged if ignored
- **A congratulations email** featuring a random animal photo upon confirmation
- **A DynamoDB table** to track the emotional journey
- **CloudFront with GB-only geo restriction**, because the filter is not going to clean itself from abroad
- **AWS Secrets Manager**, because enterprise security practices apply even to laundry

The filter is cleaned. The marriage survives. The cloud bill is negligible.

---

## How It Works

Every Sunday at 09:00 UK time, the recipient gets an email asking them to clean the filter and click a confirmation link. An SMS nudge fires simultaneously to make sure the email doesn't languish unread.

If they confirm — lovely. Everyone goes about their day. A congratulations email arrives with a picture of a bunny.

If they do not confirm, the system begins its *escalation protocol*:

| Day | Vibe |
|-----|------|
| 1 | A gentle nudge |
| 2 | Slightly more pointed |
| 3 | The filter has feelings now |
| 4 | The filter is keeping a journal |
| 5 | Legal counsel has been engaged |
| 6 | The washing machine joins an industrial dispute |
| 7 | The filter has gone to the press |
| 8 | The filter is at peace. We are not. |
| 9+ | **ANOTHER DAY. STILL UNCLEAN.** *(repeats until heat death of the universe or confirmation, whichever comes first)* |

---

## Architecture

For those who would like to understand the full technical horror of what has been built, please consult [`docs/architecture.md`](docs/architecture.md) and [`docs/threat-model.md`](docs/threat-model.md), which between them contain more Mermaid diagrams than any washing machine reminder system has any right to.

The short version:

```
EventBridge → Lambda → DynamoDB → SES → Recipient's inbox
                               → Twilio (optional SMS)
                               → Meta Cloud API (optional WhatsApp)
           Secrets Manager → Lambda (credentials, fetched at cold start)
Recipient clicks link → CloudFront (GB-only) → API Gateway → Lambda → DynamoDB
                                                                     → SES (congratulations + bunny)
```

---

## Setup

### Prerequisites

- An AWS account
- The AWS CLI and SAM CLI installed
- A verified SES sender email address (see [AWS docs](https://docs.aws.amazon.com/ses/latest/dg/creating-identities.html))
- The wisdom to know you've gone too far, and the courage to deploy anyway

### Deploy

```bash
# Clone the repo
git clone https://github.com/baldrickuk/washingmachine-notifications.git
cd washingmachine-notifications

# Configure your details
cp samconfig.toml.example samconfig.toml
# Edit samconfig.toml and fill in:
#   WifeEmail    — the recipient's email address
#   WifePhone    — mobile number in E.164 format (+447...)
#   FromEmail    — your verified SES sender address

sam build && sam deploy
```

That's it. The system will now operate autonomously every Sunday until the filter is clean, the account is deleted, or civilisation collapses.

### One-time AWS setup

1. **Verify your sender email** in SES → Verified identities
2. **Request SES production access** so you can send to any address without pre-verification (`aws sesv2 put-account-details` or via the AWS Console)
3. **Verify the recipient's email** in SES if still in sandbox mode

### Optional: SMS reminders

Set `TwilioEnabled=true` in `samconfig.toml` and provide `TwilioAccountSid`, `TwilioAuthToken`, and `TwilioFromNumber`. Credentials are stored in AWS Secrets Manager automatically on deploy — never in Lambda environment variables.

### Optional: WhatsApp (replaces email and SMS)

Set `WhatsAppPhoneNumberId` and `WhatsAppAccessToken`. Requires a Meta WhatsApp Business account and three pre-approved message templates (`filter_reminder`, `filter_escalation`, `filter_confirmed`). See `docs/architecture.md` for details.

---

## Testing

A test mode is included so you can verify the system works without waiting until Sunday, or until you've ignored something for nine days.

```bash
# Get the deployed function name
FUNC=$(aws lambda list-functions --profile dev --region eu-west-2 \
  --query 'Functions[?contains(FunctionName,`SendWeeklyEmail`)].FunctionName' \
  --output text)

# Fire the test email immediately
echo '{"test": true}' > /tmp/payload.json
aws lambda invoke \
  --function-name $FUNC \
  --payload file:///tmp/payload.json \
  --profile dev --region eu-west-2 \
  --cli-binary-format raw-in-base64-out /dev/stdout

# Then enable the TestSMSEvery10Min EventBridge rule in the AWS Console
# to receive escalating reminders every 10 minutes instead of daily.
# Disable it again when done, unless you enjoy consequences.
```

Test records use a `TEST#` DynamoDB key prefix and never interfere with the live weekly cycle.

---

## Cost

Running this in `eu-west-2` costs approximately **nothing**. The breakdown for the genuinely curious:

| Service | Usage | Cost |
|---------|-------|------|
| Lambda | ~10 invocations/week | Free tier |
| DynamoDB | 1 record/week, on-demand | Free tier |
| SES | ~5 emails/week | Free tier (62,000/month included) |
| CloudFront | ~5 requests/week | Free tier (10M/month included) |
| Secrets Manager | 1 secret | ~$0.40/month |
| EventBridge | 5 rules | Free |

Total: **~40p/month**, entirely dominated by Secrets Manager.

The cost of *not* building this — in terms of filter-related appliance damage — is left as an exercise for the reader.

---

## Contributing

If you have found yourself in a similar domestic situation and would like to contribute improvements — perhaps support for multiple chores, a points system, or a leaderboard — pull requests are welcome.

If you have found yourself here because you *received* one of these messages: hello. The link is in the email. You know what to do.

---

## Licence

MIT. Use it freely. Build it for someone you love, or at least someone who lives with you.

> *The filter was cleaned. This readme was the hardest part.*

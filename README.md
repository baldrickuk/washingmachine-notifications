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

- **Automated weekly emails** with a confirmation link
- **Daily SMS reminders** that grow progressively more unhinged if ignored
- **A DynamoDB table** to track the emotional journey
- **API Gateway** so that clicking a button in an email triggers a Lambda function, updates a database record, and stops the suffering

The filter is cleaned. The marriage survives. The cloud bill is negligible.

---

## How It Works

Every Sunday at 09:00, your chosen recipient gets a polite email asking them to clean the filter and click a confirmation link.

If they confirm — lovely. Everyone goes about their day.

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

For those who would like to understand the full technical horror of what has been built, please see [`docs/architecture.md`](docs/architecture.md), which contains no fewer than eight Mermaid diagrams, a state machine, and an entity-relationship diagram for a table with one row per week.

The short version:

```
EventBridge → Lambda → DynamoDB → SES → Wife's inbox
                                → SNS → Wife's phone (increasingly)
                    API Gateway → Lambda → DynamoDB (when she finally clicks the link)
```

---

## Setup

### Prerequisites

- An AWS account
- The AWS CLI and SAM CLI installed
- A verified SES email address (see [AWS docs](https://docs.aws.amazon.com/ses/latest/dg/creating-identities.html))
- A phone number to receive SMS messages
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

# Build and deploy
sam build && sam deploy
```

That's it. The system will now operate autonomously every Sunday until the filter is clean, the account is deleted, or civilisation collapses.

### One-time AWS setup

Before your first deploy, you'll need to:

1. **Verify your sender email** in SES → Verified identities
2. **Request SES production access** if you want to send to unverified addresses (i.e. your wife's actual inbox rather than a sandboxed test address)
3. **Check your SNS SMS spend limit** — the default is $1/month, which is plenty for one household but worth confirming

---

## Testing

A test mode is included so you can verify the system works without waiting until Sunday, or until you've ignored something for nine days.

```bash
# Fire the test email immediately
aws lambda invoke \
  --function-name washingmachine-notifications-SendWeeklyEmailFunction \
  --payload '{"test": true}' \
  --profile dev /dev/stdout

# Then enable the TestSMSEvery10Min EventBridge rule in the AWS Console
# to receive escalating SMS messages every 10 minutes instead of daily.
# Disable it again when done, unless you enjoy consequences.
```

Test records use a `TEST#` DynamoDB key prefix and never interfere with the live weekly cycle.

---

## Cost

Running this 24/7 in `eu-west-2` costs approximately **nothing**. A few pence per month at most — the DynamoDB table uses on-demand billing, the Lambdas run for milliseconds a day, and SES/SNS charges fractions of a penny per message.

The cost of *not* building this — in terms of filter-related appliance damage — is left as an exercise for the reader.

---

## Contributing

If you have found yourself in a similar domestic situation and would like to contribute improvements — perhaps support for multiple chores, a points system, or a leaderboard — pull requests are welcome.

If you have found yourself here because you *received* one of these messages: hello. The link is in the email. You know what to do.

---

## Licence

MIT. Use it freely. Build it for someone you love, or at least someone who lives with you.

> *The filter was cleaned. This readme was the hardest part.*

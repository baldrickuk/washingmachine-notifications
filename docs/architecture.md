# Architecture — Washing Machine Filter Reminder

A fully serverless AWS solution that reminds a household member to clean the washing machine filter every week, escalating through increasingly dramatic messages until the task is confirmed.

---

## System Overview

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#1e3a5f', 'primaryTextColor': '#c9d1d9', 'primaryBorderColor': '#4a7ab5', 'lineColor': '#58a6ff', 'secondaryColor': '#0d2137', 'tertiaryColor': '#162032', 'edgeLabelBackground': '#0d1117', 'clusterBkg': '#0d2137', 'clusterBorder': '#30363d', 'titleColor': '#c9d1d9', 'fontFamily': 'ui-monospace, monospace'}}}%%

graph LR
    subgraph sched ["  EventBridge Schedules  "]
        EB1("Sunday 09:00 UK\n─────────────\nBST: cron 0 8 SUN\nGMT: cron 0 9 SUN")
        EB2("Daily 08:00 UK\n─────────────\nBST: cron 0 7 *\nGMT: cron 0 8 *")
        EB3("Every 10 min\n─────────────\nTest only\ndisabled by default")
    end

    subgraph lambda ["  Lambda Functions  "]
        L1["SendWeeklyEmail"]
        L2["SendDailySMS"]
        L3["ConfirmTask"]
    end

    subgraph store ["  Storage  "]
        DB[("DynamoDB\n─────────────\nPK: WEEK#YYYY-MM-DD\nstatus · token\nsms_dates · ttl")]
        SM[("Secrets Manager\n─────────────\ntwilio_auth_token\nwhatsapp_access_token")]
    end

    subgraph api ["  API Gateway  "]
        GW["HTTP API\nGET /confirm\n─────────────\n5 req/s · burst 10"]
    end

    subgraph channel ["  Notification Channel  "]
        SES["SES\nEmail\n(always)"]
        TW["Twilio\nSMS\n(optional)"]
        WA["Meta Cloud API\nWhatsApp\n(optional)"]
    end

    subgraph human ["  Recipient  "]
        EM["📧 Email"]
        PH["📱 Phone"]
    end

    EB1 -->|fires| L1
    EB2 -->|fires| L2
    EB3 -.->|fires test| L2

    L1 & L2 & L3 -->|read at cold start| SM
    L1 -->|create record| DB
    L1 -->|send| SES
    L2 -->|check & update| DB
    L2 -->|send reminder| TW
    L2 -->|send reminder| WA
    L3 -->|mark confirmed| DB
    L3 -->|send congratulations| SES

    SES --> EM
    TW --> PH
    WA --> PH
    EM -->|"clicks link"| GW
    GW -->|"invoke\n(throttled)"| L3

    classDef schedule fill:#1a3a5c,stroke:#4a7ab5,color:#a0c4e8,rx:6
    classDef fn fill:#1e3a1e,stroke:#3a7a3a,color:#90d090
    classDef storage fill:#3a2a1e,stroke:#8a5a2a,color:#d0a070
    classDef secret fill:#2a1e3a,stroke:#6a4a8a,color:#c090d0
    classDef messaging fill:#2a1a3a,stroke:#6a3a8a,color:#b070d0
    classDef gateway fill:#1a2a3a,stroke:#3a5a7a,color:#70a0c0
    classDef person fill:#2a2a2a,stroke:#5a5a5a,color:#c0c0c0

    class EB1,EB2,EB3 schedule
    class L1,L2,L3 fn
    class DB storage
    class SM secret
    class SES,TW,WA messaging
    class GW gateway
    class EM,PH person
```

---

## AWS Components

| Component | Resource | Purpose |
|---|---|---|
| **EventBridge** | 5 scheduled rules (4 prod + 1 test) | Triggers reminder Lambdas on schedule |
| **Lambda** × 3 | `SendWeeklyEmail`, `SendDailySMS`, `ConfirmTask` | All business logic |
| **DynamoDB** | Single table, PAY_PER_REQUEST | Tracks weekly task state (30-day TTL) |
| **Secrets Manager** | `washingmachine-notifications/secrets` | Stores Twilio and WhatsApp credentials |
| **SES** | Email via verified identity | Sends reminder and congratulations emails |
| **API Gateway** | HTTP API, `GET /confirm`, throttled 5 req/s | Serves the confirmation link |
| **IAM** | Single shared role | Least-privilege access to DDB, SES, Secrets Manager |

---

## Notification Channels

The system supports three delivery channels, selected by configuration. Email is always available; SMS and WhatsApp are opt-in.

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#1e3a5f', 'primaryTextColor': '#c9d1d9', 'primaryBorderColor': '#4a7ab5', 'lineColor': '#58a6ff', 'edgeLabelBackground': '#0d1117'}}}%%

flowchart LR
    DISPATCH["_notify_initial()\n_notify_reminder()\n_notify_congratulations()"]

    DISPATCH -->|"WHATSAPP_PHONE_NUMBER_ID set"| WA["WhatsApp\nvia Meta Cloud API\n(replaces email + SMS)"]
    DISPATCH -->|"default"| EMAIL["SES Email\n+ optional SMS nudge"]

    EMAIL -->|"TWILIO_ENABLED=true"| TSMS["Twilio SMS"]
    EMAIL -->|"TWILIO_ENABLED=false"| NOSMS["SMS skipped"]

    style WA fill:#1a2a3a,stroke:#3a6a9a,color:#80b0d0
    style EMAIL fill:#1a3a1a,stroke:#3a7a3a,color:#80d080
    style TSMS fill:#2a1a3a,stroke:#6a3a8a,color:#b070d0
    style NOSMS fill:#2a2a2a,stroke:#555,color:#888
```

| `WHATSAPP_*` set | `TWILIO_ENABLED` | Channel used |
|:---:|:---:|---|
| No | false | Email only (default) |
| No | true | Email + Twilio SMS |
| Yes | — | WhatsApp only (no email) |

---

## Weekly Reminder Flow

Fires every Sunday at 09:00 UK time. Two EventBridge rules cover GMT and BST — the Lambda checks the actual London hour and exits early if wrong. Credentials are fetched from Secrets Manager on cold start.

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#1e3a5f', 'primaryTextColor': '#c9d1d9', 'primaryBorderColor': '#4a7ab5', 'lineColor': '#58a6ff', 'edgeLabelBackground': '#0d1117'}}}%%

sequenceDiagram
    actor EB as EventBridge
    participant L  as SendWeeklyEmail λ
    participant SM as Secrets Manager
    participant DB as DynamoDB
    participant CH as Channel (SES / WhatsApp)
    actor W  as Recipient

    EB->>L: Sunday 08:00 or 09:00 UTC
    activate L

    Note over L,SM: Cold start only
    L->>SM: GetSecretValue
    SM-->>L: {twilio_auth_token, whatsapp_access_token}

    L->>L: Check actual London time == 09:xx
    Note over L: Exits if wrong hour (DST guard)

    L->>DB: GetItem WEEK#2026-05-17
    DB-->>L: (not found)

    L->>L: Generate UUID token
    L->>DB: PutItem — status=PENDING, token, ttl
    L->>CH: _notify_initial(confirm_url)
    deactivate L

    CH-->>W: Reminder + confirmation link
    Note over W: Link: /confirm?week=…&token=…
```

---

## Daily Reminder Flow

Fires every day at 08:00 UK time. Skips silently if the task is already confirmed or a reminder was already sent today.

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#1e3a5f', 'primaryTextColor': '#c9d1d9', 'primaryBorderColor': '#4a7ab5', 'lineColor': '#58a6ff', 'edgeLabelBackground': '#0d1117'}}}%%

flowchart TD
    START([EventBridge fires\n08:00 UK]) --> GUARD{Actual London\nhour == 08?}

    GUARD -- No --> SKIP1(["⏭ Skip\nwrong hour"])
    GUARD -- Yes --> LOOKUP["Look up\nWEEK#&lt;this Sunday&gt;"]

    LOOKUP --> EXISTS{Record\nexists?}
    EXISTS -- No --> SKIP2(["⏭ Skip\nreminder not sent yet"])
    EXISTS -- Yes --> STATUS{status?}

    STATUS -- CONFIRMED --> SKIP3(["✅ Skip\nalready done!"])
    STATUS -- PENDING --> DEDUP{Today already\nin sms_dates?}

    DEDUP -- Yes --> SKIP4(["⏭ Skip\nalready sent today"])
    DEDUP -- No --> PICK["Select escalating message\nby sms_dates length"]

    PICK --> SEND["_notify_reminder()\n(Twilio SMS / WhatsApp / skipped)"]
    SEND --> UPDATE["Append today to\nsms_dates in DynamoDB"]
    UPDATE --> DONE(["📨 Reminder delivered"])

    style START fill:#1a3a1a,stroke:#3a7a3a,color:#90d090
    style DONE  fill:#1a3a1a,stroke:#3a7a3a,color:#90d090
    style SKIP1 fill:#2a2a2a,stroke:#555,color:#888
    style SKIP2 fill:#2a2a2a,stroke:#555,color:#888
    style SKIP3 fill:#1a3a1a,stroke:#3a7a3a,color:#90d090
    style SKIP4 fill:#2a2a2a,stroke:#555,color:#888
    style PICK  fill:#2a1a3a,stroke:#6a3a8a,color:#b070d0
    style SEND  fill:#2a1a3a,stroke:#6a3a8a,color:#b070d0
```

---

## Confirmation Flow

When the recipient clicks the confirmation link, API Gateway (throttled at 5 req/s) invokes `ConfirmTask`. The link is valid for 30 days; clicking it again after confirmation is a no-op.

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#1e3a5f', 'primaryTextColor': '#c9d1d9', 'primaryBorderColor': '#4a7ab5', 'lineColor': '#58a6ff', 'edgeLabelBackground': '#0d1117'}}}%%

sequenceDiagram
    actor W  as Recipient
    participant GW as API Gateway<br/>(5 req/s throttle)
    participant L  as ConfirmTask λ
    participant DB as DynamoDB
    participant CH as Channel (SES / WhatsApp)

    W->>GW: GET /confirm?week=2026-05-17&token=uuid
    GW->>L: Invoke with query params
    activate L

    L->>DB: GetItem WEEK#2026-05-17
    DB-->>L: {status: PENDING, token: "uuid", ...}

    L->>L: Validate token matches
    L->>DB: UpdateItem — status=CONFIRMED, confirmed_at=now
    L->>CH: _notify_congratulations(sms_count, animal)

    L-->>GW: 200 HTML — "All done! ✅"
    deactivate L
    GW-->>W: Success page + congratulations message

    Note over W,DB: SendDailySMS now sees CONFIRMED<br/>and stops sending reminders
```

---

## DynamoDB Data Model

One record per week. The partition key encodes the task type and date, making lookups O(1).

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#3a2a1e', 'primaryTextColor': '#c9d1d9', 'primaryBorderColor': '#8a5a2a', 'lineColor': '#d4a55a', 'edgeLabelBackground': '#0d1117'}}}%%

erDiagram
    REMINDERS_TABLE {
        string partition_key    "WEEK-YYYY-MM-DD (prod) or TEST-YYYY-MM-DD (test)"
        string status           "PENDING or CONFIRMED"
        string token            "UUID - validates confirmation link"
        string email_sent_at    "ISO-8601 timestamp"
        string sms_dates        "List of ISO dates (prod) or timestamps (test)"
        string last_sms_at      "ISO timestamp - test mode dedup only"
        string confirmed_at     "ISO-8601 timestamp - present when CONFIRMED"
        number ttl              "Unix epoch - DynamoDB auto-expires after 30 days"
    }
```

**Key design decisions:**

- **PAY_PER_REQUEST billing** — traffic is tiny (≤8 reads + writes per week), so on-demand is far cheaper than provisioned.
- **TTL** — records auto-delete after 30 days with no cron cleanup job needed.
- **`sms_dates` as a list** — simple append-only log. Length doubles as the escalation index with no extra counter field.
- **`TEST#` prefix** — test runs get an isolated key so they can't interfere with a real in-flight week.

---

## Secrets Management

Sensitive credentials are stored in AWS Secrets Manager and fetched once per Lambda cold start, then cached in memory for the instance lifetime.

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#1e3a5f', 'primaryTextColor': '#c9d1d9', 'primaryBorderColor': '#4a7ab5', 'lineColor': '#58a6ff', 'edgeLabelBackground': '#0d1117'}}}%%

sequenceDiagram
    participant L  as Lambda (cold start)
    participant SM as Secrets Manager
    participant ENV as Environment Variables

    L->>SM: GetSecretValue(SECRETS_ARN)
    SM-->>L: {"twilio_auth_token": "...", "whatsapp_access_token": "..."}
    Note over L: Cached in module-level _SECRETS dict

    L->>ENV: Read non-sensitive config<br/>(WIFE_EMAIL, WIFE_PHONE, TABLE_NAME…)
    Note over L,ENV: Falls back to env vars if<br/>Secrets Manager unavailable
```

| Secret | Location | Visible in Lambda config? |
|---|---|:---:|
| `twilio_auth_token` | Secrets Manager | No |
| `whatsapp_access_token` | Secrets Manager | No |
| `WIFE_EMAIL` | Environment variable | Yes — restrict `lambda:GetFunctionConfiguration` |
| `WIFE_PHONE` | Environment variable | Yes — restrict `lambda:GetFunctionConfiguration` |
| `TWILIO_ACCOUNT_SID` | Environment variable | Yes (identifier, not credential) |

---

## Task State Machine

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#1e3a5f', 'primaryTextColor': '#c9d1d9', 'primaryBorderColor': '#4a7ab5', 'lineColor': '#58a6ff', 'edgeLabelBackground': '#0d1117'}}}%%

stateDiagram-v2
    direction LR

    [*]       --> PENDING   : Sunday reminder sent\n(new DynamoDB record)
    PENDING   --> PENDING   : Daily 08:00 escalation\n(channel-agnostic)
    PENDING   --> CONFIRMED : Link clicked\n(token validated)
    CONFIRMED --> [*]       : 30-day TTL expires
    PENDING   --> [*]       : 30-day TTL expires\n(if never confirmed)
```

---

## Reminder Escalation Ladder

Each day without confirmation triggers the next message in the sequence. From day 9 onwards the final message repeats. Works across all channels (email body, SMS, WhatsApp).

| # | Tone | Opening |
|---|---|---|
| 1 | Gentle | *"Morning! Just a reminder to clean the washing machine filter…"* |
| 2 | Nudge | *"Day 2: Still waiting on that filter! It won't clean itself (believe me, we checked)…"* |
| 3 | Dramatic | *"Day 3: The filter is starting to feel forgotten. It stares sadly at the drum…"* |
| 4 | Sentient filter | *"Day 4: The filter has begun keeping a journal. Entry 1: 'Still unclean. Still unloved.'…"* |
| 5 | Legal threats | *"Day 5: The filter has engaged legal counsel… a strongly-worded letter is being drafted…"* |
| 6 | Industrial action | *"Day 6: The washing machine has announced a work-to-rule in solidarity with the filter…"* |
| 7 | Full crisis | *"Day 7: ONE WEEK. The filter has gone to the press…'NEGLECTED FILTER SUFFERS IN SILENCE'…"* |
| 8 | Existential | *"Day 8: The filter has accepted its fate and is making peace with the universe. We have not…"* |
| 9+ | Maximum stern | *"ANOTHER DAY. STILL UNCLEAN. The filter has written its will…"* _(repeats)_ |

---

## Timezone Handling (GMT / BST)

The UK observes GMT (UTC+0) in winter and BST (UTC+1) in summer. EventBridge only understands UTC, so two rules fire per trigger — one for each possible UTC offset. The Lambda checks `datetime.now(ZoneInfo("Europe/London")).hour` and exits immediately if it isn't the target hour.

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#1e3a5f', 'primaryTextColor': '#c9d1d9', 'primaryBorderColor': '#4a7ab5', 'lineColor': '#58a6ff', 'edgeLabelBackground': '#0d1117'}}}%%

gantt
    title EventBridge rules firing vs. actual UK time
    dateFormat HH:mm
    axisFormat %H:%M

    section Sunday Reminder
    SundayEmailBST fires (08:00 UTC → 09:00 BST ✓) : milestone, 08:00, 0m
    SundayEmailGMT fires (09:00 UTC → 09:00 GMT ✓) : milestone, 09:00, 0m

    section Daily Reminder
    DailySMSBST fires (07:00 UTC → 08:00 BST ✓) : milestone, 07:00, 0m
    DailySMSGMT fires (08:00 UTC → 08:00 GMT ✓) : milestone, 08:00, 0m
```

In BST the `GMT` rule fires at 10:00 UK time — the hour check rejects it immediately with no side effects.

---

## Test Mode

Passing `{"test": true}` in the Lambda event activates a parallel test cycle that never touches production records.

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#1e3a5f', 'primaryTextColor': '#c9d1d9', 'primaryBorderColor': '#4a7ab5', 'lineColor': '#58a6ff', 'edgeLabelBackground': '#0d1117'}}}%%

flowchart LR
    subgraph prod ["Production cycle  (weekly)"]
        direction TB
        P1["WEEK#2026-05-17\nstatus=PENDING"]
        P2["Reminder sent daily\nat 08:00 UK"]
        P3["WEEK#2026-05-17\nstatus=CONFIRMED"]
        P1 --> P2 --> P3
    end

    subgraph test ["Test cycle  (every 10 min)"]
        direction TB
        T1["TEST#2026-05-16\nstatus=PENDING\n(reset on each test trigger)"]
        T2["Reminder sent every\n10 minutes"]
        T3["TEST#2026-05-16\nstatus=CONFIRMED"]
        T1 --> T2 --> T3
    end

    style prod fill:#0d2137,stroke:#1e4a7a
    style test fill:#1a2a0d,stroke:#3a5a1a
```

| Behaviour | Production | Test |
|---|---|---|
| Trigger | EventBridge, Sunday 09:00 UK | Manual invoke with `{"test": true}` |
| DynamoDB key | `WEEK#YYYY-MM-DD` | `TEST#YYYY-MM-DD` |
| Time guard | Exits if not correct UK hour | Bypassed |
| Reminder dedup | Once per calendar day | Once per 10 minutes |
| Email subject | Normal | Prefixed with `[TEST]` |
| Email banner | None | Orange "TEST MODE" banner |
| Confirm link | `…&token=…` | `…&token=…&test=1` |

**To run a test cycle:**

```bash
# 1. Trigger the test reminder (re-run to reset the escalation counter)
aws lambda invoke \
  --function-name washingmachine-notificatio-SendWeeklyEmailFunction-FhfvdL0p367f \
  --payload file:///tmp/payload.json \
  --profile dev --region eu-west-2 \
  --cli-binary-format raw-in-base64-out /dev/stdout

# 2. Enable the 10-minute rule in the AWS Console:
#    EventBridge → Rules → …TestSMSEvery10Min… → Enable

# 3. Disable the rule when finished
```

---

## Deployment

```bash
# Prerequisites: AWS CLI + SAM CLI installed, AWS profile configured

cp samconfig.toml.example samconfig.toml
# Edit samconfig.toml — set WifeEmail, WifePhone, FromEmail

sam build && sam deploy
```

**One-time AWS setup required before first deploy:**

1. **SES → Verified identities** — verify your sender address (`guy@dunite.uk`)
2. **SES production access** — request via `aws sesv2 put-account-details` or AWS Console to lift sandbox restrictions
3. **Secrets Manager** — populated automatically by CloudFormation from `samconfig.toml` parameter values

**Optional channels:**

| Channel | Additional setup |
|---|---|
| Twilio SMS | Set `TwilioEnabled=true` and fill in `TwilioAccountSid`, `TwilioAuthToken`, `TwilioFromNumber` |
| WhatsApp | Set `WhatsAppPhoneNumberId`, `WhatsAppAccessToken`, create three approved Meta message templates |

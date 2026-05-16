# Architecture — Washing Machine Filter Reminder

A fully serverless AWS solution that reminds a household member to clean the washing machine filter every week, escalating from a polite email to increasingly dramatic SMS messages until the task is confirmed.

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

    subgraph store ["  DynamoDB  "]
        DB[("Reminders Table\n─────────────\nPK: WEEK#YYYY-MM-DD\nstatus · token\nsms_dates · ttl")]
    end

    subgraph msg ["  Messaging  "]
        SES["SES\nEmail"]
        SNS["SNS\nSMS"]
    end

    subgraph api ["  API Gateway  "]
        GW["HTTP API\nGET /confirm"]
    end

    subgraph human ["  Recipient  "]
        EM["📧 Email"]
        PH["📱 Phone"]
    end

    EB1 -->|fires| L1
    EB2 -->|fires| L2
    EB3 -.->|fires test| L2

    L1 -->|create record| DB
    L1 -->|send| SES
    L2 -->|check & update| DB
    L2 -->|publish| SNS
    L3 -->|mark confirmed| DB

    SES --> EM
    SNS --> PH
    EM -->|"clicks link"| GW
    GW -->|invoke| L3

    classDef schedule fill:#1a3a5c,stroke:#4a7ab5,color:#a0c4e8,rx:6
    classDef fn fill:#1e3a1e,stroke:#3a7a3a,color:#90d090
    classDef storage fill:#3a2a1e,stroke:#8a5a2a,color:#d0a070
    classDef messaging fill:#2a1a3a,stroke:#6a3a8a,color:#b070d0
    classDef gateway fill:#1a2a3a,stroke:#3a5a7a,color:#70a0c0
    classDef person fill:#2a2a2a,stroke:#5a5a5a,color:#c0c0c0

    class EB1,EB2,EB3 schedule
    class L1,L2,L3 fn
    class DB storage
    class SES,SNS messaging
    class GW gateway
    class EM,PH person
```

---

## AWS Components

| Component | Resource | Purpose |
|---|---|---|
| **EventBridge** | 4 scheduled rules (2 prod + 1 test) | Triggers email & SMS Lambdas on schedule |
| **Lambda** × 3 | `SendWeeklyEmail`, `SendDailySMS`, `ConfirmTask` | All business logic |
| **DynamoDB** | Single table, PAY_PER_REQUEST | Tracks weekly task state (30-day TTL) |
| **SES** | Email via verified identity | Sends the weekly reminder email |
| **SNS** | Direct `Publish` to phone number | Sends escalating SMS messages |
| **API Gateway** | HTTP API, `GET /confirm` | Serves the confirmation link |
| **IAM** | Single shared role | Least-privilege access to DDB, SES, SNS |

---

## Weekly Email Flow

Fires every Sunday at 09:00 UK time. Two EventBridge rules cover GMT and BST — the Lambda checks the actual London hour and exits early if wrong.

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#1e3a5f', 'primaryTextColor': '#c9d1d9', 'primaryBorderColor': '#4a7ab5', 'lineColor': '#58a6ff', 'edgeLabelBackground': '#0d1117'}}}%%

sequenceDiagram
    actor EB as EventBridge
    participant L  as SendWeeklyEmail λ
    participant DB as DynamoDB
    participant SE as SES
    actor W  as Wife's inbox

    EB->>L: Sunday 08:00 or 09:00 UTC
    activate L

    L->>L: Check actual London time == 09:xx
    Note over L: Exits if wrong hour (DST guard)

    L->>DB: GetItem WEEK#2026-05-17
    DB-->>L: (not found)

    L->>L: Generate UUID token
    L->>DB: PutItem — status=PENDING, token, ttl
    L->>SE: SendEmail with confirm link
    deactivate L

    SE-->>W: "Clean the filter" email + button
    Note over W: Link contains week + token
```

---

## Daily SMS Reminder Flow

Fires every day at 08:00 UK time. Skips silently if the task is already confirmed or was already sent today.

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#1e3a5f', 'primaryTextColor': '#c9d1d9', 'primaryBorderColor': '#4a7ab5', 'lineColor': '#58a6ff', 'edgeLabelBackground': '#0d1117'}}}%%

flowchart TD
    START([EventBridge fires\n08:00 UK]) --> GUARD{Actual London\nhour == 08?}

    GUARD -- No --> SKIP1(["⏭ Skip\nwrong hour"])
    GUARD -- Yes --> LOOKUP["Look up\nWEEK#&lt;this Sunday&gt;"]

    LOOKUP --> EXISTS{Record\nexists?}
    EXISTS -- No --> SKIP2(["⏭ Skip\nemail not sent yet"])
    EXISTS -- Yes --> STATUS{status?}

    STATUS -- CONFIRMED --> SKIP3(["✅ Skip\nalready done!"])
    STATUS -- PENDING --> DEDUP{Today already\nin sms_dates?}

    DEDUP -- Yes --> SKIP4(["⏭ Skip\nalready sent today"])
    DEDUP -- No --> PICK["Select message\nby sms_dates length\n(escalation index)"]

    PICK --> SEND["SNS Publish\nto mobile"]
    SEND --> UPDATE["Append today to\nsms_dates in DynamoDB"]
    UPDATE --> DONE(["📱 SMS delivered"])

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

When the recipient clicks the button in the email, API Gateway invokes `ConfirmTask`. The link is valid for 30 days and is single-use (token validated, status checked).

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#1e3a5f', 'primaryTextColor': '#c9d1d9', 'primaryBorderColor': '#4a7ab5', 'lineColor': '#58a6ff', 'edgeLabelBackground': '#0d1117'}}}%%

sequenceDiagram
    actor W  as Wife
    participant GW as API Gateway
    participant L  as ConfirmTask λ
    participant DB as DynamoDB

    W->>GW: GET /confirm?week=2026-05-17&token=uuid
    GW->>L: Invoke with query params
    activate L

    L->>DB: GetItem WEEK#2026-05-17
    DB-->>L: {status: PENDING, token: "uuid", ...}

    L->>L: Validate token matches
    L->>DB: UpdateItem — status=CONFIRMED,\nconfirmed_at=now

    L-->>GW: 200 HTML — "All done! ✅"
    deactivate L
    GW-->>W: Success page

    Note over W,DB: SendDailySMS now sees CONFIRMED\nand stops sending reminders
```

---

## DynamoDB Data Model

One record per week. The partition key encodes the task type and date, making lookups O(1).

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#3a2a1e', 'primaryTextColor': '#c9d1d9', 'primaryBorderColor': '#8a5a2a', 'lineColor': '#d4a55a', 'edgeLabelBackground': '#0d1117'}}}%%

erDiagram
    REMINDERS_TABLE {
        string PK           "WEEK#YYYY-MM-DD (prod) or TEST#YYYY-MM-DD (test)"
        string status       "PENDING or CONFIRMED"
        string token        "UUID — validates confirmation link"
        string email_sent_at "ISO-8601 timestamp"
        list   sms_dates    "ISO dates (prod) or ISO timestamps (test)"
        string last_sms_at  "ISO timestamp — test mode dedup only"
        string confirmed_at "ISO-8601 timestamp — present when CONFIRMED"
        number ttl          "Unix epoch — DynamoDB auto-expires after 30 days"
    }
```

**Key design decisions:**

- **PAY_PER_REQUEST billing** — traffic is tiny (≤8 reads + writes per week), so on-demand is far cheaper than provisioned.
- **TTL** — records auto-delete after 30 days with no cron cleanup job needed.
- **`sms_dates` as a list** — simple append-only log. Length doubles as the escalation index with no extra counter field.
- **`TEST#` prefix** — test runs get an isolated key so they can't interfere with a real in-flight week.

---

## Task State Machine

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#1e3a5f', 'primaryTextColor': '#c9d1d9', 'primaryBorderColor': '#4a7ab5', 'lineColor': '#58a6ff', 'edgeLabelBackground': '#0d1117'}}}%%

stateDiagram-v2
    direction LR

    [*]       --> PENDING   : Sunday email sent\n(new DynamoDB record)
    PENDING   --> PENDING   : Daily 08:00 SMS\n(escalating message)
    PENDING   --> CONFIRMED : Link clicked\n(token validated)
    CONFIRMED --> [*]       : 30-day TTL expires
    PENDING   --> [*]       : 30-day TTL expires\n(if never confirmed)
```

---

## SMS Escalation Ladder

Each day without confirmation triggers the next message in the sequence. From day 9 onwards the final message repeats.

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

The UK observes GMT (UTC+0) in winter and BST (UTC+1) in summer. EventBridge only understands UTC, so two rules fire per trigger — one for each possible UTC offset. The Lambda then checks `datetime.now(ZoneInfo("Europe/London")).hour` and exits immediately if it isn't the target hour.

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#1e3a5f', 'primaryTextColor': '#c9d1d9', 'primaryBorderColor': '#4a7ab5', 'lineColor': '#58a6ff', 'edgeLabelBackground': '#0d1117'}}}%%

gantt
    title EventBridge rules firing vs. actual UK time
    dateFormat HH:mm
    axisFormat %H:%M

    section Sunday Email
    SundayEmailBST fires (08:00 UTC → 09:00 BST ✓) : milestone, 08:00, 0m
    SundayEmailGMT fires (09:00 UTC → 09:00 GMT ✓) : milestone, 09:00, 0m

    section Daily SMS
    DailySMSBST fires (07:00 UTC → 08:00 BST ✓) : milestone, 07:00, 0m
    DailySMSGMT fires (08:00 UTC → 08:00 GMT ✓) : milestone, 08:00, 0m
```

In BST the `GMT` rule fires at 10:00 UK time — the hour check rejects it immediately with no side effects.

---

## Test Mode

Passing `{"test": true}` in the Lambda event (or via the disabled EventBridge rule) activates a parallel test cycle that never touches production records.

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#1e3a5f', 'primaryTextColor': '#c9d1d9', 'primaryBorderColor': '#4a7ab5', 'lineColor': '#58a6ff', 'edgeLabelBackground': '#0d1117'}}}%%

flowchart LR
    subgraph prod ["Production cycle  (weekly)"]
        direction TB
        P1["WEEK#2026-05-17\nstatus=PENDING"]
        P2["SMS sent daily\nat 08:00 UK"]
        P3["WEEK#2026-05-17\nstatus=CONFIRMED"]
        P1 --> P2 --> P3
    end

    subgraph test ["Test cycle  (every 10 min)"]
        direction TB
        T1["TEST#2026-05-16\nstatus=PENDING\n(reset on each test email)"]
        T2["SMS sent every\n10 minutes"]
        T3["TEST#2026-05-16\nstatus=CONFIRMED"]
        T1 --> T2 --> T3
    end

    style prod fill:#0d2137,stroke:#1e4a7a
    style test fill:#1a2a0d,stroke:#3a5a1a
```

| Behaviour | Production | Test |
|---|---|---|
| Email trigger | EventBridge, Sunday 09:00 UK | Manual invoke with `{"test": true}` |
| DynamoDB key | `WEEK#YYYY-MM-DD` | `TEST#YYYY-MM-DD` |
| Time guard | Exits if not correct UK hour | Bypassed |
| SMS dedup | Once per calendar day | Once per 10 minutes |
| Email subject | Normal | Prefixed with `[TEST]` |
| Email banner | None | Orange "TEST MODE" banner |
| Confirm link | `…&token=…` | `…&token=…&test=1` |

**To run a test cycle:**

```bash
# 1. Trigger the test email (can re-run to reset the SMS counter)
aws lambda invoke \
  --function-name washingmachine-notifications-SendWeeklyEmailFunction \
  --payload '{"test": true}' \
  --profile dev /dev/stdout

# 2. Enable the 10-minute SMS rule in the AWS Console:
#    EventBridge → Rules → TestSMSEvery10Min → Enable

# 3. Disable the rule when finished
```

---

## Deployment

```bash
# Prerequisites: AWS CLI + SAM CLI installed, AWS profile configured

cp samconfig.toml.example samconfig.toml
# Edit samconfig.toml — set WifeEmail, WifePhone (+44...), FromEmail

sam build && sam deploy
```

**One-time AWS setup required before first deploy:**

1. **SES → Verified identities** — verify your sender address (and recipient address if still in SES sandbox)
2. **SES production access** — request via AWS Console to send to unverified addresses
3. **SNS → Text messaging** — raise the default $1/month SMS spend limit for production use

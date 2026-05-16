# AWS Well-Architected Review — Washing Machine Filter Reminder

> *This review applies the AWS Well-Architected Framework to a system designed to remind one person to clean one filter once a week. The framework was built for enterprise workloads. We are using it anyway.*

**Review date:** May 2026
**Reviewer:** Claude (AI-assisted self-assessment)
**Workload risk profile:** Low — single household, non-critical, no SLA, no revenue dependency

---

## Executive Summary

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#1e3a5f', 'primaryTextColor': '#c9d1d9', 'xyChart': {'backgroundColor': '#0d1117', 'plotColorPalette': '#58a6ff'}}}}%%
xychart-beta
    title "Well-Architected Pillar Scores (out of 5)"
    x-axis ["Operational Excellence", "Security", "Reliability", "Performance Efficiency", "Cost Optimization", "Sustainability"]
    y-axis "Score" 0 --> 5
    bar [4, 5, 4, 4, 5, 3]
```

| Pillar | Score | HRI | MRI | Status |
|--------|:-----:|:---:|:---:|--------|
| Operational Excellence | 4/5 | 0 | 2 | ✅ Alarms and DLQ in place |
| Security | 5/5 | 0 | 1 | ✅ Excellent — threat model fully maintained |
| Reliability | 4/5 | 0 | 1 | ✅ DLQ and failure alerting resolved |
| Performance Efficiency | 4/5 | 0 | 2 | ✅ Well-optimised — minor tuning opportunities |
| Cost Optimization | 5/5 | 0 | 0 | ✅ Effectively free |
| Sustainability | 3/5 | 0 | 1 | ⚠️ ARM/Graviton not used |
| **Overall** | **4.2/5** | **0** | **7** | |

**Key message:** All four High Risk Issues have been resolved. CloudWatch alarms now fire on any Lambda error, and a dead letter queue catches events that fail after retries. The remaining gaps are medium priority — structured logging, automated tests, and switching to ARM Graviton2 are the next logical steps.

---

## Workload Context

Before applying best practices, it is worth acknowledging what this workload is and is not:

| Factor | Assessment |
|--------|-----------|
| Criticality | Low — a missed reminder means a dirty filter, not a business outage |
| Users | 1 (the recipient) |
| Revenue dependency | None |
| Data sensitivity | Low-medium — PII (email/phone) protected in Secrets Manager |
| Recovery time objective | Hours to days (acceptable) |
| Recovery point objective | 1 week (one missed cycle is tolerable) |

Some Well-Architected best practices (multi-region, cross-AZ replication, chaos engineering) are acknowledged but explicitly accepted as out of scope for this risk profile.

---

## Pillar 1 — Operational Excellence

*Run and monitor systems to deliver business value, and continually improve supporting processes and procedures.*

### Findings

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#1e3a5f', 'primaryTextColor': '#c9d1d9', 'primaryBorderColor': '#4a7ab5', 'lineColor': '#58a6ff', 'edgeLabelBackground': '#0d1117', 'clusterBkg': '#0d2137', 'clusterBorder': '#30363d'}}}%%

flowchart LR
    subgraph good ["✅ In place"]
        A["Infrastructure as Code\n(SAM/CloudFormation)"]
        B["Test mode\n(safe pre-prod testing)"]
        C["Code quality\n(Pylint 10/10)"]
        D["Documentation\n(arch + threat model)"]
        E["Data lifecycle\n(DynamoDB TTL)"]
    end

    subgraph gaps ["⚠️ Gaps"]
        F["No CloudWatch\nalarms"]
        G["No dead letter\nqueue"]
        H["Unstructured\nlogging"]
        I["No automated\ntests or CI/CD"]
    end
```

| # | Finding | Risk | Recommendation |
|---|---------|:----:|----------------|
| OE-1 | **No CloudWatch alarms** — Lambda errors, throttles, and duration spikes produce no alerts | ✅ ~~High~~ | Resolved — CloudWatch alarms on `Errors` for all three functions, DLQ depth, and API Gateway 4xx. All route to SNS → email. |
| OE-2 | **No dead letter queue (DLQ)** — EventBridge invokes Lambdas asynchronously. After 2 retries, failed events are silently discarded | ✅ ~~High~~ | Resolved — SQS DLQ attached to `SendWeeklyEmail` and `SendDailySMS`. CloudWatch alarm fires on any message in the queue. |
| OE-3 | **Unstructured logging** — Lambda handlers use `print()` producing plain text. Log querying in CloudWatch Insights is difficult | 🟡 Medium | Replace `print()` with Python's `logging` module using a JSON formatter. Enables structured queries like `filter @message.status = "CONFIRMED"`. |
| OE-4 | **No automated tests** — no unit or integration tests exist | 🟡 Medium | Add `pytest` unit tests for the core logic (`_escalating_sms`, `_sms_commentary`, `_week_pk`, etc.). Mock boto3 clients. Target >80% coverage. |
| OE-5 | **No CI/CD pipeline** — deployment is a manual `sam deploy` | 🟡 Medium | Add a GitHub Actions workflow: lint → test → `sam build` → `sam deploy` on push to `main`. |
| OE-6 | **No CloudWatch dashboard** — no single pane of glass for operational health | 🟢 Low | Create a dashboard with: Lambda invocation counts, error rates, DynamoDB read/write units, SES send metrics, CloudFront request counts. |

### Best Practices Met

- ✅ **OPS 1** — Workload is defined as code (SAM template)
- ✅ **OPS 5** — Test mode enables safe experimentation without production impact
- ✅ **OPS 6** — DynamoDB TTL automates data lifecycle management
- ✅ **OPS 8** — Documentation maintained alongside code in the same repository

---

## Pillar 2 — Security

*Protect information, systems, and assets while delivering business value through risk assessments and mitigation strategies.*

> This pillar is covered in depth in [`threat-model.md`](threat-model.md) (v1.3). Summary below.

### Findings

| # | Finding | Risk | Status |
|---|---------|:----:|--------|
| SEC-1 | Credentials in Lambda environment variables | 🔴 ~~High~~ | ✅ Resolved — moved to Secrets Manager |
| SEC-2 | No API Gateway rate limiting | 🟡 ~~Medium~~ | ✅ Resolved — 5 req/s, burst 10 |
| SEC-3 | PII (email/phone) in Lambda environment | 🟡 ~~Medium~~ | ✅ Resolved — moved to Secrets Manager |
| SEC-4 | Non-GB access to confirmation endpoint | 🟡 ~~Medium~~ | ✅ Resolved — CloudFront GB geo restriction |
| SEC-5 | DynamoDB CloudTrail data events not enabled | 🟡 Medium | ⚠️ Open — no data-plane audit log |
| SEC-6 | `ses:SendEmail` IAM action scoped to `Resource: '*'` | 🟢 Low | Could be narrowed to verified identity ARNs |

### Best Practices Met

- ✅ **SEC 1** — Implement a strong identity foundation (IAM least-privilege, no wildcard actions on sensitive resources)
- ✅ **SEC 2** — Enable traceability (CloudWatch logs, `confirmed_at` timestamp)
- ✅ **SEC 3** — Apply security at all layers (CloudFront → API GW throttle → token validation → IAM)
- ✅ **SEC 4** — Protect data in transit (HTTPS enforced via CloudFront and API Gateway)
- ✅ **SEC 5** — Protect data at rest (DynamoDB default encryption, secrets in Secrets Manager)
- ✅ **SEC 7** — Prepare for security events (threat model maintained, findings tracked)

---

## Pillar 3 — Reliability

*Ensure a workload performs its intended function correctly and consistently when it's expected to.*

### Findings

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#1e3a5f', 'primaryTextColor': '#c9d1d9', 'primaryBorderColor': '#4a7ab5', 'lineColor': '#58a6ff', 'edgeLabelBackground': '#0d1117'}}}%%

sequenceDiagram
    participant EB as EventBridge
    participant L  as Lambda
    participant DLQ as DLQ (missing)
    participant CW as CloudWatch (no alarm)

    EB->>L: Invoke (async)
    L->>L: Error occurs
    Note over L: Retry 1 of 2
    L->>L: Error again
    Note over L: Retry 2 of 2
    L->>L: Error again
    L--xDLQ: Event discarded silently
    Note over DLQ,CW: Nobody knows.\nThe reminder was never sent.\nThe filter remains unclean.
```

| # | Finding | Risk | Recommendation |
|---|---------|:----:|----------------|
| REL-1 | **No dead letter queue** — async Lambda failures are silently discarded after 2 retries | ✅ ~~High~~ | Resolved — SQS DLQ attached to both scheduled functions. Messages retained for 14 days. |
| REL-2 | **No failure alerting** — Lambda errors produce no notification | ✅ ~~High~~ | Resolved — CloudWatch alarms on Lambda `Errors` metric, DLQ depth, and API Gateway 4xx throttling. All alert via SNS to `AlertEmail`. |
| REL-3 | **No post-deploy verification** — no automated check that Sunday's email was actually sent | 🟡 Medium | Add a Monday morning EventBridge rule that checks DynamoDB for a `WEEK#<last-sunday>` record with `email_sent_at` populated. Alert if missing. |
| REL-4 | **Single region** — `eu-west-2` only | 🟢 Low | Accepted for this risk profile. Recovery is a `sam deploy` to another region. |

### Best Practices Met

- ✅ **REL 1** — Automatic recovery from failure (Lambda retries, idempotent confirmation endpoint)
- ✅ **REL 2** — Test recovery procedures (test mode validates the full path without production impact)
- ✅ **REL 8** — Use highly available managed services (DynamoDB, SES, Lambda — all multi-AZ by default)
- ✅ **REL 9** — Automate failure handling (DynamoDB TTL, idempotent operations prevent data corruption)
- ✅ **REL 10** — Use fault isolation (single-purpose Lambda functions; a failure in `ConfirmTask` doesn't affect `SendWeeklyEmail`)

---

## Pillar 4 — Performance Efficiency

*Use computing resources efficiently to meet system requirements, and maintain that efficiency as demand changes and technologies evolve.*

### Findings

| # | Finding | Risk | Recommendation |
|---|---------|:----:|----------------|
| PERF-1 | **Lambda on x86 architecture** — all three functions use x86 (default). ARM (Graviton2) delivers ~20% better price-performance | 🟡 Medium | Add `Architectures: [arm64]` to Globals in `template.yaml`. Python 3.12 fully supports ARM Lambda. No code changes required. |
| PERF-2 | **Lambda memory not tuned** — default 128MB used. Actual memory use may allow reduction (lower cost) or require increase (faster execution) | 🟡 Medium | Run [AWS Lambda Power Tuning](https://github.com/alexcasalboni/aws-lambda-power-tuning) step function against each handler to find the optimal memory/cost balance. |
| PERF-3 | **Twilio SDK loaded unconditionally** — `from twilio.rest import Client` is inside a conditional block but the `twilio` package is always present in the deployment package, adding cold start overhead when unused | 🟢 Low | Separate optional dependencies into a Lambda Layer, or use conditional packaging in `requirements.txt`. |
| PERF-4 | **Global Lambda timeout of 30s** — `ConfirmTask` completes in ~500ms; a 30s timeout is unnecessarily permissive | 🟢 Low | Set per-function timeouts: `SendWeeklyEmail` 30s (calls SES + external APIs), `SendDailySMS` 15s, `ConfirmTask` 10s. |

### Best Practices Met

- ✅ **PERF 1** — Secrets Manager response cached at module level — no per-invocation API call
- ✅ **PERF 2** — DynamoDB single-item GetItem by partition key — O(1) regardless of table size
- ✅ **PERF 3** — CloudFront PriceClass_100 — GB users served from nearest European edge nodes
- ✅ **PERF 4** — PAY_PER_REQUEST on DynamoDB — no over-provisioning at any traffic level
- ✅ **PERF 5** — Serverless architecture — no idle compute resources

---

## Pillar 5 — Cost Optimization

*Avoid unnecessary costs.*

### Current Cost Profile

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#1e3a5f', 'primaryTextColor': '#c9d1d9', 'primaryBorderColor': '#4a7ab5', 'lineColor': '#58a6ff'}}}%%

pie title Monthly cost breakdown (~$0.40 total)
    "Secrets Manager (1 secret)" : 85
    "Everything else (free tier)" : 15
```

| Service | Monthly usage | Monthly cost |
|---------|:-------------:|:------------:|
| Lambda | ~40 invocations, ~20s total compute | Free tier |
| DynamoDB | ~4 reads, ~4 writes, ~1KB stored | Free tier |
| SES | ~8 emails | Free tier |
| CloudFront | ~5 requests | Free tier |
| API Gateway | ~5 requests | Free tier |
| EventBridge | 5 rules | Free |
| Secrets Manager | 1 secret + ~40 GetSecretValue calls | **~$0.40** |
| **Total** | | **~$0.40/month** |

### Findings

| # | Finding | Risk | Recommendation |
|---|---------|:----:|----------------|
| COST-1 | **Secrets Manager at $0.40/month** — the single meaningful cost in this workload | 🟢 Low | SSM Parameter Store SecureString is free for standard parameters and would eliminate this cost. Trade-off: less auditable, no automatic rotation. At $0.40/month the trade-off does not justify migration. |

### Best Practices Met

- ✅ **COST 1** — Practice Cloud Financial Management — cost reviewed and documented
- ✅ **COST 2** — Expenditure and usage awareness — costs are minimal and entirely within free tier except Secrets Manager
- ✅ **COST 3** — Cost-effective resources — serverless; no provisioned capacity; PAY_PER_REQUEST
- ✅ **COST 4** — Manage demand and supply — DynamoDB auto-scales; Lambda scales to zero
- ✅ **COST 5** — Optimise over time — TTL prevents unbounded storage accumulation

---

## Pillar 6 — Sustainability

*Minimise the environmental impacts of running cloud workloads.*

### Findings

| # | Finding | Risk | Recommendation |
|---|---------|:----:|----------------|
| SUS-1 | **Lambda on x86 architecture** — ARM (Graviton2) processors are ~60% more energy-efficient per unit of compute than equivalent x86 | 🟡 Medium | Switch to `arm64` in `template.yaml` (same change as PERF-1). This is the single most impactful sustainability improvement available. |
| SUS-2 | **No resource tagging** — AWS Customer Carbon Footprint Tool and cost allocation reports require consistent tagging | 🟢 Low | Add stack-level tags: `Project`, `Environment`, `Owner`. In SAM, use the `Tags` section under `Globals`. |

### Current Sustainability Strengths

- ✅ **SUS 1** — Serverless architecture — compute is near-zero between invocations (~99.9% idle time)
- ✅ **SUS 2** — CloudFront PriceClass_100 — restricts traffic to US/EU edge locations (lower transport emissions than global distribution)
- ✅ **SUS 3** — DynamoDB TTL — data is automatically expired, preventing unbounded storage energy consumption
- ✅ **SUS 4** — Right-sized traffic volume — the system processes the minimum viable number of requests to achieve its purpose

---

## Remediation Roadmap

Prioritised by risk level and implementation effort.

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#1e3a5f', 'primaryTextColor': '#c9d1d9', 'primaryBorderColor': '#4a7ab5', 'lineColor': '#58a6ff', 'edgeLabelBackground': '#0d1117'}}}%%

gantt
    title Remediation Roadmap
    dateFormat  YYYY-MM-DD
    axisFormat  %b %Y

    section High Risk (address now)
    OE-1  CloudWatch alarms for Lambda errors     :crit, 2026-05-17, 1d
    OE-2  Dead letter queue for EventBridge       :crit, 2026-05-17, 1d
    REL-1 SQS DLQ on async Lambda functions       :crit, 2026-05-17, 1d
    REL-2 Failure alerting via SNS email          :crit, 2026-05-18, 1d

    section Medium Risk (next iteration)
    PERF-1  Switch to ARM Graviton2               :active, 2026-05-24, 1d
    SUS-1   ARM reduces energy use 60pct          :active, 2026-05-24, 1d
    OE-3    Structured JSON logging               :2026-05-25, 2d
    OE-4    Unit tests with pytest                :2026-05-26, 3d
    OE-5    GitHub Actions CI/CD pipeline         :2026-05-29, 2d
    REL-3   Monday post-deploy verification       :2026-05-31, 1d

    section Low Risk (backlog)
    PERF-2  Lambda Power Tuning                   :2026-06-07, 2d
    PERF-4  Per-function timeout tuning           :2026-06-09, 1d
    OE-6    CloudWatch dashboard                  :2026-06-10, 1d
    SUS-2   Resource tagging                      :2026-06-11, 1d
    SEC-6   Narrow SES IAM to identity ARN        :2026-06-12, 1d
```

### Quick wins (under 30 minutes each)

These can all be done in a single `template.yaml` edit and `sam deploy`:

```yaml
# 1. Switch to ARM Graviton2 (PERF-1, SUS-1)
Globals:
  Function:
    Architectures: [arm64]

# 2. Per-function timeouts (PERF-4)
SendWeeklyEmailFunction:
  Timeout: 30
SendDailySMSFunction:
  Timeout: 15
ConfirmTaskFunction:
  Timeout: 10

# 3. Resource tags (SUS-2)
Globals:
  Function:
    Tags:
      Project: washingmachine-notifications
      Environment: production
      Owner: guy@dunite.uk
```

---

## Summary Scorecard

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#1e3a5f', 'primaryTextColor': '#c9d1d9', 'primaryBorderColor': '#4a7ab5', 'lineColor': '#58a6ff', 'edgeLabelBackground': '#0d1117'}}}%%

flowchart LR
    subgraph excellent ["⭐⭐⭐⭐⭐  Excellent"]
        S["Security\n5/5"]
        C["Cost Optimization\n5/5"]
    end

    subgraph good ["⭐⭐⭐⭐  Good"]
        P["Performance Efficiency\n4/5"]
    end

    subgraph improve ["⭐⭐⭐  Improve"]
        Su["Sustainability\n3/5\nARM switch pending"]
    end

    subgraph good2 ["⭐⭐⭐⭐  Good"]
        O["Operational Excellence\n4/5\nAlarms and DLQ resolved"]
        R["Reliability\n4/5\nDLQ and alerting resolved"]
    end

    style excellent fill:#0d2137,stroke:#1e7a1e
    style good fill:#0d2137,stroke:#7a7a1e
    style good2 fill:#0d2137,stroke:#7a7a1e
    style improve fill:#0d2137,stroke:#7a3a1e
```

| Total findings | 13 |
|---|---|
| 🔴 High Risk Issues | 0 (4 resolved) |
| 🟡 Medium Risk Issues | 7 |
| 🟢 Low Risk Issues | 5 (excluding accepted risks) |
| ✅ Resolved | 8 |
| Accepted (out of scope for risk profile) | 2 (single region, VPC) |

---

*Review conducted against the AWS Well-Architected Framework (2024 edition). Next review recommended after addressing the High Risk Issues, or when the architecture changes materially — whichever comes first. The filter, for its part, has no architectural concerns.*

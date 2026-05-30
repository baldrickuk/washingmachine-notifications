# Threat Model — washingmachine-notifications

> Security artefact produced by structured threat modelling (STRIDE + DREAD + MITRE ATT&CK Cloud Matrix).
> Version 2.0 — supersedes the v1.3 model. The v1.3 model described a CloudFormation +
> Secrets Manager + Twilio architecture that **no longer matches the deployed code**. The system
> is now Terraform/OpenTofu, uses **SSM Parameter Store (SecureString)** for secrets/PII, and
> **Pushover** as the optional push channel. This model is grounded in the actual `src/` and
> `terraform/` source as of the review date.

---

## 1. System Summary

### 1.1 Purpose
An AWS serverless system that sends a weekly reminder to clean a washing-machine filter, escalates
daily until confirmed, and records confirmation via a tokenised link. Four Lambda handlers in
`src/handlers/app.py`: `send_weekly_email`, `send_daily_sms`, `confirm_task`, `verify_delivery`.

### 1.2 Scope
In scope: Lambda (4 handlers), DynamoDB reminders table, SES, API Gateway HTTP API v2
(`GET /confirm`), CloudFront (GB geo whitelist), EventBridge schedules, SSM Parameter Store,
SQS DLQ, SNS alert topic, CloudWatch alarms, CloudTrail + S3 audit bucket, IAM role/policy.

Out of scope: the washing machine, the filter, the Pushover SaaS backend internals, the recipient's
email/device security posture (noted as an assumption), the AWS account control plane (root/MFA).

### 1.3 Data Classification

| Asset | Classification | Location |
|---|---|---|
| Recipient email address (`wife_email`) | PII | SSM SecureString `/stack/wife_email` |
| Recipient phone number (`wife_phone`) | PII | SSM SecureString `/stack/wife_phone` |
| Pushover app token | Credential | SSM SecureString `/stack/pushover_app_token` |
| Pushover user key | Credential | SSM SecureString `/stack/pushover_user_key` |
| Confirmation token (UUIDv4) | Secret (capability) | DynamoDB item attr `token`; emailed link; API query string |
| Task state (`status`, `sms_dates`, timestamps) | Internal / low-sensitivity | DynamoDB reminders table |
| `FROM_EMAIL` | Non-sensitive identifier | Lambda env var |

### 1.4 Threat Actors

| Actor | Capability | Motivation |
|---|---|---|
| External internet attacker | Anonymous HTTP to CloudFront and to the public `execute-api` origin URL; no creds | DoS, false confirmation, cost inflation, recon |
| Compromised dependency | Code execution inside Lambda at runtime (supply-chain) | Exfiltrate cached `_PARAMS` (creds + PII), pivot via IAM role |
| Malicious insider | Holds some AWS IAM principal in the account | Read PII/creds, tamper state, cover tracks |

---

## 2. Data Flow Diagram (text)

```
EXTERNAL ENTITIES
  (E1) Internet attacker / recipient browser  [UNTRUSTED]
  (E2) Pushover API  api.pushover.net          [EXTERNAL SaaS, TLS]
  (E3) Animal image APIs (cat/dog/fox/bunny/loremflickr) [EXTERNAL SaaS, TLS]
  (E4) Recipient mailbox + device              [UNTRUSTED, out of scope]

TRUST BOUNDARIES
  ==TB1== Internet  <->  CloudFront edge          (geo whitelist GB)
  ==TB2== Internet  <->  API Gateway origin URL   (execute-api.* — public hostname; X-Origin-Verify secret required)
  ==TB3== CloudFront <-> API Gateway origin        (AllViewerExceptHostHeader + X-Origin-Verify custom header injected)
  ==TB4== API Gateway <-> ConfirmTask Lambda       (resource policy: apigw principal, /*/*/confirm)
  ==TB5== EventBridge <-> scheduled Lambdas        (resource policy: events.amazonaws.com)
  ==TB6== Lambda execution role <-> AWS data plane (IAM policy: DDB, SES, SSM, KMS, SQS, SNS)
  ==TB7== Lambda runtime <-> external SaaS egress  (no egress filtering / no VPC)

PROCESSES
  (P1) send_weekly_email   handler app.send_weekly_email
  (P2) send_daily_sms      handler app.send_daily_sms
  (P3) confirm_task        handler app.confirm_task            [internet-reachable]
  (P4) verify_delivery     handler app.verify_delivery
  (P0) _load_parameters()  cold-start SSM fetch, caches _PARAMS in module memory

DATA STORES
  (D1) DynamoDB reminders table  (PK, status, token, sms_dates, ttl)  encrypted-at-rest (AWS owned)
  (D2) SSM Parameter Store SecureString x4 (KMS aws/ssm managed key)
  (D3) SQS DLQ  (14d retention; SSE NOT explicitly set)
  (D4) SNS alerts topic (encryption NOT set) -> email subscription
  (D5) S3 audit bucket (CloudTrail DynamoDB data events; no PAB/SSE/versioning block in IaC)
  (D6) CloudWatch Logs (structured JSON via _log/print)

PRIMARY FLOWS
  EventBridge(GMT+BST rules) --invoke--> P1 --putItem--> D1
                                         P1 --SES SendEmail--> E4 (confirm link w/ token)
                                         P1 --Pushover POST--> E2 (if enabled)
  EventBridge daily          --invoke--> P2 --get/update--> D1 ; P2 --Pushover--> E2
  EventBridge Monday         --invoke--> P4 --getItem--> D1 ; P4 --SNS Publish--> D4
  E1 browser --GET /confirm?week&token--> [TB1 CloudFront geo] --> [TB3] --> API GW --> [TB4] --> P3
     ALT: E1 --GET--> execute-api origin URL directly (TB2, bypasses CloudFront geo)
  P3 --getItem/updateItem--> D1 ; P3 --SES/Pushover congratulations--> E4/E2 ; P3 --fetch image--> E3
  P0 (all handlers cold start) --GetParameter WithDecryption--> D2 (KMS Decrypt)
  P1/P2 on failure after retries --> D3 (DLQ)
  CloudTrail --DynamoDB data events--> D5
```

Key structural observation: **TB2 is the weakest boundary.** `outputs.tf` exposes
`confirm_api_url` and explicitly documents it as *"API Gateway origin URL (direct — bypasses geo
restriction)"*. The `execute-api` endpoint has no geo restriction, no WAF, no shared-secret header
check against CloudFront, so the entire CloudFront GB whitelist is an advisory speed-bump, not a
control.

---

## 3. Threat Register (sorted by DREAD descending)

DREAD scored on the raw threat (1–10 each: Damage, Reproducibility, Exploitability, Affected users,
Discoverability), averaged. Existing controls are noted separately and do **not** reduce the raw
score. Priority: CRITICAL ≥8.0, HIGH 6.0–7.9, MEDIUM 4.0–5.9, LOW <4.0.

---

### T01 — Geo-restriction bypass via direct API Gateway origin  ·  DREAD 7.8  ·  ✅ MITIGATED
- **Component:** API Gateway HTTP API (`api_gateway.tf`), CloudFront (`cloudfront.tf`), `outputs.tf:confirm_api_url`
- **STRIDE:** Spoofing, Tampering (boundary bypass), Denial of Service
- **Attack:** The `https://{api_id}.execute-api.eu-west-2.amazonaws.com/confirm?week=…&token=…`
  origin is publicly reachable from any country. CloudFront's `geo_restriction whitelist=["GB"]`
  only governs the CloudFront distribution; it does not protect the origin.
- **Attack path:** Recon origin id (TF output, DNS, email link analysis, or `execute-api` enumeration) → `curl` origin `/confirm` from any geography → reach `ConfirmTask` with no geo or CloudFront throttle in front.
- **Pre-conditions:** Knowledge of the `execute-api` hostname (low bar — appears in TF outputs, possibly logs).
- **Impact:** The advertised GB geo control and the CloudFront layer are nullified; attacker can brute/replay tokens and flood the Lambda from anywhere, defeating a documented security control.
- **Existing controls:** API GW stage throttle 5 req/s burst 10; UUIDv4 token required.
- **Mitigation applied (M01):** CloudFront now injects `X-Origin-Verify: <secret>` on every origin request (`cloudfront.tf:custom_header`). `confirm_task` uses `hmac.compare_digest` to validate the header — requests missing or mismatching the secret are rejected 403 before any business logic executes. Secret stored in SSM SecureString; `ORIGIN_VERIFY_ENABLED = bool(token)` so deployments without the variable are unaffected.
- **Residual risk:** Low — hostname still public (UUIDv4 token remains the last line of defence); secret rotation requires SSM update + Lambda cold start.
- **MITRE ATT&CK:** T1133 External Remote Services; T1090 Proxy (geo evasion); T1499 Endpoint DoS.

### T02 — Unhandled `date.fromisoformat(week)` raises on malformed input  ·  DREAD 7.2  ·  HIGH
- **Component:** `confirm_task`, `src/handlers/app.py:541` `pk = _week_pk(date.fromisoformat(week), is_test)`
- **STRIDE:** Denial of Service, Tampering (input validation)
- **Attack:** `confirm_task` validates only that `week` and `token` are present (line 538), then passes
  `week` straight into `date.fromisoformat(week)`. Any non-ISO value (`week=x`, `week=2026-13-99`,
  `week=../`) raises `ValueError`, which is uncaught → Lambda errors → API Gateway returns 500/502.
- **Attack path:** `GET /confirm?week=AAAA&token=AAAA` (via origin, see T01) → unhandled exception → 5xx.
- **Pre-conditions:** Reachable endpoint (trivially, via T01 origin or CloudFront from GB).
- **Impact:** Reliable error generation; trips the `confirm-task-errors` CloudWatch alarm (threshold ≥1) on demand, causing alert fatigue / masking real incidents; consumes Lambda error budget; cheap repeatable fault injection.
- **Existing controls:** API GW throttle limits rate; alarm exists (which the attacker abuses).
- **MITRE ATT&CK:** T1499.004 Application/Endpoint DoS; T1565 Data Manipulation (via alarm noise).
- **Note:** Also no `try/except` around `date.fromisoformat` — contrast with the careful guarding elsewhere.

### T03 — Over-broad `kms:Decrypt` on `key/*` wildcard  ·  DREAD 6.6  ·  HIGH
- **Component:** `terraform/iam.tf:44-55` SSMParameters statement, resource `arn:aws:kms:…:key/*`
- **STRIDE:** Elevation of Privilege, Information Disclosure
- **Attack:** The Lambda role is granted `kms:Decrypt` against **every KMS key in the account/region**
  (`key/*`), not just the key encrypting the four SSM SecureStrings. A compromised dependency (or any
  code path coerced to call KMS) inheriting this role can decrypt ciphertext protected by unrelated
  keys elsewhere in the account, far beyond this app's data.
- **Attack path:** Supply-chain compromise of `boto3`/transitive dep, or SSRF-to-metadata → assume role context → `kms:Decrypt` arbitrary ciphertext from other workloads sharing the account.
- **Pre-conditions:** Code execution under the Lambda role (T06), and presence of other KMS-protected data in the account.
- **Impact:** Lateral movement / cross-workload secret decryption; violates least privilege.
- **Existing controls:** None scoping the key; relies on no other code calling KMS.
- **MITRE ATT&CK:** T1078.004 Valid Accounts: Cloud; T1552 Unsecured Credentials; T1530 Data from Cloud Storage.

### T04 — Over-broad `ses:SendEmail` on `identity/*` wildcard  ·  DREAD 6.4  ·  HIGH
- **Component:** `terraform/iam.tf:35-42` SES statement, resource `…:identity/*`
- **STRIDE:** Spoofing, Elevation of Privilege
- **Attack:** The role may `ses:SendEmail` from **any verified identity in the account**, not just
  `FROM_EMAIL`. A compromised dependency can send arbitrary mail (phishing, spam) as any verified
  domain/address, abusing the account's SES reputation and sending quota.
- **Attack path:** Code execution under Lambda role (T06) → `ses:SendEmail` with attacker-chosen Source/Destination/body.
- **Pre-conditions:** Code execution under role; SES in production mode (README requests it).
- **Impact:** Brand/domain spoofing, deliverability/reputation damage, potential SES account suspension, phishing launchpad.
- **Existing controls:** None on Source; SES sandbox would limit recipients but README instructs requesting production access.
- **MITRE ATT&CK:** T1078.004 Valid Accounts: Cloud; T1585/T1586 spoofed messaging; T1496 Resource Hijacking (quota).

### T05 — `confirm_task` has no reserved concurrency — DoS / cost via origin  ·  DREAD 6.2  ·  HIGH
- **Component:** `terraform/lambda.tf:94-110` (no `reserved_concurrent_executions`), reachable via T01/CloudFront
- **STRIDE:** Denial of Service
- **Attack:** API GW throttle (5 req/s burst 10) caps request rate, but there is no Lambda reserved
  concurrency floor/ceiling. Combined with T01 (origin bypass) and T02 (forced errors), sustained
  traffic drives invocations + each does a DynamoDB `GetItem` and (on the error path) Lambda retries,
  burning account-wide concurrency, DynamoDB on-demand RCUs, and CloudWatch costs. A single public
  function can starve the other three handlers of account concurrency.
- **Attack path:** Distributed `GET /confirm` to origin (T01) at/above throttle from many sources → exhaust shared account concurrency / inflate cost.
- **Pre-conditions:** Reachable endpoint (T01).
- **Impact:** Availability loss for confirmation + sibling Lambdas; bill inflation (DynamoDB, Lambda, CloudWatch, CloudFront egress).
- **Existing controls:** API GW stage throttle; PAY_PER_REQUEST DynamoDB (no provisioned cap = cost, not outage).
- **MITRE ATT&CK:** T1499 Endpoint DoS; T1496 Resource Hijacking (cost).

### T06 — Compromised dependency exfiltrates cached SSM creds + PII  ·  DREAD 5.8  ·  MEDIUM
- **Component:** `_load_parameters()` / module-global `_PARAMS` (`app.py:24-51`), TB7 egress
- **STRIDE:** Information Disclosure, Elevation of Privilege
- **Attack:** All four secrets/PII values are fetched at cold start and held in process memory
  (`_PARAMS`, `WIFE_EMAIL`, `WIFE_PHONE`, `PUSHOVER_*`). Lambda has unrestricted outbound internet
  (no VPC/egress filtering, and the code already makes arbitrary outbound HTTPS to Pushover and
  animal APIs). A malicious/compromised pip dependency reads these globals and POSTs them to an
  attacker endpoint, indistinguishable from legitimate egress.
- **Attack path:** Poisoned dependency in `requirements.txt` build (`build.sh` pip install) → runs in Lambda → reads `_PARAMS` → exfiltrates over HTTPS; also leverages role for T03/T04.
- **Pre-conditions:** Supply-chain compromise; no dependency pinning/hash verification observed.
- **Impact:** Loss of Pushover credentials + recipient PII; pivot to broad KMS/SES via T03/T04.
- **Existing controls:** SecureString at rest; minimal dependency surface (boto3 + stdlib). No egress controls, no SBOM, no hash pinning.
- **MITRE ATT&CK:** T1195.001 Supply Chain Compromise; T1552 Unsecured Credentials; T1567 Exfiltration over Web Service.

### T07 — Confirmation link forwarding / inbox access → false confirmation  ·  DREAD 5.8  ·  MEDIUM
- **Component:** `confirm_task` token model; SES email body (`_email_html`)
- **STRIDE:** Spoofing (of the human action), Repudiation
- **Attack:** The token is a bearer capability with no binding to the recipient. Anyone who obtains the
  link (forwarded email, shared inbox, mailbox compromise, shoulder-surf) can confirm the task,
  recording it as done when it is not, silencing reminders.
- **Attack path:** Obtain link from E4 mailbox → click from any GB origin (or origin via T01) → state set CONFIRMED.
- **Pre-conditions:** Access to the confirmation link.
- **Impact:** False "filter cleaned" record; defeats the system's sole purpose for that week (domestic, low security impact).
- **Existing controls:** HTTPS; idempotent re-click; 30-day TTL; GB geo (advisory, bypassable).
- **MITRE ATT&CK:** T1539 Steal Web Session Cookie (analogue: steal bearer link); T1534 Internal Spearphishing (forwarding).

### T08 — Non-constant-time token comparison (timing side channel)  ·  DREAD 4.4  ·  MEDIUM
- **Component:** `confirm_task`, `app.py:552` `if item["token"] != token:`
- **STRIDE:** Information Disclosure
- **Attack:** Token equality uses Python `!=`, which short-circuits on first differing byte. In theory a
  timing oracle leaks prefix-correctness. Practically near-infeasible: the attacker must already know
  the `week` PK to fetch the item, UUIDv4 space is 122-bit, network jitter dwarfs the signal, and API
  GW throttling limits sampling.
- **Attack path:** High-volume timed `/confirm` requests against a known `week`, statistically inferring token bytes.
- **Pre-conditions:** Known valid `week`; enormous request budget; throttle defeats it.
- **Impact:** Theoretical token recovery → false confirmation.
- **Existing controls:** Throttle; huge keyspace; comparison only reached after PK is known.
- **MITRE ATT&CK:** T1110 Brute Force (timing-assisted).

### T09 — SQS DLQ has no explicit SSE-KMS; event payloads at rest  ·  DREAD 4.4  ·  MEDIUM
- **Component:** `terraform/main.tf:71-74` `aws_sqs_queue.dlq` (no `kms_master_key_id` / `sqs_managed_sse_enabled`)
- **STRIDE:** Information Disclosure
- **Attack:** Failed Lambda invocation events land in the DLQ. EventBridge inputs are low-sensitivity,
  but failed `confirm_task`-style payloads/context could include query parameters (week/token). Without
  explicit SSE-KMS, encryption relies on the SQS default; an account principal with `sqs:ReceiveMessage`
  reads payloads. (Modern SQS defaults to SSE-SQS, but it is not pinned in IaC and not a customer-managed key.)
- **Attack path:** Insider or compromised principal with SQS read on the DLQ → read retained event bodies.
- **Pre-conditions:** SQS read permission on the DLQ.
- **Impact:** Possible exposure of tokens/PK in failed events (14-day retention window).
- **Existing controls:** IAM (Lambda role has only SendMessage); default SQS encryption.
- **MITRE ATT&CK:** T1530 Data from Cloud Storage Object.

### T10 — SNS alert topic unencrypted; PK/operational detail in alert email  ·  DREAD 4.2  ·  MEDIUM
- **Component:** `terraform/main.tf:80-88` `aws_sns_topic.alerts` (no `kms_master_key_id`); `verify_delivery` publishes `pk`
- **STRIDE:** Information Disclosure, Repudiation
- **Attack:** `verify_delivery` publishes the DynamoDB `pk` (`WEEK#YYYY-MM-DD`) to SNS, delivered by
  email to `alert_email` in cleartext. The topic has no KMS encryption; in-account principals with
  `sns:Subscribe`/topic access, or anyone able to add a subscription, can intercept operational metadata.
- **Attack path:** Insider subscribes a rogue endpoint to the topic (no topic policy restricting Subscribe) → receives alerts; or reads cleartext email.
- **Pre-conditions:** Account access to SNS, or access to the alert mailbox.
- **Impact:** Leak of operational status/timing; low data sensitivity.
- **Existing controls:** None on topic encryption or subscription policy.
- **MITRE ATT&CK:** T1530 Data from Cloud Storage; T1530/T1567 interception.

### T11 — S3 audit bucket missing public-access-block / SSE / versioning controls  ·  DREAD 4.2  ·  MEDIUM
- **Component:** `terraform/monitoring.tf:263-312` `aws_s3_bucket.trail` (+ bucket policy, lifecycle only)
- **STRIDE:** Information Disclosure, Tampering, Repudiation
- **Attack:** The CloudTrail audit bucket defines only a lifecycle rule and a bucket policy. There is no
  `aws_s3_bucket_public_access_block`, no `aws_s3_bucket_server_side_encryption_configuration`, and no
  versioning/object-lock. CloudTrail logs (the audit trail itself) could be deleted or tampered by a
  sufficiently privileged insider, and lack of PAB risks misconfiguration-driven exposure of the audit
  trail (which records DynamoDB token access).
- **Attack path:** Insider with `s3:DeleteObject`/`PutBucketPolicy` tampers/erases trail; or future ACL/policy mistake exposes logs publicly.
- **Pre-conditions:** Account access; absence of guardrails (no Object Lock).
- **Impact:** Audit log integrity loss (anti-forensics) and potential disclosure of access records.
- **Existing controls:** S3 default SSE-S3 (AWS-managed) applies even if unspecified; account-level BPA may exist but is not asserted in IaC.
- **MITRE ATT&CK:** T1562.008 Impair Defenses: Disable/Modify Cloud Logs; T1485 Data Destruction.

### T12 — Sender-domain email spoofing (SPF/DKIM/DMARC not enforced in scope)  ·  DREAD 4.2  ·  MEDIUM
- **Component:** SES sending (`_send_email`, `FROM_EMAIL`); DNS for the sender domain (out of IaC)
- **STRIDE:** Spoofing
- **Attack:** A third party spoofs the `FROM_EMAIL` domain to send fake "filter reminder / confirm here"
  emails containing an attacker link, unless SPF, DKIM, and a `p=reject` DMARC policy are published and
  enforced for the sender domain. None of this is managed in the reviewed IaC.
- **Attack path:** Attacker sends spoofed email with malicious confirm-style link → recipient clicks attacker URL.
- **Pre-conditions:** Sender domain lacks enforced DMARC; recipient trusts the look-alike.
- **Impact:** Phishing of the recipient; reputational; mostly low real-world value for this app.
- **Existing controls:** SES DKIM-signs verified identities (if DNS records published — not verifiable here).
- **MITRE ATT&CK:** T1656 Impersonation; T1566 Phishing.

### T13 — CloudFront lacks WAF, access logging, and viewer min-TLS hardening  ·  DREAD 4.2  ·  MEDIUM
- **Component:** `terraform/cloudfront.tf` (no `web_acl_id`, no `logging_config`, default cert, no `minimum_protocol_version`)
- **STRIDE:** Denial of Service, Repudiation, Information Disclosure
- **Attack:** No WAF means no L7 rate-based or bot rules at the edge; no access logging means reduced
  forensic visibility for edge abuse; the default CloudFront certificate sets no explicit modern
  minimum viewer TLS version. Combined with T01, the edge offers little protection.
- **Attack path:** L7 flood / scripted abuse at the edge with no WAF mitigation and no edge logs to investigate.
- **Pre-conditions:** Public distribution (always).
- **Impact:** Weaker DoS resilience and forensics at the edge.
- **Existing controls:** `redirect-to-https`; geo whitelist (bypassable via origin).
- **MITRE ATT&CK:** T1499 Endpoint DoS; T1562.008 Impair Defenses (no logs).

### T14 — Malicious insider reads SSM SecureString PII/credentials  ·  DREAD 4.2  ·  MEDIUM
- **Component:** SSM Parameter Store params (`main.tf:27-65`), AWS-managed KMS key (`aws/ssm`)
- **STRIDE:** Information Disclosure
- **Attack:** Parameters use SecureString with the AWS-managed `aws/ssm` key. Any account principal with
  `ssm:GetParameter` + the broad `kms:Decrypt` (T03 style) on the managed key can read recipient PII and
  Pushover credentials. With an AWS-managed key there is no per-key policy to constrain decryptors beyond IAM.
- **Attack path:** Insider with SSM read + KMS decrypt on `aws/ssm` → `get-parameter --with-decryption`.
- **Pre-conditions:** IAM principal with SSM/KMS read.
- **Impact:** Disclosure of PII + credentials.
- **Existing controls:** SecureString; CloudTrail management events (note: trail here logs DynamoDB data events only — SSM reads rely on default management-event logging if a separate trail exists).
- **MITRE ATT&CK:** T1552.001 Credentials in Files/Stores; T1078.004 Valid Accounts: Cloud.

### T15 — Outbound SSRF / tainted URL in `_fetch_animal_image`  ·  DREAD 3.4  ·  LOW
- **Component:** `_fetch_animal_image` (`app.py:443-482`), `ANIMAL_TYPE` env (config-controlled)
- **STRIDE:** Information Disclosure (egress), Tampering
- **Attack:** `animal` is interpolated into `https://loremflickr.com/640/480/{search_term}/all`. The value
  derives from `ANIMAL_TYPE` (operator-set, not user-supplied), so practical risk is low. If a future
  change ever routed user input into `animal`, this becomes an SSRF/URL-injection sink. The handler also
  makes unrestricted outbound calls (TB7) with no allowlist.
- **Attack path:** Operator misconfig or future input flow sets `animal` to a crafted value → request to attacker-chosen host.
- **Pre-conditions:** Control over `ANIMAL_TYPE` (operator) — currently not attacker-controlled.
- **Impact:** Low today; latent SSRF if input source changes.
- **Existing controls:** Value is operator config; broad exception catch; 5s timeout; returns "" on error.
- **MITRE ATT&CK:** T1190 Exploit Public-Facing Application (SSRF class).

### T16 — DynamoDB record tampering via account compromise  ·  DREAD 3.4  ·  LOW
- **Component:** DynamoDB reminders table; Lambda role DDB write actions (`iam.tf:22-33`)
- **STRIDE:** Tampering
- **Attack:** A principal with DynamoDB write (the Lambda role or an insider) can flip `status` to
  CONFIRMED or rewrite `token`, faking confirmation or breaking links. No public write path exists.
- **Attack path:** Compromised role (T06) or insider → `UpdateItem` on the table.
- **Pre-conditions:** AWS write access to the table.
- **Impact:** State integrity loss for the reminder cycle (low severity).
- **Existing controls:** No public DDB endpoint; CloudTrail DynamoDB data events record the change.
- **MITRE ATT&CK:** T1565.001 Stored Data Manipulation.

### T17 — Confirmation repudiation — no IP/User-Agent captured  ·  DREAD 3.2  ·  LOW
- **Component:** `confirm_task` logging (`_log("Task confirmed"…)`)
- **STRIDE:** Repudiation
- **Attack:** Only `confirmed_at` and a log line are recorded; no source IP or User-Agent, so the actor
  who confirmed cannot be attributed. Acceptable for this domestic use case.
- **Attack path:** Recipient (or link holder) confirms, later denies doing so; no attributable evidence.
- **Pre-conditions:** Any successful confirmation.
- **Impact:** Weak non-repudiation (trivial real-world impact here).
- **Existing controls:** Timestamp; CloudWatch invocation logs.
- **MITRE ATT&CK:** T1070 Indicator Removal (analogue: lack of attributable record).

### T18 — Test-mode EventBridge rule / test path abuse  ·  DREAD 3.0  ·  LOW
- **Component:** `eventbridge.tf:95-114` `test_sms` rule (DISABLED by default); `is_test` branches in code
- **STRIDE:** Tampering, Elevation of Privilege (operational)
- **Attack:** An insider with `events:EnableRule` re-enables the disabled 10-minute test rule, or invokes
  handlers with `{"test": true}` to bypass the DST/hour guards and drive `TEST#` records and Pushover
  sends at high frequency (notification spam / minor cost).
- **Attack path:** Insider enables rule / invokes Lambda with test payload → rapid test cycles, Pushover spam.
- **Pre-conditions:** AWS access to EventBridge/Lambda invoke.
- **Impact:** Notification spam to recipient; minor cost; isolated to TEST# keys.
- **Existing controls:** Rule disabled by default; TEST# keys isolate from prod state; 10-min test throttle in code.
- **MITRE ATT&CK:** T1648 Serverless Execution (abuse of scheduled trigger).

### T19 — EventBridge event spoofing of scheduled handlers  ·  DREAD 3.0  ·  LOW
- **Component:** Lambda resource policies for `events.amazonaws.com` (`eventbridge.tf` permissions)
- **STRIDE:** Spoofing
- **Attack:** Forged "scheduled" invocations of the handlers. The resource-based policies restrict the
  principal to `events.amazonaws.com` and `source_arn` to this account's specific rule ARNs, so an
  external party cannot forge them; only an in-account principal able to invoke Lambda directly could
  simulate events (overlaps T18). DST/hour guards further limit effect in prod.
- **Attack path:** In-account `lambda:InvokeFunction` with a crafted event → handler runs (guards mostly reject off-hours).
- **Pre-conditions:** In-account invoke permission.
- **Impact:** Minimal — guards and idempotency limit damage.
- **Existing controls:** `source_arn`-scoped permissions; London-hour DST guard; idempotent records.
- **MITRE ATT&CK:** T1648 Serverless Execution.

---

## 4. Risk Summary

### 4.1 Counts by severity

| Severity | Count | Threat IDs |
|---|---|---|
| CRITICAL (≥8.0) | 0 | — |
| HIGH (6.0–7.9) | 5 | T01, T02, T03, T04, T05 |
| MEDIUM (4.0–5.9) | 9 | T06, T07, T08, T09, T10, T11, T12, T13, T14 |
| LOW (<4.0) | 5 | T15, T16, T17, T18, T19 |
| **Total** | **19** | |

### 4.2 Counts by STRIDE category (primary + secondary tags)

| STRIDE | Count | Threat IDs |
|---|---|---|
| Spoofing (S) | 6 | T01, T04, T07, T12, T18 implied, T19 |
| Tampering (T) | 6 | T01, T02, T11, T15, T16, T18 |
| Repudiation (R) | 4 | T07, T10, T11, T17 |
| Information Disclosure (I) | 8 | T03, T06, T09, T10, T11, T13, T14, T15 |
| Denial of Service (D) | 5 | T01, T02, T05, T13, (T18) |
| Elevation of Privilege (E) | 4 | T03, T04, T06, T18 |

---

## 5. Mitigations Plan

### 5.1 CRITICAL / HIGH — full detail

#### M01 → mitigates T01 (geo bypass via origin) — ✅ IMPLEMENTED
- **Control type:** Preventive (network/boundary)
- **Description:** CloudFront injects `X-Origin-Verify: <secret>` on every origin request; `confirm_task` rejects requests without the correct header with 403.
- **AWS service:** CloudFront (custom origin header) + Lambda (`confirm_task`)
- **Implementation:** `cloudfront.tf` `origin.custom_header { name = "X-Origin-Verify" value = var.origin_verify_token }`. In `app.py` `confirm_task`: `hmac.compare_digest(presented, ORIGIN_VERIFY_TOKEN)` — timing-safe comparison. Secret in SSM SecureString `/washingmachine-notifications/origin_verify_token`. `ORIGIN_VERIFY_ENABLED = bool(token)` so empty token disables the check.
- **Effort:** Medium (completed)
- **Residual risk:** Low — execute-api hostname still public; secret rotation needed if leaked. Geo restriction remains advisory rather than enforced at the network layer.

#### M02 → mitigates T02 (`fromisoformat` crash)
- **Control type:** Preventive (input validation)
- **Description:** Validate/parse `week` defensively and return a clean 400 instead of throwing.
- **AWS service:** Lambda (code)
- **Implementation:** Wrap `date.fromisoformat(week)` in `confirm_task` in `try/except ValueError` and return `_html_response(400, _error_page(...))`; add a regex/length check on `token` (UUID format) before lookup. (Code change in `src/handlers/app.py`; covered by unit tests.)
- **Effort:** Low
- **Residual risk:** Very low.

#### M03 → mitigates T03 (kms:Decrypt wildcard)
- **Control type:** Preventive (least privilege)
- **Description:** Scope `kms:Decrypt` to only the key that encrypts the SSM SecureStrings.
- **AWS service:** IAM + KMS
- **Implementation:** Create a customer-managed KMS key for the SSM parameters (set `key_id` on each `aws_ssm_parameter`), then in `iam.tf` replace `arn:…:key/*` with that specific key ARN, optionally gated by `kms:ViaService = ssm.<region>.amazonaws.com` condition. Split the SSM statement so `ssm:GetParameter` and `kms:Decrypt` carry distinct, tight resources.
- **Effort:** Medium
- **Residual risk:** Low — confined to the app's own SSM key.

#### M04 → mitigates T04 (ses:SendEmail wildcard)
- **Control type:** Preventive (least privilege)
- **Description:** Restrict sending to the single verified `FROM_EMAIL` identity.
- **AWS service:** IAM + SES
- **Implementation:** In `iam.tf` SES statement, replace `identity/*` with `identity/${var.from_email}` (or the verified domain identity ARN), and add a condition `ses:FromAddress = var.from_email`. Consider an SES sending authorization policy on the identity.
- **Effort:** Low
- **Residual risk:** Low.

#### M05 → mitigates T05 (no reserved concurrency)
- **Control type:** Preventive (resource control)
- **Description:** Cap and isolate `confirm_task` concurrency to protect siblings and bound cost.
- **AWS service:** Lambda (+ DynamoDB, WAF)
- **Implementation:** Set `reserved_concurrent_executions` (e.g. 5–10) on `aws_lambda_function.confirm_task` in `lambda.tf`; add an AWS Budgets alarm; combine with M01 (origin lockdown) and rate-based WAF. Optionally set a DynamoDB on-demand max via application-level caching of negative lookups.
- **Effort:** Low
- **Residual risk:** Low — bounded blast radius; legitimate single-user traffic well within cap.

### 5.2 MEDIUM / LOW — recommended controls (summary)

| ID | Threat | Recommended control |
|---|---|---|
| T06 | Dependency exfil of creds/PII | Pin + hash-lock deps (`pip --require-hashes`), generate SBOM, enable CodeArtifact/Dependabot, consider Lambda in VPC with egress allowlist to `api.pushover.net`; least-privilege role (M03/M04) limits blast radius. |
| T07 | Link forwarding / false confirm | Accept as residual (domestic). If hardening: shorten TTL, one-time token invalidated on first use, optional second-factor tap. |
| T08 | Timing comparison | Use `hmac.compare_digest(item["token"], token)` in `confirm_task`. Low effort. |
| T09 | DLQ encryption | Set `sqs_managed_sse_enabled = true` (or CMK `kms_master_key_id`) on `aws_sqs_queue.dlq`. |
| T10 | SNS encryption / subscribe policy | Set `kms_master_key_id` on `aws_sns_topic.alerts`; add a topic policy restricting `sns:Subscribe`; avoid embedding `pk` in alert text. |
| T11 | Audit bucket hardening | Add `aws_s3_bucket_public_access_block`, SSE config (CMK), versioning, and Object Lock (governance) for the trail bucket; enable log-file validation on the CloudTrail. |
| T12 | Email spoofing | Publish SPF + DKIM + `DMARC p=reject` for the sender domain; verify in SES. |
| T13 | CloudFront hardening | Attach `web_acl_id` (WAF rate-based + bot rules), `logging_config` to an S3 log bucket, and explicit modern viewer min-TLS (custom cert + `minimum_protocol_version = TLSv1.2_2021`). |
| T14 | Insider SSM read | Use a CMK with a tight key policy (ties to M03); ensure a management-events CloudTrail captures `ssm:GetParameter`; alert on bulk parameter reads. |
| T15 | SSRF latent | Keep `animal` operator-only; if ever user-driven, allowlist hosts; consider validating the final image URL host. |
| T16 | DDB tampering | Least privilege (M03/M04) + existing CloudTrail data events; alert on `UpdateItem` outside expected handlers. |
| T17 | Confirmation repudiation | Log source IP + User-Agent from the API GW v2 request context in `confirm_task`. |
| T18 | Test-rule abuse | Remove `test_sms` rule from prod stack post-testing; restrict `events:EnableRule`/`lambda:InvokeFunction` via SCP/permission boundary. |
| T19 | EventBridge spoofing | Already well-scoped (`source_arn`); maintain permission boundaries limiting direct `lambda:InvokeFunction`. |

---

## 6. Assumptions & Exclusions

**Assumptions**
- AWS account root has MFA; administrative IAM is tightly controlled and out of scope.
- `terraform.tfvars` is gitignored and never committed.
- A separate organisation/account CloudTrail captures management events (the app trail logs only
  DynamoDB **data** events).
- SES is or will be in production sending mode (per README), widening T04 impact.
- Pushover SaaS and the third-party animal-image APIs are trusted to the extent of TLS transport.
- The recipient's mailbox/device security is the recipient's responsibility (governs T07).

**Exclusions**
- The washing machine, filter, and the emotional state of either.
- AWS-managed control-plane vulnerabilities.
- Twilio/WhatsApp channels described in `docs/architecture.md` and the prior threat model — these are
  **not present in the current code** (`app.py` implements SES + Pushover only). Treated as
  documentation drift, not live attack surface.

---

## 7. Recommended Next Steps

**Detection rules (CloudWatch Logs Insights / metric filters)**
- Alarm on `confirm_task` 5xx / `ValueError` log spikes (detects T02 abuse) separately from the
  existing error-count alarm so attacker-induced errors are distinguishable from outages.
- Metric filter on `"Invalid token presented"` log line (`app.py:553`) to detect token-guessing (T01/T08).
- CloudTrail alert on `kms:Decrypt` with keys other than the SSM key, and on `ssm:GetParameter` bulk reads (T03/T14).
- CloudTrail/WAF alert on direct `execute-api` hits not carrying the CloudFront origin header (T01).

**Pentest scope**
- Black-box: attempt origin-direct access to `execute-api` from a non-GB IP; fuzz `week`/`token`;
  attempt forced 5xx; concurrency exhaustion test against `confirm_task`.
- Grey-box: assume the Lambda role and enumerate reachable KMS keys and SES identities (validate
  M03/M04 scoping).

**Adversary emulation (MITRE ATT&CK Cloud)**
- Emulate T1195.001 supply-chain (inject a benign exfil dependency in a test build) to validate egress
  controls and least-privilege containment (T06).
- Emulate T1562.008 (attempt to delete/modify the CloudTrail S3 objects) to validate T11 hardening.

**Re-review triggers**
- Any change introducing user-controlled input into `animal`/image fetching (re-rate T15).
- Adding Twilio/WhatsApp channels (re-introduces external credential surface).
- Enabling SES production mode (raises T04 impact).
- Moving Lambda into a VPC or adding new outbound integrations (re-rate T06/TB7).
- Annual review, or on material architecture change.

---

*Threat model version 2.0. 19 threats: 0 critical, 5 high, 9 medium, 5 low. Grounded in the live
Terraform + `app.py` source. Companion machine-readable artefact: `docs/threat-model.tc.json`
(AWS Threat Composer schema v1).*

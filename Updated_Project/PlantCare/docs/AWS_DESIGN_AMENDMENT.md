# AWS adaptation of master v2.0

The approved hosting change replaces localhost SQL and Flask with AWS services. The message schemas, timing thresholds, deterministic rules, watering safeguards, no-ML requirement and live/simulation separation remain governing requirements.

| Master behavior | AWS implementation |
|---|---|
| One backend state owner | One FIFO message group per mode; worker batch size 1 |
| Durable atomic state/journal | DynamoDB conditional version plus transactional puts |
| Journal before publish | Transaction includes command and outbox; publish only after commit |
| Retry semantics | At-least-once delivery; exact command IDs and device dedupe prevent repeated actuation |
| Independent stale evaluator | Scheduled Lambda emits ticks every 2 seconds during its bounded 60-second execution |
| History access | Time-oriented sort keys; strongly consistent pages of at most 2,000 rows; dashboard total cap 400,000 |
| Localhost browser trust | HTTPS API Gateway JWT authorizer with explicit issuer and audience; no public mutation route |
| Local privileged profile reload | IAM-authorized operator queues the fixed mode-specific JSON; no browser-selected file path |
| Backend restart | Change `BackendGeneration` on operator restart/redeployment; logical durable owner resumes across ordinary Lambda cold starts |
| Startup before first sample | `source` and `sample_ts` are null with stale/unknown; explicit schema-1 startup extension |
| Scenario day/night control | Optional boolean `demo_daylight` accepted only in simulation profile |

These are implementation amendments, not evidence that cloud acceptance passed. Cold-start restoration is intentional: treating every Lambda instance creation as a full backend restart would continually disarm a serverless system. An explicit generation change produces disarm/fault semantics, including conservative cooldown.

FIFO serialization covers the current single plant per mode. Adding plants requires a new group/partition mapping and corresponding authorization review. The SDK transactions use IAM `dynamodb:PutItem` for transactional puts, not a fictitious `dynamodb:TransactWriteItems` IAM action. AWS IoT's direct SQS action does not support FIFO queues, so an ingress Lambda bridges IoT to FIFO.

Profile evidence flags are attestations by the team after actual measurements; a boolean cannot itself prove a physical experiment occurred. Raw endpoints/noise/count and dose/timing validation reject obvious inconsistent settings but do not certify a pump installation.

Reference: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis-iam.html
Reference: https://docs.aws.amazon.com/iot/latest/developerguide/sqs-rule-action.html

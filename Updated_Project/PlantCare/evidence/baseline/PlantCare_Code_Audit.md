# Plant Care Companion: code and specification audit

**Review date:** 12 November 2026  
**Verdict:** Development starter; does not yet meet the master specification. Suitable for continuing isolated sensor/cloud smoke testing, not for declaring full-system or watering acceptance.

## 1. Scope and governing requirements

Reviewed the supplied `PlantCare_Team3_XIAO_Cloud.zip` and both `Plant Care Companion — Master Implementation Doc v2.0` PDFs (suffixes `-1` and `-2`). The PDFs are byte-for-byte identical, with SHA-256 `4293813726827c049686a7851c465459ca5f0a10b5e57bc33e437960aa76fd50`.

The user's AWS change supersedes the laptop/SQLite architecture. Therefore, absence of SQLite, a laptop worker, or Flask specifically is **not** counted as a defect. Their required behaviors—durable history, ordered condition state, command journaling, idempotency, freshness, and dashboard access—still need AWS equivalents. A cloud dashboard also needs an explicit authentication/authorization design replacing the document's localhost trust boundary.

The only explicitly approved change in this request was AWS hosting/storage. The master document says **no ML** (§1), but the ZIP describes a separate ML decision and enables a synthetic classifier for simulation. This is a requirements conflict, not an assumed new requirement. Update the canonical spec if the team has separately approved ML; AWS hosting alone does not authorize changing the condition rules.

Original application files were not modified. All findings concern the supplied snapshot, not code that might exist in another teammate's repository.

## 2. Executed checks and their limits

| Check | Result | What it establishes |
|---|---|---|
| Supplied unit tests | 9 passed | Existing tests pass, including a model smoke test and mocked cloud route |
| Additional spec/robustness suite | 80 tests: 35 passed, 45 assertion failures, 0 errors | Reproducible validation, analysis, persistence, ordering, and logger gaps |
| Python compileall | Passed | Python syntax compiles; does not validate firmware or cloud deployment |
| AWS SAM/CloudFormation template static lint | Passed: cfn-lint 1.60.0, exit 0, no diagnostics | Static template check only; no SAM container build or deployment |
| README `python aws/local_invoke.py` | Failed: `ModuleNotFoundError: No module named 'aws'` | Documented startup command is broken in a clean shell |
| README `python ml/train_example.py` | Same import failure | Documented training command is broken in a clean shell |
| `python -m aws.local_invoke` | Passed | Module invocation reaches the dry-run handler |

The 45 failures are **not 45 independent defects**, and 35/80 is **not a project-completion or code-coverage percentage**. Tests deliberately include negative and boundary cases. Missing components are tracked separately rather than padded into the executable test count. The fractional-raw logger test is additional robustness coverage: the current firmware emits integer raw readings.

Python 3.12.14, scikit-learn 1.8.0, joblib 1.5.3, NumPy 2.3.5, SciPy 1.17.0 were used. AWS SDK calls were replaced with local fakes; no cloud requests or billable deployment were performed. The fake DynamoDB implements the unconditional overwrite used by this handler, and the fake MQTT captures published payloads. These are behavioral reproductions, not real-service certification or concurrency load tests.

No Arduino CLI, board libraries/toolchain, physical XIAO/display, AWS credentials, or deployment access was available. Firmware was inspected, not compiled/flashed. There is no physical relay, pump, TLS, reconnect, display, end-to-end latency, or measured calibration acceptance result in this review.

## 3. Highest-priority findings

### F01 — Required watering subsystem is absent

**Evidence:** `aws/handler.py:26`; all supplied firmware sketches; `firmware/display/README.md`. **Spec:** §§5, 7, 9, 10.

There is no watering coordinator, command/event validation, command journal, automatic/manual dose path, response-rise calculation, reset handshake, or device-local command receiver. Firmware has no relay GPIO initialization, independent hard-stop timer, NVS transaction marker, dedupe ring, or persistent cooldown/fault handling. The handler always reports `DISARMED` and pump OFF.

Not sending pump commands is a sensible starter limitation, but it does **not** demonstrate the required safety behavior. In particular, no pump writes does not prove the relay is electrically OFF during boot/reset. Incoming telemetry claiming `pump.on=true` or a pump fault is also falsely rendered OFF/no fault by the handler; tests reproduce both. Complete this subsystem before attaching it to the physical watering demo.

### F02 — Condition rules ignore persistence, hysteresis, and night

**Evidence:** `aws/analysis.py:18–35`. **Spec:** §6, pp. 7–9; §11.

`classify_rules()` is explicitly immediate and stateless. Reproduced examples:

- The first 800-lux sample activates `low_light`; demo entry requires 10 seconds and a later qualifying sample.
- A 4-second light dip activates the issue; the required scenario says it must not.
- After sustained low light, 1200 lux clears the issue instead of holding it in the hysteresis gap.
- A first 1400-lux recovery sample clears immediately instead of waiting 5 seconds in demo mode.
- A 22:00 New York sample still triggers low light.

The same missing state affects temperature, humidity, dry/wet persistence, recovery, continuity gaps, and fresh-timer behavior after cooldown. A 12-second low-light test passes only because immediate activation also happens to be active at 12 seconds; it does not validate the timer algorithm. Implement and persist per-issue timers/state, with duplicate/order checks before advancement.

### F03 — Staleness and future-time protection are missing

**Evidence:** `aws/contracts.py:9–10`; `aws/handler.py:18–26`; SAM triggers. **Spec:** §§6, 8, 10.

A calibrated healthy packet timestamped one hour ago becomes `state=happy, data_status=ok` with a fresh report timestamp. A packet six seconds in the future is accepted despite the five-second future limit. All reports advertise 180 seconds of freshness, even for `profile=demo, sample_interval_s=2`, where the requirement is 10 seconds.

The template only invokes analysis on telemetry. There is no independent stale evaluator/heartbeat or implemented display/dashboard age watchdog to handle a complete absence of packets. Use original sample age and receipt/monotonic timing appropriately; never equate Lambda invocation time with fresh sensor data.

### F04 — Delayed or duplicate telemetry can roll the retained condition backward

**Evidence:** `aws/handler.py:32–50`. **Spec:** §§6, 8.

Sending seq 2 and then seq 1 publishes seq 1 last, replacing the retained latest condition. Sending seq 1, then seq 2, then a duplicate seq 1 does the same. There is no durable latest-sample/version check. Concurrent invocations can also race; that risk follows from the lack of synchronization but was not load-tested here.

DynamoDB overwrites one row for a duplicate key, so an identical duplicate does **not** create two sample rows. However, a changed payload with the same identity replaces the original data, which the test reproduces. Use conditional identity writes and a durable ordering/serialization design for current state and publication. A conditional history insert alone does not solve publish ordering or recovery after an MQTT failure. AWS documents both unconditional PutItem replacement and the need for idempotent Lambda processing; links appear in §9.

### F05 — Telemetry validation does not enforce the frozen contract

**Evidence:** `aws/contracts.py:3–21`. **Spec:** §5, pp. 5–7.

Confirmed accepted inputs include:

- Missing `profile`, `uptime_ms`, `sample_interval_s`, or `pump`.
- Missing soil `raw`, `raw_valid`, or `calibration_id`.
- Negative uptime, zero/string sample intervals, scalar pump instead of an object, or negative cooldown.
- Negative/string raw soil data, non-boolean raw validity, or an overlength calibration ID.
- `schema=true` (Python equality makes it compare equal to 1).
- A non-UTC timestamp or UTC timestamp without the required milliseconds-and-Z representation.
- A packet larger than 4096 UTF-8 bytes.
- An invalid measurement with its `value` key omitted, or invalid raw/pct data still carrying a non-null value.

Some important checks already work: boolean sequence IDs, negative lux, out-of-range RH, NaN/infinite temperature, malformed modes, and invalid scalar measurements with non-null values are rejected. Extend the validator rather than replacing these working checks. Validate all message types; only telemetry validation currently exists. Log bounded, sanitized reasons for rejections as required.

### F06 — Calibration/profile gates are incomplete

**Evidence:** `profiles/pothos.json`; `aws/analysis.py:29–34,48–54`; `aws/handler.py:8,21`; cloud firmware lines 135–147. **Spec:** §§3, 6, 9.

Keeping live calibration and watering values unqualified is correct until measurement evidence exists. The problem is that there is no calibration implementation, NVS storage, profile validator, canonical timing data, or profile reload flow.

The profile omits required raw endpoints/calibration ID and normal/demo timing sections, uses `revision` instead of `profile_revision`, and changes the watering schema. A packet claiming calibrated 0% soil can be marked happy with the supplied unqualified profile because both soil thresholds are null. Reversed soil thresholds are accepted. Device calibration/config claims need to be checked against the selected qualified profile, not merely trusted.

### F07 — Reports omit required information and reuse identities

**Evidence:** `aws/handler.py:20–26`. **Spec:** §§5, 8, 10.

`invalid_fields` and `details` are always empty, even when a sensor is invalid or an issue is active. The report therefore cannot supply the required reading, threshold, unit, and recommendation cards.

`backend_boot_id` is constant (`lambda-prototype`) and `report_seq` copies the sensor sequence. Different sensor boots starting at seq 1 produce the same report identity. Introduce a durable report generation/version scheme suitable for Lambda; do not assume warm process memory is authoritative.

### F08 — CSV logging loses disconnected-soil samples

**Evidence:** `tools/log_sensors.py:10–15,29–45`; both human-readable sensor sketches. **Spec:** §§9, 12.

Firmware emits `Soil Moisture: INVALID / OFFLINE`, but the logger recognizes only `Soil Moisture (raw)`. Consequently the entire row is never completed or yielded, including otherwise valid temperature, humidity, and light readings. This biases fault evidence and baseline completeness.

Recognize the offline label and emit a complete row with blank soil value and false validity. The original test covered an invalid humidity reading, not the actual soil-failure line. Additional robustness finding: fractional raw text such as `360.9` is silently truncated to 360 instead of rejected. Logger temperature/light acceptance ranges also differ from telemetry validation, so align or explicitly document them.

### F09 — AWS storage is only raw sample history; APIs and durable state are absent

**Evidence:** `template.yaml`, `aws/handler.py:35–45`, repository inventory. **Spec:** §8, adapted to AWS.

The table stores raw telemetry and source timestamp by `(mode/device, boot/seq)`. Receipt time is not stored separately. There are no durable condition records, issue timers, command/events/rejection journals, or authenticated history/state/watering APIs. No dashboard HTML/JS is included.

The sample sort key is a serialized `[boot_id, seq]` string, not chronological UTC order. Therefore it cannot directly provide the required ascending time-window history query; this is a schema/query-design gap, not a claim that DynamoDB cannot implement the requirement. Choose time-oriented access patterns/indexes and bounded queries. Preserve live/simulation separation and original identities.

### F10 — Display and simulation deliverables are missing

**Evidence:** `firmware/display/README.md`; repository inventory. **Spec:** §§10–11.

The display directory is a checklist only. PlantFace source, MQTT subscriptions, parser extensions, mode banners, issue cards, stale watchdog, and watering indicators are not included, so no display acceptance can be established.

There is no scenario publisher, simulated actuator, or full fixture set for night transitions, dips, hysteresis, multiple issues, successful watering, no-rise fault, and inspected reset. Unit tests are not a substitute for replaying these sequences through the same cloud/storage/display path.

### F11 — Simulation runs a different classification policy

**Evidence:** `template.yaml:60`; `aws/handler.py:14–17`; `aws/analysis.py:39–47`; `ml/train_example.py`. **Spec:** §1 no-ML decision; §11 common analysis path.

The SAM simulation function enables the synthetic model. Its suggestions replace rule-derived issues; it is not merely an extra advisory field. The classifier was trained on synthetic threshold labels, with no real plant outcome validation. Its behavior is not an acceptance oracle for the prescribed exact rules and timers, and simulation can differ from the live rule path.

If ML is not separately approved, disable it for acceptance and run the same deterministic engine in both modes. If approved, revise the spec, define ML's precise role, and retain the required deterministic watering safeguards.

### F12 — Firmware is a telemetry smoke-test build, not the specified controller

**Evidence:** `firmware/PlantCareCloud/CloudTelemetry.cpp`, `PlantCareCloud.ino`. **Spec:** §§4, 9.

Source inspection confirms useful work: correct live topic strings, configured TLS credentials/8883, QoS-1 publish arguments, retained status/LWT with null offline timestamp, a 4096-byte MQTT client buffer, reconnect delays, boot/seq fields, and a separate cloud task so ordinary reconnect delays are not placed in the sensor loop.

Limitations: profile and cadence are hardcoded to demo/2 seconds; no normal/fast selection; no calibration conversion; no control subscriptions; no graceful-offline path; no explicit NTP-failure diagnostic or demonstrated first-sync evidence; firmware library versions are not pinned. The single-slot outbox overwrites pending samples and drops old/failed publications. This matches the documented no-backfill approach, but requires sent-ID logging to measure connected-run completeness; generated sequence IDs alone are not proof of successful publication. These firmware observations remain uncompiled source findings.

### F13 — Onboarding instructions are inconsistent

**Evidence:** root README quick start and `docs/*`.

Both direct-file Python startup commands fail; `python -m aws.local_invoke` works. The training script likewise needs the documented module form `python -m ml.train_example` from the project root (the later collection document uses that form). Do not regenerate the submitted model during an audit merely to hide an import issue.

Some handoff documents still say MQTT/history are unimplemented although a cloud sketch and raw-history writes now exist. Three different sensor sketches use different output formats/cadences. Select one canonical production path and one explicit logging path, then have a teammate follow the instructions from a fresh environment. Exact firmware versions and actual build/flash evidence are still required.

## 4. Requirement-to-evidence matrix

| Requirement group | Current status | Basis / next acceptance gate |
|---|---|---|
| Sensor pin/address setup and validity | Partial, source-only | Correct planned pins/addresses; unplug/replug and read-error evidence needed |
| Soil calibration | Missing implementation/evidence | Qualified endpoints, repeated insertions, noise, ID, NVS and conversion |
| TLS/MQTT sensor telemetry | Implemented in source, unverified on device | Compile, NTP, actual QoS-1 publish, LWT and reconnect trace |
| Normal/demo/fast cadence | Partial | Only demo cadence in cloud sketch |
| All frozen message contracts | Failing/incomplete | Telemetry validator gaps; other message types absent |
| Six condition rules | Immediate threshold subset | Timers, hysteresis, continuity, day/night and profile gates absent |
| Stale/invalid/uncalibrated behavior | Partial/failing | Basic invalid/uncalibrated handling works; age and fields incomplete |
| Durable sample identity/history | Partial | Raw rows exist; mutation/order/receipt-time problems |
| Durable analysis and command state | Missing | No state tables/coordinator/journals |
| Automatic/manual watering and safeguards | Missing | Cloud and device modules plus bench qualification |
| Display | Not supplied | Checklist is not implementation |
| Dashboard and API | Not supplied | UI, history, controls, authentication and fault rendering |
| Simulation isolation | Partial | Separate function modes/topics/IAM publish resources; device policies not supplied |
| Scenario replay/simulated actuator | Missing | Replay common production path with visible simulation labels |
| Evidence and reproducible startup | Incomplete | Evidence README only; two failing README commands |

The master references 30 professor-facing demo steps but does not reproduce their complete original numbered checklist. This audit maps the supplied requirements; it does not invent a pass/fail assessment of unseen step wording.

## 5. What already works locally

- All nine supplied tests pass with the pinned model dependencies available.
- Uncalibrated telemetry produces unknown instead of claiming a calibrated assessment.
- Several invalid numeric inputs are rejected, and null invalid metrics are accepted.
- Low humidity is mild; no unintended high-humidity or excess-light rule was observed.
- Other valid issues survive an unavailable sensor on the rule path.
- Live and simulated Lambda mode checks reject a mismatched mode before AWS writes/publication.
- Mocked publication uses the correct respective condition topic, QoS 1 and retention.
- Repeated identical telemetry uses one DynamoDB identity, and a publish failure followed by retry still leaves one history identity in the local fake.
- Normal complete serial rows parse successfully.
- No live pump commands are generated by this snapshot.

These are narrow passes and must not be generalized to full end-to-end success.

## 6. Suggested repair order and ownership

1. **Pranav + team:** record the AWS architecture amendment; resolve the ML conflict; freeze canonical contracts/profile and chosen firmware path.
2. **Pranav + Anish:** fix contract validation, offline-soil CSV loss, and startup documentation. Add source/receipt timestamps and packet identity evidence.
3. **Cristian + Pranav:** implement the pure deterministic condition engine and durable AWS state; prove time boundaries, night, gaps, duplicates, and out-of-order behavior before wiring UI.
4. **Pranav:** implement history/state APIs, durable ordered publication, rejection logs and authenticated browser access. Match required API behaviors even if route implementation changes.
5. **Camilo:** supply PlantFace source and complete networking/parser/watchdog/UI; implement dashboard against the agreed API.
6. **Anish + Cristian:** collect calibration and pump qualification evidence, then implement device safety and the watering coordinator together. Keep unqualified values null until measured.
7. **All:** replay common-path simulation scenarios, then hardware/cloud integration; save per-step evidence and run the exact startup instructions independently.

## 7. Required tests after implementation

The attached tests expose current functions; refactor their adapters when the stateful engine interface is implemented. Do not delete failing requirements merely to achieve a green suite.

Add explicit tests for each rule's equality/entry/clear boundaries; 1.5× interval continuity boundary; duplicate and out-of-order timer behavior; night entry/exit; normal versus demo versus fast stale thresholds; warm/cold Lambda restart; simultaneous invocations; DynamoDB conditional conflicts; failures between persistence and publication; conflicting duplicate identities; and mode-separated history.

Watering tests must cover all local refusal reason codes, duplicate/expired/old-boot requests, overlong-duration rejection (not clamping), no double actuation, command timeouts, late events, sensor loss mid-dose, NVS recovery, cooldown preservation, three-post-dose-reading median, no-rise fault, inspected reset staying disarmed, and browser request-id reuse. Test local hard-stop timing during blocked Wi-Fi/TLS and power/reset interruptions on the bench with saved evidence.

Finish with actual device → IoT → Lambda → DynamoDB → display/dashboard identity traces, bounded-run sample completeness, certificate topic restrictions, real connection loss, real time sync, and chart gaps. Neither mocks nor static template lint establishes these.

## 8. Reproduce this audit

Extract the evidence ZIP. From its root:

```sh
cd PlantCare_Team3_Starter
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m aws.local_invoke
cd ..
python audit/test_spec_audit.py PlantCare_Team3_Starter
```

The audit runner returns nonzero for the known requirement failures and rewrites its adjacent `spec_test_results.txt` and `spec_test_summary.json`. It requires no AWS connection. The original source tree is included without application changes; `source_manifest.json` records its hashes. Logs contain detailed assertions and source locations. `environment.json` records tested package versions.

## 9. External references used for AWS behavior

- AWS DynamoDB PutItem: https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_PutItem.html — unconditional puts replace existing same-key items; conditional writes can prevent replacement.
- AWS Lambda with IoT: https://docs.aws.amazon.com/lambda/latest/dg/services-iot.html — asynchronous invocation and retries.
- AWS Lambda best practices: https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html — idempotent event processing.

All implementation/spec findings otherwise come from the supplied files and executed local tests, not assumptions about an unseen deployment.

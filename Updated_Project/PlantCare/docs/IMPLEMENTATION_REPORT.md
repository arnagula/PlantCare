# Plant Care Companion — implementation and verification report

**Date:** 12 November 2026  
**Scope:** supplied Team 3 code and Master Implementation Doc v2.0, with AWS replacing the localhost/SQL architecture.  
**Verdict:** substantially implemented and locally verified software candidate. **Not full-system acceptance:** AWS is not deployed, measured live calibration/pump qualification is absent, and the original PlantFace GUI was not supplied.

## 1. What this report establishes

The initial audit exposed behavior that contradicted the design, not merely missing deployment settings. This revision adds the deterministic timed engine, frozen-message validation, calibration gates, durable ordering/journaling, watering coordinator, device safety implementation, AWS infrastructure/adapters, dashboard, display bridge and simulation path. The code keeps monitoring available while live watering remains unqualified.

Passing local tests proves the tested behavior under the documented test conditions. It does not prove real certificates, AWS permissions, timing under physical faults, sensor accuracy, pump volume or the assembled display. The acceptance gaps below remain explicit; no project-completion percentage is inferred from a test count.

There was an interrupted implementation attempt whose unsaved files were lost when the workspace reset. This report uses the recovered original inputs and the newly rebuilt code. Earlier pre-reset test/build claims are not counted as evidence for this revision. Checkpoints were saved during rebuilding.

## 2. Governing requirements and approved adaptation

Both master PDFs supplied for the original review were identical: SHA-256 `4293813726827c049686a7851c465459ca5f0a10b5e57bc33e437960aa76fd50`. The source archive was `PlantCare_Team3_XIAO_Cloud.zip`. Original source and baseline evidence were recovered from `PlantCare_Audit_Evidence.zip`.

AWS supersedes the laptop/SQLite implementation choice. It does not change the six issue definitions, timing, invalid/stale semantics, device safeguards, QoS 1, live/simulation separation, calibration evidence, or no-ML decision. The previous synthetic model is archived and excluded from runtime deployment.

`AWS_DESIGN_AMENDMENT.md` records the necessary adaptations: a logical durable backend across Lambda cold starts, explicit `BackendGeneration` restart behavior, FIFO serialization, transactional state/outbox, JWT authentication, privileged queue-based reload, bounded history pages, startup null source fields, and simulation-only day/night override. These adaptations are documented for team review rather than silently presented as original PDF wording.

## 3. Initial tests — reproduced on the unchanged baseline

| Check | Observed result | Meaning |
|---|---|---|
| Original supplied unit suite | **9 passed** | Original narrow smoke tests pass |
| Original specification audit | **80 run: 35 passed, 45 failed, 0 errors** | Reproduces the original behavioral and contract defects |
| Initial audit syntax/template checks | Passed in original evidence | Static checks did not detect the behavioral gaps |
| Initial README direct-file commands | Import errors in original evidence | Module invocation needed correction |

The nine-test suite and 80-test audit were rerun after recovery against the unmodified baseline. Logs are `evidence/baseline_rerun_9.txt` and `evidence/baseline_rerun/`. The 45 failures are not 45 independent defects. The original 80-test runner assumes the old stateless handler and mocked unconditional storage interface; the new acceptance suite tests the replacement stateful service and AWS adapter boundaries. Original tests were retained as evidence rather than altered to disguise their old assumptions.

## 4. Recommendations and resulting changes

| Finding | Initial recommendation | Changes in this revision | Remaining acceptance |
|---|---|---|---|
| F01 Watering absent | Implement cloud coordinator and independent device safeguards | Seven-state coordinator; arm/reset acknowledgements; manual and automatic gates; median response; timeouts; faults; immutable command/event/outcome journal; portable safety core and GPIO timer firmware | Measured pump qualification and physical power/network/NVS failure tests |
| F02 Stateless rules | Implement persistence, hysteresis, continuity and night | Serializable per-rule entry/clear timers, exact strict comparisons, recovery delays, America/New_York night and sample-order checks | Real sensor scenario demonstrations |
| F03 Freshness absent | Use original timestamps and independent absence detection | Future-time checks, normal/demo/fast timeouts, heartbeat ticks, browser/display watchdogs | Actual scheduling latency and connectivity loss |
| F04 Rollback/overwrites | Serialize updates, preserve identity, recover publication | Per-mode FIFO owner, conditional version, atomic records/state, persisted outbox, exact duplicate suppression, conflicting-identity rejection | Real-service retry/load/failure injection |
| F05 Incomplete contracts | Validate all frozen payloads | Telemetry, condition, commands, events and status validators; bounded wire size; strict UTC, finite types, required null/value fields | Device-to-cloud traces with actual payloads |
| F06 Weak qualification | Canonical profiles and measured gates | Separate live/sim profiles; ordered thresholds; endpoint/noise/count evidence; dose/response/cooldown validation; privileged reload; firmware config generation | Actual dry/wet and pump evidence; matching qualified deployment |
| F07 Incomplete reports | Validity/details and independent report identity | Invalid-field lists, issue values/units/threshold/advice, durable backend report sequence/generation, actual pump/fault visibility | Original GUI rendering of all fields |
| F08 Logger drops rows | Preserve disconnected soil rows and reject fractional raw | Offline label recognized; invalid row retained; integer raw enforcement; aligned ranges | Hardware serial capture |
| F09 Missing state/API/UI | Implement AWS equivalents for required behavior | DynamoDB time-keyed readings/history/journals; authenticated APIs; dashboard; request dedupe and stable results | AWS setup, JWT/certificate negative tests, real-browser acceptance |
| F10 Missing display/simulator | Extend PlantFace and run common-path fixtures | Display network/parser/watchdog bridge with explicit GUI hooks; local and TLS simulation tools including successful/no-rise dose paths | Camilo's missing original GUI integration; cloud scenario replay |
| F11 Different simulation policy | Use deterministic common analysis | Same engine/coordinator for both modes; synthetic model archived and excluded from deployment | Team must retain this policy unless spec is explicitly revised |
| F12 Sensor-only firmware | Add commands, qualification, cadence, shutdown and pinned build | Canonical XIAO controller, GPIO2 OFF first, local timer, NVS markers/config, fresh soil checks, TLS task, event retries, normal/fast cadence, graceful shutdown, pinned PlatformIO dependencies | Real board flash and bench evidence |
| F13 Broken/inconsistent onboarding | Correct entry points and choose canonical paths | `python -m` commands; updated README/setup/bench docs; legacy code archived; production package allowlist | Teammate clean-environment walkthrough |

## 5. Implemented behavior in detail

### Condition engine

Each qualifying measurement starts a timer; a later fresh qualifying sample must reach the interval before activation. A nonqualifying sample resets the pending timer. Active issues remain through the hysteresis band and clear only after sustained recovery. Equality does not start an entry or recovery timer. Duplicate, old-sequence, old-timestamp and retired-boot samples cannot advance current assessment. Gaps interrupt continuity; stale/invalid assessments stop presenting old issues as current. Valid fields continue independently when another sensor is invalid.

| Issue | Enter | Clear | Normal persistence | Demo persistence |
|---|---|---|---:|---:|
| Thirsty | soil < d | soil > d_c | 300 s | 10 s |
| Too wet | soil > w | soil < w_c | 3,600 s | 10 s |
| Low light | daytime lux < 1,100 | lux > 1,300 or night | 1,800 s | 10 s |
| Too cold | temperature < 16 C | temperature > 17 C | 300 s | 10 s |
| Too hot | temperature > 27 C | temperature < 26 C | 300 s | 10 s |
| Low humidity | RH < 50% | RH > 55% | 1,800 s | 10 s |

Normal recovery is 60 seconds; demo recovery is 5 seconds. Normal sampling is 60 seconds, active/observation sampling 2 seconds; normal stale timeout 180 seconds and fast/demo timeout 10 seconds. Night is 20:00–08:00 America/New_York. Low humidity remains a mild advisory. There is no high-humidity or excessive-light issue. Numeric care ranges come from the governing design; persistence and hysteresis are engineering settings, not measured horticultural outcome claims.

### Qualification and device control

Live profile fields stay null/unqualified until measured. Simulation's 300/700 raw endpoints, 30/40/70/80 thresholds and 2-second dose are fixtures, not live recommendations. Firmware generation refuses a simulation profile. Qualification requires approved evidence, at least 20 dry and 20 wet samples, distinct endpoints with nonoverlapping measured noise, ordered thresholds, positive dose within hard maximum, response wait at least 6 seconds, cooldown at least response wait and rise above measured noise.

The device initializes the relay OFF before networking; the hardware adapter schedules an independent `esp_timer` cutoff. NVS records an active transaction before ON and clears it after OFF. Failed marker writes lock out actuation. Reboots disarm; unfinished markers fault. Commands require matching mode/boot/config, a valid 10-second envelope, valid local moisture, qualification, arming, dry-now, cooldown and duration bounds. Duration is rejected rather than clamped. Accepted and rejected command identities are remembered to prevent later reinterpretation of a retry. Queued event retries reuse the exact event sequence/payload.

Physical cutoff accuracy, active-high relay polarity and fault behavior still require measurement. Host execution of the safety logic does not prove ESP32 scheduling, electrical OFF levels or actual water flow.

### Coordinator, durability and cloud interfaces

The coordinator follows DISARMED → READY → COMMAND_PENDING → RUNNING → OBSERVING → COOLDOWN → READY, with latched FAULT transitions. Arming is acknowledged by the device; submitting an HTTP request alone does not arm. Manual watering bypasses dry persistence but still requires soil below the dry threshold and every safety gate. Completion enters observation; the last three valid post-dose samples are evaluated by median, not a single favorable outlier. Cooldown begins at physical completion. Reset requires inspection, remains disarmed, and preserves cooldown.

DynamoDB commits sample/reading rows, state and outbox together under a version condition. The worker publishes only after commit. A failed or ambiguous publish can repeat the same outbox item; this is at-least-once delivery, not an exactly-once MQTT claim. Device dedupe and immutable command IDs provide the actuation guard. Five reading types retain validity and separate receipt/source timestamps. Current-state order cannot be rewritten by an old identity. Late events are journaled and cannot automatically clear a fault or rewind a completed pump state.

Separate FIFO queues and IoT policies isolate modes. Workers have table permissions constrained by mode partition and topic-specific publication. HTTP mutations require the configured JWT authorizer; the dashboard keeps a short-lived token in memory. Request IDs survive retries and reserve a stable command ID/result; the worker rechecks gates at execution time. Profiles reload only through an IAM-authorized operator command with a fixed mode-specific file.

### User interfaces and simulations

The dashboard provides units, validity, original sample time, issue advice, watering stage, disabled reasons, confirmation prompts, two-second polling, history windows, invalid/missing-data gaps and watering markers/logs. It renders strings as text rather than HTML. Network uncertainty keeps the request ID available for retry.

The display bridge runs networking outside the GUI task, accepts ordered fresh condition reports and applies both source-age and arrival-age watchdogs. It supplies integration hooks; it does not manufacture a replacement for the missing original PlantFace implementation. Preserving its touch/audio/animation behavior requires that source.

The offline simulation uses the same service and storage interfaces as production. The TLS publisher has only simulated topics/identity, with complete schema-1 telemetry and a simulated actuator. Operator-controlled day/night fixtures are restricted to the simulated profile.

## 6. New tests and evidence

The final machine-readable count is in `evidence/new_test_summary.json`; every test name/result is in `evidence/new_tests.txt`.

| Verification | Result / scope |
|---|---|
| Python specification/regression suite | **204 passed, 0 failures, 0 errors, 0 skipped** at report preparation |
| C++ safety core | Strict C++17 warnings-as-errors build; AddressSanitizer/UndefinedBehaviorSanitizer assertion suite passed |
| C++ display/UTC logic | Same strict/sanitized host build; ordering, clock, format and watchdog assertion suite passed |
| Dashboard DOM behavior | **10 passed** using jsdom; startup unknown, mode/metrics, token clearing, disabled controls, text safety, single POST, history gaps and outage handling |
| SAM/CloudFormation template | `cfn-lint 1.60.0` passed with no diagnostics |
| Python/JavaScript syntax | compileall and `node --check` passed |
| Success simulation | Full sample → rule → command → actuator → event → observation → cooldown path ends READY/happy |
| No-rise simulation | Same path ends FAULT/insufficient_rise and remains faulted |
| Actual browser rendering | Not completed: Chromium was unavailable and its download failed; DOM tests are not visual/browser acceptance |
| Sensor firmware | PlatformIO build passed: 46,036 bytes static RAM; 913,101 bytes flash. No flashing or hardware test |
| Display bridge compile harness | PlatformIO build passed: 18,420 bytes static RAM; 257,589 bytes flash. Compile-only XIAO harness, not the Waveshare GUI |

Tests cover required/missing fields, boolean-versus-number errors, finite ranges, timestamp formats/future bounds, all six normal/demo persistence rules, equality, hysteresis and recovery, day/night transitions, gaps, stale/invalid data, unqualified claims, calibration evidence, sample identity/receipt history, outbox recovery, conditional conflict, live/sim isolation, command journaling, request idempotency/conflicts, JWT routing, SDK request shapes, device restart/fault/reset, completion/start timeouts, median response, sensor loss and late-event handling. SDK Stubber checks real SDK shapes without contacting AWS; it does not certify deployed IAM or transactions under load.

### Issues found during remediation

Additional tests/review led to fixes beyond the initial recommendations: stable IDs for pending API retries; durable blocked results; late-event correlation through the command journal; unexpected pump visibility; rejection-ID memory in the safety core; condition-history suppression of countdown-only changes; profile reload fault preservation; packet-identity encoding; control of future timestamps at receipt; deployment packaging that excludes secrets/legacy models; preserving faults through disarm; full cooldown after uncertain reset; canonical watering API aliases; and reading unit/mode/calibration metadata. A failed jsdom harness evaluation was corrected in the test harness; it was not counted as an application pass.

## 7. Remaining conclusions and next steps

1. **Pranav — cloud integration:** provision AWS and authentication using `AWS_SETUP.md`; build/deploy the reviewed stack; prove negative IAM/JWT tests, real QoS/retries, queue recovery and retained condition ordering. Run simulation first. Cloud setup is a remaining phase, not a failed prerequisite for writing/test-driving the implementation.
2. **Anish + Cristian — measured qualification:** collect and retain soil and pump measurements, fill the canonical live profile, approve evidence, regenerate firmware and deploy matching IDs. Run every physical failure test in `BENCH_ACCEPTANCE.md`. Until then, live watering correctly remains blocked.
3. **Camilo — display integration:** supply the original PlantFace source, wire the bridge callbacks into its GUI, and verify all issue/status/detail fields while preserving existing touch/audio/animation behavior. The compile harness is not a finished display application.
4. **Team — browser and complete demonstration:** run a real-browser review and physical end-to-end identity/latency/completeness test. Apply the original professor-facing numbered checklist, preserving ownership and weights. The full original 30-step wording was not included in the audited master; no unseen step is declared passed.
5. **Release decision:** accept the project only after saving the AWS, calibration, pump, display and end-to-end evidence. Local test success supports continuing integration; it does not support a claim that every physical/deployed design specification has already been met.

## 8. Reproduction and evidence files

Run the commands in the updated README from a clean virtual environment. `tools.verify` exits unsuccessfully on failures, errors or skips. The ZIP contains source, tests, simulation traces, baseline reruns, new logs, template lint, firmware build logs, dependency/build pins, setup instructions and acceptance checklists. Private credentials, `node_modules`, compiler caches and generated binaries are excluded.

Primary AWS references consulted for the adaptation:

- https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis-iam.html — transactional permissions use underlying item operations.
- https://docs.aws.amazon.com/iot/latest/developerguide/sqs-rule-action.html — direct IoT SQS actions do not support FIFO, motivating ingress Lambda.

## 9. Final build and packaging notes

The controller build completed successfully using espressif32 6.10.0, Arduino framework 2.0.17 (PlatformIO package `3.20017.241212+sha.dcc1105b`), MQTT 2.5.2 and ArduinoJson 7.3.1. Sensor libraries are pinned in `platformio.ini`; resolved dependency versions are retained in the full build log. Downloads with checksum mismatches were rejected by the package manager, which retried another mirror; verification was not disabled. The display bridge compiled in the explicit compile-only harness, with no-op GUI hooks. It must not be flashed as a replacement display application.

`evidence/firmware_build.txt` and `evidence/display_adapter_build.txt` contain the build results. `evidence/lambda_package_manifest.txt` records the runtime allowlist check: no credentials, firmware, legacy classifier or test evidence ships in the Lambda bundle. `evidence/source_hashes.json` fingerprints the final application/test/document source files. `evidence/environment_final.json` records the local runtime versions. The final deliverable excludes toolchain caches, private credential filenames, generated firmware binaries and Node dependencies.

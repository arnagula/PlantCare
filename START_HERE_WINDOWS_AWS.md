# Plant Care Companion — Windows / AWS startup

This bundle includes:
- `Updated_Project/PlantCare/`: most recent updated implementation, AWS SAM template, Lambda, dashboard, firmware, tests, and docs. This is a candidate and has **not** been verified deployed to AWS.
- `Data_Collection/PlantCare_24Hour_Log/`: acquisition sketch and `log_24h.py` for current serial logging.
- `Previous_AWS_Prototype/`: older prototype ZIPs for reference and recovery. Do not combine their `template.yaml` or Python modules with the updated implementation without reviewing differences.
- `Project_Status_README.md`: earlier project summary.

## First steps on this Windows computer

Open a **new** PowerShell window (leave your currently running plant logger open).

```powershell
aws --version
sam --version
python --version
aws configure list
aws sts get-caller-identity
```

If `aws` or `sam` are not found, install AWS CLI v2 and AWS SAM CLI using their official Windows installers. Configure a profile using credentials authorized for your AWS account; avoid putting secrets inside this ZIP. Prefer SSO/temporary credentials where available.

After extracting:

```powershell
cd "<EXTRACTED_FOLDER>\Updated_Project\PlantCare"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m tools.verify
```

Read `docs/AWS_SETUP.md` **before deployment**. The updated stack requires an IoT Data-ATS endpoint plus a configured JWT issuer and audience. It can create queues, Lambda, DynamoDB, rules and an HTTP API; check resources/costs and existing names before executing a change set.

```powershell
aws iot describe-endpoint --endpoint-type iot:Data-ATS --region us-east-1
sam build
sam deploy --guided
```

Use `us-east-1` only if that is still your intended region. In the guided deployment provide the parameters documented in `docs/AWS_SETUP.md`; do not blindly overwrite the previously deployed `plantcare-team3` stack. Use a separate test stack if uncertain.

## Important

The 24-hour serial data logger is **not** the production AWS-publishing controller. Keep collecting data as planned; switching to production firmware would change the serial protocol and interrupt collection.

Automatic watering must remain disabled until physical pump, relay, power, drainage and calibration testing is completed.

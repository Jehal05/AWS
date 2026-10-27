# Deploying RenewFlow to AWS

One small instance behind CloudFront, so the whole demo costs roughly $10 for two weeks, and
less on the AWS Free plan where credits apply. A $10 budget with email alerts is created by the stack.

```
 customer ── WhatsApp ──► End User Messaging Social ─┐
 customer ◄── email ───── SES ── event destination ──┼─► SNS topic ─► CloudFront ─► EC2 (app + SQLite)
                                                     │                                  │
                                       Bedrock (Converse) ◄───────────────────────────────┘
```

## Before you deploy

1. AWS account on the Free plan; set a $10 budget (the stack also creates one).
2. SES: verify a sender identity (a domain or address you own). New accounts start in the sandbox,
   which only sends to verified addresses. Request production access for real recipients.
3. Bedrock: enable model access for the model in `RENEWFLOW_BEDROCK_MODEL` in your region.
4. WhatsApp (optional until approved): link a WhatsApp Business account in End User Messaging
   Social, create and get approval for a utility template whose body is a single `{{1}}`, and note the
   phone number id. Until then, leave `LocalChannels=whatsapp` and the channel stays simulated.

## Deploy

```bash
cd infra
pip install -r requirements.txt
npm install -g aws-cdk
cdk bootstrap
cdk deploy \
  --parameters WebhookToken=$(openssl rand -hex 24) \
  --parameters SesFromAddress=renewals@your-domain.com \
  --parameters AlertEmail=you@your-company.com
```

On a deployed instance the Reset, Run simulation and settings endpoints are disabled unless you
also pass `--parameters AdminToken=<secret>` and send it as the `X-Admin-Token` header. SNS
messages must carry a valid signature (`RENEWFLOW_SNS_VERIFY=0` turns this off, for tests only).

The outputs give the dashboard URL and the SNS topic ARN. Then, in the End User Messaging Social
console, set that topic as the WhatsApp event destination so replies and receipts reach the app.
Confirm that the SNS subscription shows as Confirmed.

## Tear down

`cdk destroy` removes everything the stack created. Do this after judging ends (Nov 12).

## Known limits

- SNS signatures are not verified; the webhook relies on a secret URL token plus a topic allow-list.
- Port 80 on the instance is open to the internet so CloudFront can reach it. The data is synthetic.
- SQLite lives on one instance's disk. That is deliberate for a demo, not for production.

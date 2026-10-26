# RenewFlow

An omnichannel, agentic assistant for insurance renewals, built for the AWS Communication
Developer Services (CDS) Agentic AI Partner Hackathon.

RenewFlow picks the channel a customer is most likely to answer on (WhatsApp, email, optionally
SMS), holds a two-way conversation, moves between channels without losing context, learns from
engagement events, enforces guardrails on every message, and hands off to a person when needed.

## Run it (no AWS account needed)

```bash
pip install -e ".[dev]"
PYTHONPATH=src python -m renewflow --reset      # http://localhost:8000
pytest                                          # 58 tests
```

Open the dashboard, select **Priya Sharma** and press **Start renewal**, then use
**Play as customer** to reply on WhatsApp or email. **Run simulation** pushes 20 synthetic
customers through the same agent. All data is synthetic.

## Architecture

![RenewFlow architecture](docs/architecture.png)

More: [deployment](docs/DEPLOY.md), [demo script](docs/DEMO_SCRIPT.md), [Devpost draft](docs/DEVPOST.md).

- `agent/` tool-calling loop (max 8 steps), guardrails, traced tool calls
- `channels/` `Channel` protocol: `LocalChannel` now, AWS End User Messaging Social + SES next
- `llm/` `ChatModel` protocol: `MockModel` now, Amazon Bedrock next
- `analytics/` channel scoring (30-day half-life, Bayesian smoothing) and KPIs
- `api/` FastAPI; `static/` dependency-free dashboard

## Guardrails

Consent, enabled channel, per-channel length, prohibited promises, quiet hours (21:00-08:00
customer time), 2 proactive messages per 24h, and no invented prices (every ₹ amount must come
from a tool result). STOP/START are handled deterministically before the model runs.

## AWS mode

| Piece | Local | AWS |
|---|---|---|
| WhatsApp | `LocalChannel` | End User Messaging Social `SendWhatsAppMessage` (`channels/aws.py`) |
| Email | `LocalChannel` | SES v2 `SendEmail` (`channels/aws.py`) |
| Model | rule-based mock | Bedrock Converse with tool use (`llm/bedrock.py`) |
| Inbound + receipts | dashboard simulator | SNS → `/webhooks/sns/<token>` (`aws/events.py`) |

A channel can stay simulated in AWS mode (`RENEWFLOW_LOCAL_CHANNELS`) and the dashboard labels
each channel as live or simulated. Deployment (CDK, about $10 for two weeks) is in
[docs/DEPLOY.md](docs/DEPLOY.md). The adapters are tested against botocore's real request schemas.

## Status

Local mode and the AWS adapters are complete and tested. Not yet exercised against a live AWS
account: Bedrock model access, SES production sending, and the WhatsApp number and template.

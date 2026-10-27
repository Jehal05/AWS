# RenewFlow

An omnichannel, agentic assistant for insurance renewals, built for the AWS Communication
Developer Services (CDS) Agentic AI Partner Hackathon.

RenewFlow starts each renewal on the channel the customer is most likely to answer (WhatsApp or
email), explains why the premium changed, prices payment options, sends a payment link, and moves
to another channel mid-conversation without losing context. It hands claims, complaints and
anything unclear to a person, honours STOP immediately, and shows everything on a dashboard.

**Demo video (2:29, with voice-over and subtitles):** [docs/demo/renewflow-demo.mp4](docs/demo/renewflow-demo.mp4)

[![Watch the demo](docs/demo/thumbnail-1280x720.jpg)](docs/demo/renewflow-demo.mp4)

![Overview](docs/screenshots/1-overview.png)

## Try it in two minutes

You need Python 3.11 or newer. No AWS account, keys or network access are required.

```bash
git clone https://github.com/Jehal05/AWS.git && cd AWS
pip install -e ".[dev]"
python -m renewflow --reset          # open http://localhost:8000
```

1. Open **Conversations**. **Priya Sharma** is selected.
2. Press **Start renewal**. The agent picks WhatsApp because that is where she engages, and sends.
3. Open **Play as customer** and tap *Premium looks higher, can I split it?*. The agent explains the
   increase and prices a quarterly plan.
4. Tap *Please email me the details*. The same thread continues on email (see the "Continued on
   Email" marker). Open the email, press **Renew securely**, then **Pay now**.
5. Pick another customer, start their renewal, and send *My claim was rejected*. They land in
   **Handoffs** and the assistant goes quiet. Send *STOP* on a third customer to see consent revoked.
6. Press **Run simulation** to push 20 synthetic customers through the same agent, then open
   **Overview** and **Channels**.

Run `pytest` for the 74 tests (a browser test replays this whole story).

Everything is synthetic, and in this mode WhatsApp and email are simulated in-process. The
dashboard labels each channel "(simulated)" or "(live)" so the two are never confused.

## How it uses AWS Communication Developer Services

| Piece | Local | AWS |
|---|---|---|
| WhatsApp | `LocalChannel` | End User Messaging Social `SendWhatsAppMessage` (`channels/aws.py`) |
| Email | `LocalChannel` | SES v2 `SendEmail` (`channels/aws.py`) |
| Model | rule-based mock using the same tool-calling protocol | Bedrock Converse with tool use (`llm/bedrock.py`) |
| Inbound replies and receipts | dashboard simulator | SNS → webhook (`aws/events.py`, `api/webhooks.py`) |

Channels and the model sit behind small interfaces, so the same agent runs in both modes. The AWS
adapters are tested against botocore's real request and response schemas. **They have not yet been
exercised against a live AWS account**: that needs Bedrock model access, SES production sending and
a Meta-approved WhatsApp number. Deployment (CDK, about $10 for two weeks, with a $10 budget alert)
is described in [docs/DEPLOY.md](docs/DEPLOY.md).

![Architecture](docs/architecture.png)

## What makes it safe to run on real customers

- Consent and enabled-channel checks on every send
- Quiet hours in the customer's time zone (21:00 to 08:00) and a limit of 2 proactive messages a day
- Per-channel length limits and blocked promises
- **No invented prices:** every ₹ amount in a message must come from a pricing tool, or the send is blocked
- STOP and START are handled before the model runs
- Claims, complaints and unclear requests go to a person with a summary; model or tool failures
  also end in a handoff rather than a silent drop
- Every tool call is traced and visible in the dashboard's Activity tab

## Does choosing the channel help?

The Overview splits simulated customers at random: half are contacted on the channel the score
recommends, half on email first. It reports contacted, responded, renewed and time to renew for
each. The customers are synthetic and see a message with the probability their persona reads that
channel, so the gap follows from that assumption and is not evidence. On 8 simulated cohorts the
scored group renewed 32 of 80 against 29 of 80, which is within noise. The point is the
measurement; a real pilot would replace the simulated behaviour.

## Evaluation

`python -m renewflow.eval` runs 37 labelled customer messages (claims, cancellations, price
questions, opt-outs, vague replies; English, Hinglish and Hindi) and checks the outcome: handoff,
opt-out, email, payment link, answer or clarify. The rule-based mock passes 37/37, but it was
adjusted while building this set, so read that as a regression guard, not an accuracy claim. The
same command grades Bedrock with `RENEWFLOW_MODEL=bedrock`; that run has not happened yet because
there is no AWS access.

## Layout

```
src/renewflow/
  agent/       tool-calling loop (max 8 steps), guardrails, tools, prompts
  analytics/   channel scoring (30-day half-life, Bayesian smoothing) and KPIs
  channels/    Channel protocol, local and AWS adapters
  llm/         ChatModel protocol, mock and Bedrock adapters
  aws/         inbound WhatsApp and SES event processing
  api/         FastAPI app and SNS webhook
  static/      dependency-free dashboard
infra/         CDK stack      docs/   architecture, deployment, demo script, Devpost text
tests/         74 tests
```

## Limits

SQLite on one instance is deliberate for a demo, not for production. The SNS webhook uses a secret
URL token, a topic allow-list and SNS signature verification (tested against locally signed
messages, not yet against real SNS traffic). When deployed, Reset, Run simulation and settings are
disabled unless an admin token is configured. The Bedrock adapter is tested with a scripted fake
client in the exact Converse response shape, not against the live service.

Licensed under MIT.

# Devpost submission text (draft)

Replace every `[…]` before submitting. Claims about AWS must match what is actually deployed.

## Project name
RenewFlow

## Tagline
An agent that renews insurance policies on the channel each customer actually answers.

## Inspiration
Renewals are the most predictable revenue an insurer has, and the most routinely lost. The same
reminder goes to everyone by SMS or email, nobody replies, and the policy lapses. The customers who
do reply have a question about the premium that a human has to answer, usually days later.

## What it does
RenewFlow starts each renewal on the channel the customer is most likely to answer, based on their
own engagement history and consent. It explains why the premium changed, prices payment options,
sends a payment link, and moves to another channel when the customer asks, in the same conversation.
It hands claims, complaints and anything unclear to a person with a written summary, and honours
STOP immediately. A dashboard shows renewal rate, revenue secured, the funnel, what the guardrails
blocked, and every step the agent took.

## How we built it
- **AWS End User Messaging Social** sends WhatsApp messages (an approved template opens the
  conversation; replies inside 24 hours are free-form).
- **Amazon SES** sends email; delivery, bounce and complaint events come back through **Amazon SNS**.
- **Amazon Bedrock** (Converse API with tool use) drives the agent loop.
- A Python/FastAPI service holds the conversation state, scoring and guardrails. Channels and the
  model sit behind adapters, so the whole product also runs offline for testing.
- Infrastructure is defined in CDK: one small instance behind CloudFront, with a $10 budget alert.

## Guardrails (what makes it safe to run on customers)
Consent and channel checks, quiet hours in the customer's time zone, a daily message limit, per-channel
length limits, blocked promises, and a rule that every ₹ amount in a message must come from a pricing
tool. STOP and START are handled before the model runs. Tool failures and model failures end in a
human handoff, never a silent drop.

## Challenges
[Fill in from real experience: WhatsApp template approval, SES sandbox, idempotent webhooks, …]

## Accomplishments
- A complete renewal, from first message to payment, across two channels in one thread
- 58 automated tests, including the whole demo story and the guardrails
- Adapters validated against the real AWS request schemas

## What we learned
[Fill in.]

## What's next
Verify SNS signatures, move state to DynamoDB, add SMS and voice, and A/B test message timing.

## Built with
Python, FastAPI, SQLite, Amazon Bedrock, AWS End User Messaging Social, Amazon SES, Amazon SNS,
AWS CDK, Amazon CloudFront

## Required fields
- ACE opportunity ID: [ask the partner team]
- Demo video (about 3 minutes): [link]
- Repository: https://github.com/Jehal05/AWS
- Architecture diagram: docs/architecture.png
- Live demo URL: [after deployment, otherwise "runs locally, see README"]
- Data: all customers, policies and engagement records are synthetic.

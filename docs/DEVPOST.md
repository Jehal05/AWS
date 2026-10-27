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
- **WhatsApp's 24-hour rule shapes the design.** Free-form text is only allowed inside the window, so
  the proactive opener has to be an approved template and every later reply plain text. We built
  that split into the adapter instead of hoping the first message would be allowed.
- **Keeping a model honest about money.** A renewal message with a wrong premium is worse than no
  message. Every ₹ amount must come from a pricing tool or the send is blocked, and a test proves a
  model that invents "₹9,999" is stopped.
- **Bedrock Converse is strict.** Roles must alternate, the first message must be a user message,
  and tool results have to be merged into one user turn. We wrote an adapter for this and test it
  with a scripted client in the exact response shape.
- **Duplicate and forged events.** SNS can deliver twice and anyone can POST to a URL, so inbound
  events are idempotent, the webhook URL carries a secret, topics are allow-listed and the SNS
  signature is verified.
- **Our own experiment fooled us.** The first version of the channel A/B showed the fixed-email
  group beating the scored group, because simulated customers ignored which channel they were
  contacted on. We changed the simulation, label the result "synthetic" and say it follows from an
  assumption.

## Accomplishments
- A complete renewal, from first message to payment, across two channels in one thread
- 74 automated tests, including the whole demo story, the guardrails and a browser run of the UI
- A 37-message golden set in English, Hinglish and Hindi (`python -m renewflow.eval`)
- A dashboard with zero axe accessibility violations in light and dark themes and on mobile
- Adapters validated against the real AWS request schemas

## What we learned
- Treat every claim about impact as a hypothesis until it is measured. A dashboard number made from
  simulated customers is a demonstration of the measurement, nothing more.
- Put the safety checks (consent, STOP, price integrity) outside the model, so they hold no matter
  which model runs.
- Hindi and Hinglish arrive in the first week of any real WhatsApp pilot in India. They belong in
  the test set from day one.

## What's next
Run the golden set against Bedrock, move state to DynamoDB, add SMS and voice, run a real A/B test on a pilot book of business, and add per-language WhatsApp templates.

## Built with
Python, FastAPI, SQLite, Amazon Bedrock, AWS End User Messaging Social, Amazon SES, Amazon SNS,
AWS CDK, Amazon CloudFront

## Required fields
- ACE opportunity ID: [ask the partner team]
- Demo video (2:29, voice-over, opens with the thumbnail): docs/demo/renewflow-demo.mp4 in the repo. Upload it to YouTube or Vimeo for Devpost and paste the link: [link]
- Video thumbnail: docs/demo/thumbnail.png (1920x1080), also embedded as the mp4 cover
- Subtitles to upload with the video: docs/demo/renewflow-demo.srt
- Repository: https://github.com/Jehal05/AWS
- Architecture diagram: docs/architecture.png
- Gallery images: docs/screenshots/ (7 images at 3:2)
- Live demo URL: [after deployment, otherwise "runs locally, see README"]
- Data: all customers, policies and engagement records are synthetic.

## WhatsApp (Meta) prize: how we use End User Messaging Social

RenewFlow opens each renewal with an approved WhatsApp template through End User Messaging Social
`SendWhatsAppMessage`, then replies in free-form text inside the 24-hour window. Delivery, read and
failure receipts and customer replies return through SNS to our webhook, feed the channel score,
and continue the same conversation thread, including a move to email mid-conversation. Status:
adapters are tested against botocore schemas; a live send needs a Meta-approved number.

## Note on the numbers

Impact figures in the dashboard come from a synthetic 20-customer simulation with no real baseline.
They show the system working, not measured business results.

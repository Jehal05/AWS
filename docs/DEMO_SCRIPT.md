# Demo script (about 3 minutes)

Record the dashboard at 1440×900 in the light theme. Use the demo data (`--reset`) so every run
looks the same. Keep quiet hours **off** for the recording so the first message goes out at once.
Say what is simulated: the line on screen "Synthetic data" stays visible throughout.

| Time | On screen | Say |
|---|---|---|
| 0:00 | Overview, empty state | "Insurers lose renewals to slow, one-size-fits-all reminders. RenewFlow is an agent that chooses the channel, holds the conversation, and knows when to stop." |
| 0:15 | Conversations → Priya Sharma, **Details** tab | "Priya's renewal is up from ₹14,800 to ₹18,400. Her history says she reads WhatsApp and ignores email, so that is where we start. These scores come from her last 90 days, and consent comes first." |
| 0:35 | Press **Start renewal** | "The agent checks the best channel, looks up the policy, sends, and schedules a follow-up. Every step is in the Activity tab." Open **Activity** for two seconds. |
| 0:55 | **Play as customer**, WhatsApp, send "Premium looks higher, can I split it?" | "Now I am Priya. The agent explains exactly why it went up, and offers a quarterly plan. Every rupee amount comes from a pricing tool, never from the model, and a guardrail blocks any number the tools did not produce." |
| 1:25 | Send "Please email me the details" | "She asks for the details by email. Same conversation, new channel, no lost context. See the marker: continued on Email." Switch to the Email tab, open the message. |
| 1:50 | Press **Renew securely**, then **Pay now** | "She pays from the link. The policy is renewed, she gets a receipt on WhatsApp, and the funnel moves." |
| 2:05 | Reply "My claim was rejected, I want to speak to a person" on a second customer | "Claims and complaints are never handled by the bot. It hands over with a summary, then stays silent until a person resolves it." Show **Handoffs**. |
| 2:25 | Send STOP | "STOP revokes consent on every channel immediately. That runs before the model, so it cannot be talked out of it." |
| 2:35 | **Run simulation**, then Overview | "Twenty synthetic customers through the same agent. Renewal rate, revenue secured, what the guardrails blocked, and which channel works for whom." |
| 2:55 | Architecture slide | "Built on End User Messaging Social for WhatsApp, SES for email and Bedrock for the model, with every channel behind an adapter." |

## If AWS is live by recording time
Replace the last line with a real send: show the WhatsApp message arriving on a phone and the SES
email in an inbox, and say which parts are live. Never describe a simulated channel as live.

## Checklist
- [ ] `python -m renewflow --reset`, then reload the page
- [ ] Quiet hours switch is off
- [ ] Browser zoom 100%, notifications silenced
- [ ] Say "synthetic data" once out loud

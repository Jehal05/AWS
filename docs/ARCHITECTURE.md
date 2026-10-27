# RenewFlow architecture

Every diagram below is Mermaid, which GitHub renders in the page. Each one describes what the code
in this repository does today. Where something is designed but not yet run on AWS, the diagram says so.

- [1. System context](#1-system-context)
- [2. Components](#2-components)
- [3. A renewal, end to end](#3-a-renewal-end-to-end)
- [4. Inbound message handling](#4-inbound-message-handling)
- [5. The agent loop](#5-the-agent-loop)
- [6. Guardrails](#6-guardrails)
- [7. Choosing a channel](#7-choosing-a-channel)
- [8. Conversation states](#8-conversation-states)
- [9. Events from AWS](#9-events-from-aws)
- [10. Data model](#10-data-model)
- [11. Deployment on AWS](#11-deployment-on-aws)
- [12. Local mode versus AWS mode](#12-local-mode-versus-aws-mode)

## 1. System context

Who talks to what. Solid arrows are implemented; the AWS side is tested against botocore schemas but
has not yet run against a live account.

```mermaid
flowchart LR
    C(["Customer"])
    OP(["Renewals team"])

    subgraph CH["Customer channels"]
        WA["WhatsApp"]
        EM["Email"]
    end

    subgraph AWS["AWS Communication Developer Services"]
        EUM["End User Messaging Social<br/>SendWhatsAppMessage"]
        SES["Amazon SES v2<br/>SendEmail"]
        SNS["Amazon SNS<br/>renewflow-events"]
    end

    BR["Amazon Bedrock<br/>Converse with tool use"]
    RF["RenewFlow<br/>agent, guardrails, dashboard"]

    C <--> WA
    C <--> EM
    WA <--> EUM
    EM <--> SES
    RF -->|"send"| EUM
    RF -->|"send"| SES
    EUM -->|"replies, receipts"| SNS
    SES -->|"delivery, open, click, bounce"| SNS
    SNS -->|"signed HTTPS POST"| RF
    RF <-->|"reasoning and tool calls"| BR
    OP <-->|"dashboard, handoffs"| RF
```

## 2. Components

The agent only ever sees two small interfaces, `Channel` and `ChatModel`. That is what lets the same
code run locally with a simulator and on AWS with the real services.

```mermaid
flowchart LR
    subgraph IF["Interfaces"]
        UI["Dashboard<br/>vanilla ES modules"]
        WH["SNS webhook"]
    end

    subgraph APP["Application"]
        API["FastAPI<br/>api/app.py"]
        SVC["RenewFlow service<br/>service.py"]
        EVT["AWS event processor<br/>aws/events.py"]
    end

    subgraph AGENT["Agent"]
        ORCH["Orchestrator<br/>agent loop"]
        TOOLS["Six tools<br/>agent/tools.py"]
        GR["Guardrails<br/>checked inside send_message"]
        SCORE["Channel scoring<br/>analytics/scoring.py"]
    end

    subgraph PORTS["Swappable ports"]
        MODEL{{"ChatModel"}}
        CHAN{{"Channel"}}
        MODEL -.-> MOCK["MockModel"]
        MODEL -.-> BED["BedrockModel"]
        CHAN -.-> LOCAL["LocalChannel"]
        CHAN -.-> WAC["AwsWhatsAppChannel"]
        CHAN -.-> SEC["SesEmailChannel"]
    end

    STORE[("SQLite store<br/>WAL")]

    UI --> API
    WH --> API
    API --> SVC
    SVC --> ORCH
    SVC --> EVT
    ORCH --> MODEL
    ORCH --> TOOLS
    TOOLS --> GR
    TOOLS --> SCORE
    TOOLS --> CHAN
    ORCH --> STORE
    TOOLS --> STORE
    EVT --> STORE
    EVT --> ORCH
```

## 3. A renewal, end to end

The demo story with Priya Sharma: the agent opens on WhatsApp, explains the premium, moves the same
conversation to email and she pays.

```mermaid
sequenceDiagram
    autonumber
    actor P as Priya
    participant D as Dashboard
    participant A as Agent
    participant G as Guardrails
    participant WA as WhatsApp
    participant EM as Email

    D->>A: Start renewal
    A->>A: next_best_channel (scores her history)
    Note over A: WhatsApp wins: she reads and replies there
    A->>G: send_message (opener)
    G-->>A: allowed
    A->>WA: opening message
    WA->>P: Your premium is ₹14,800 (last year ₹18,400)

    P->>A: Premium looks higher, can I split it?
    A->>A: lookup_policy, generate_quote (quarterly)
    A->>G: send_message
    G-->>A: allowed (every ₹ amount came from a tool)
    A->>WA: reasons for the increase and 4 payments of ₹4,738
    WA->>P: reply

    P->>A: Please email me the details
    A->>EM: full quote with a secure payment link
    A->>WA: "I've emailed the quote"
    Note over A,EM: Same thread, now across two channels

    P->>EM: opens the email and clicks Renew securely
    EM->>A: read and click events
    P->>A: Pay now
    A->>A: policy renewed, receipt sent
    A->>D: renewal counted on the Overview
```

## 4. Inbound message handling

Compliance rules run before the model does. STOP is never left to a model to interpret.

```mermaid
flowchart TD
    IN(["Customer message<br/>arrives on a channel"]) --> SAVE["Save the message"]
    SAVE --> OPTED{"Conversation<br/>opted out?"}
    OPTED -- yes --> START{"Is it START?"}
    START -- yes --> RESUB["Restore consent<br/>send confirmation"]
    START -- no --> QUIET(["Stay silent"])
    OPTED -- no --> STOP{"Is it STOP, unsubscribe<br/>or similar?"}
    STOP -- yes --> REVOKE["Revoke consent on every channel<br/>confirm once"]
    STOP -- no --> HUMAN{"A person owns<br/>this conversation?"}
    HUMAN -- yes --> PAUSE(["Agent paused,<br/>message waits for the person"])
    HUMAN -- no --> RUN["Run the agent"]
    RUN --> OUT{"Outcome"}
    OUT -- "answered" --> REPLY(["Reply sent"])
    OUT -- "claim, complaint, cancel,<br/>unclear twice, error" --> HAND(["Handoff to a person<br/>with a summary"])
```

## 5. The agent loop

At most 8 model calls per run. Any model or tool failure ends in a handoff rather than silence.

```mermaid
flowchart TD
    S(["Trigger: renewal due<br/>or customer message"]) --> M["Ask the model<br/>what to do next"]
    M --> Q{"Tool calls<br/>requested?"}
    Q -- no --> FIN["Final text, run ends"]
    Q -- yes --> EX["Execute each tool<br/>trace it in the dashboard"]
    EX --> ADD["Add results to the<br/>conversation"]
    ADD --> LIM{"Step limit<br/>reached?"}
    LIM -- no --> M
    LIM -- yes --> ERR["Record: step limit exceeded"]
    M -. "model raises" .-> ERR
    ERR --> ESC["Escalate to a person"]
    FIN --> SENT{"Inbound run and<br/>nothing was sent?"}
    SENT -- yes --> ESC
    SENT -- no --> DONE(["Run complete"])
    ESC --> DONE
```

The six tools are `lookup_policy`, `generate_quote`, `next_best_channel`, `send_message`,
`schedule_followup` and `handoff_to_human`. Each call and its result is stored and shown in the
conversation's Activity tab.

## 6. Guardrails

Every outbound message passes these checks in this order, and the first failure blocks the send and
is recorded. The model cannot skip them because they sit inside the `send_message` tool.

```mermaid
flowchart TD
    A(["send_message called"]) --> C1{"Channel enabled?"}
    C1 -- no --> X1["Blocked: channel_unavailable"]
    C1 -- yes --> C2{"Customer has<br/>consented to it?"}
    C2 -- no --> X2["Blocked: no_consent"]
    C2 -- yes --> C3{"Within the channel's<br/>length limit?"}
    C3 -- no --> X3["Blocked: too_long"]
    C3 -- yes --> C4{"Free of banned<br/>promises?"}
    C4 -- no --> X4["Blocked: prohibited_claim"]
    C4 -- yes --> C5{"Proactive message?"}
    C5 -- yes --> C6{"Outside quiet hours<br/>21:00 to 08:00 local?"}
    C6 -- no --> X5["Blocked: quiet_hours"]
    C6 -- yes --> C7{"Fewer than 2 proactive<br/>messages in 24 h?"}
    C7 -- no --> X6["Blocked: rate_limit"]
    C7 -- yes --> C8
    C5 -- no --> C8{"Every ₹ amount returned<br/>by a pricing tool?"}
    C8 -- no --> X7["Blocked: ungrounded_amount"]
    C8 -- yes --> OK(["Send through the channel"])
```

## 7. Choosing a channel

The score is computed from the customer's own history, weighted toward recent behaviour.

```mermaid
flowchart LR
    H[("90 days of events<br/>delivered, read,<br/>replied, clicked")] --> W["Weight each event<br/>30-day half-life"]
    W --> S["Smooth each rate toward<br/>a prior (Bayesian)<br/>so thin history is not over-trusted"]
    S --> F["Score per channel<br/>read 0.45 + reply 0.30<br/>+ click 0.15 + delivery 0.10"]
    F --> E{"Consent and<br/>channel enabled?"}
    E -- "no" --> N["Not eligible"]
    E -- "yes" --> R["Rank eligible channels"]
    R --> B["Best channel first,<br/>runner-up as fallback,<br/>with a confidence label"]
```

## 8. Conversation states

```mermaid
stateDiagram-v2
    [*] --> open: renewal starts
    open --> open: agent replies
    open --> handoff: claim, complaint, cancel,<br/>unclear twice, or error
    handoff --> open: person resolves it
    open --> opted_out: STOP
    opted_out --> open: START
    open --> renewed: payment completed
    renewed --> [*]
    note right of handoff
        The agent is paused.
        Customer messages are saved
        and wait for a person.
    end note
    note right of opted_out
        Consent revoked on all channels.
        No proactive messages.
    end note
```

## 9. Events from AWS

How replies and delivery receipts get back into the conversation. The signature, the token, the
topic and the host of any subscribe URL are all checked before anything is processed.

```mermaid
sequenceDiagram
    autonumber
    participant AWS as End User Messaging Social / SES
    participant SNS as Amazon SNS
    participant WH as Webhook
    participant EP as Event processor
    participant AG as Agent

    AWS->>SNS: publish event
    SNS->>WH: HTTPS POST to /webhooks/sns/token
    WH->>WH: token matches?
    WH->>WH: topic on the allow-list?
    WH->>WH: SNS signature valid?<br/>cert host is sns.region.amazonaws.com
    alt any check fails
        WH-->>SNS: 404 or 403, nothing processed
    else subscription confirmation
        WH->>SNS: confirm (SubscribeURL host validated)
    else notification
        WH->>EP: process message
        EP->>EP: skip if provider_id already seen
        alt WhatsApp receipt or SES event
            EP->>EP: record delivered, read, click
            Note over EP: permanent bounce or complaint<br/>revokes email consent
        else WhatsApp inbound message
            EP->>AG: handle_inbound(customer, text)
        end
    end
```

## 10. Data model

```mermaid
erDiagram
    CUSTOMERS ||--o{ CONSENTS : grants
    CUSTOMERS ||--o{ POLICIES : holds
    CUSTOMERS ||--o{ THREADS : "talks in"
    POLICIES ||--o{ QUOTES : "priced by"
    THREADS ||--o{ MESSAGES : contains
    THREADS ||--o{ HANDOFFS : escalates
    THREADS ||--o{ AGENT_RUNS : "handled by"
    AGENT_RUNS ||--o{ TOOL_CALLS : makes
    CUSTOMERS ||--o{ EVENTS : generates
    MESSAGES ||--o{ EVENTS : "delivered, read, clicked"
    CUSTOMERS ||--o{ FOLLOWUPS : "scheduled for"

    CUSTOMERS {
        int id PK
        text language
        text timezone
        text persona
    }
    THREADS {
        int id PK
        text status "open, handoff, opted_out, renewed"
    }
    MESSAGES {
        int id PK
        text channel "whatsapp, email, sms"
        text direction "in or out"
        text meta "kind, provider_id"
    }
    EVENTS {
        int id PK
        text type "sent, delivered, read, replied, clicked, renewed, blocked"
    }
    HANDOFFS {
        int id PK
        text reason
        text summary
        text status "open or resolved"
    }
```

## 11. Deployment on AWS

Defined in [`infra/stack.py`](../infra/stack.py) with the CDK. It synthesises and its assertions pass,
but it **has not been deployed**; see [DEPLOY.md](DEPLOY.md). The design keeps cost near $10 for two
weeks: one small instance, no NAT gateway, no load balancer, and a budget alarm.

```mermaid
flowchart TB
    U(["Operators and customers<br/>(payment pages)"]) -->|HTTPS| CF["Amazon CloudFront"]
    CF -->|HTTP origin| EC2

    subgraph VPC["VPC, public subnet only (no NAT gateway)"]
        EC2["EC2 t4g.micro<br/>Amazon Linux 2023<br/>systemd: RenewFlow on port 80"]
    end

    EC2 -->|"converse"| BR["Amazon Bedrock"]
    EC2 -->|"SendEmail"| SES["Amazon SES v2<br/>configuration set: renewflow"]
    EC2 -->|"SendWhatsAppMessage"| EUM["End User Messaging Social"]
    EUM -->|"events"| SNS["SNS topic<br/>renewflow-events"]
    SES -->|"event destination"| SNS
    SNS -->|"HTTPS subscription"| CF

    ROLE["IAM role<br/>bedrock, ses, social-messaging,<br/>ssm:GetParameter"] -.- EC2
    SSM["SSM parameter<br/>/renewflow/base-url"] -.- EC2
    BUD["AWS Budgets<br/>$10, alerts at 50%, 80%, 100%"] -.-> MAIL(["Alert email"])
```

## 12. Local mode versus AWS mode

The same agent runs in both. The dashboard labels each channel "(simulated)" or "(live)" so the two
are never confused.

```mermaid
flowchart LR
    subgraph LOCAL["Local mode: no AWS account needed"]
        direction TB
        L1["Customer simulator<br/>in the dashboard"] --> L2["Agent"]
        L2 --> L3["MockModel"]
        L2 --> L4["LocalChannel"]
        L4 --> L1
    end

    subgraph LIVE["AWS mode"]
        direction TB
        A1["Real customers"] --> A2["EUM Social, SES, SNS"]
        A2 --> A3["Agent"]
        A3 --> A4["BedrockModel"]
        A3 --> A5["AwsWhatsAppChannel<br/>SesEmailChannel"]
        A5 --> A2
    end

    LOCAL -. "RENEWFLOW_MODE=aws<br/>RENEWFLOW_LOCAL_CHANNELS=whatsapp<br/>keeps a channel simulated" .-> LIVE
```

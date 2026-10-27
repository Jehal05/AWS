"""Golden conversations: one customer message each, with the behaviour we expect.

Labels describe what a careful human agent would do, not what the mock happens to do, so the same
set can grade the Bedrock model. Outcomes: optout, handoff, email, pay_link, answer, clarify.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    text: str
    expect: str
    tag: str  # english, hinglish, hindi, angry, vague, claim, cancel, price, optout


CASES: tuple[Case, ...] = (
    # claims and complaints
    Case("My claim was rejected", "handoff", "claim"),
    Case("I want to file a claim for my accident", "handoff", "claim"),
    Case("I will take this to the ombudsman", "handoff", "claim"),
    Case("Claim reject ho gaya, mujhe baat karni hai", "handoff", "hinglish"),
    # cancel, discount, guarantees, fraud, already paid
    Case("I want to cancel my policy", "handoff", "cancel"),
    Case("Mujhe policy cancel karni hai", "handoff", "hinglish"),
    Case("Give me a discount or I will switch insurers", "handoff", "cancel"),
    Case("Can you guarantee no hike next year?", "handoff", "cancel"),
    Case("I already renewed this last week", "handoff", "cancel"),
    Case("Is this a scam?", "handoff", "angry"),
    Case("This is ridiculous, you people are cheats!", "handoff", "angry"),
    Case("Refund my money right now", "handoff", "angry"),
    # asks for a person
    Case("Please connect me to a human", "handoff", "english"),
    Case("I want to speak to a manager", "handoff", "english"),
    Case("मुझे किसी व्यक्ति से बात करनी है", "handoff", "hindi"),
    # opt-out
    Case("STOP", "optout", "optout"),
    Case("Please unsubscribe me", "optout", "optout"),
    Case("stop messaging me", "optout", "optout"),
    Case("Mujhe messages mat bhejo", "optout", "hinglish"),
    # price and explanation questions
    Case("How much is the premium?", "answer", "price"),
    Case("What is my premium?", "answer", "price"),
    Case("Why is my premium higher this year?", "answer", "price"),
    Case("Premium kyun badha?", "answer", "hinglish"),
    Case("Premium kitna hai?", "answer", "hinglish"),
    Case("Can I split it into instalments?", "answer", "price"),
    Case("Can I pay monthly?", "answer", "price"),
    Case("प्रीमियम इतना क्यों बढ़ गया?", "answer", "hindi"),
    # channel switch and payment
    Case("Please email me the details", "email", "english"),
    Case("Send the quote on mail", "email", "english"),
    Case("Send me the payment link", "pay_link", "english"),
    Case("I want to renew, please proceed", "pay_link", "english"),
    Case("Renew kar do, link bhejo", "pay_link", "hinglish"),
    # vague: ask, never push a payment
    Case("ok", "clarify", "vague"),
    Case("yes", "clarify", "vague"),
    Case("hmm", "clarify", "vague"),
    Case("hello", "clarify", "vague"),
    Case("what is this about?", "clarify", "vague"),
)

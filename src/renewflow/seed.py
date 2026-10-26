"""Synthetic demo data: customers, policies, consents and 90 days of engagement history.

Everything here is invented. Emails use the reserved example.com domain and phone numbers are
placeholders; nothing is ever sent to them in local mode.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from .agent.guardrails import tz_for
from .clock import iso
from .store import Store

HERO_ID = 1  # Priya Sharma: the customer the live demo follows

FIRST = ["Rahul", "Ananya", "Vikram", "Neha", "Arjun", "Kavya", "Rohan", "Sneha", "Aditya",
         "Meera", "Karan", "Isha", "Siddharth", "Pooja", "Nikhil", "Divya", "Manish", "Shreya",
         "Amit", "Tanvi", "Harsh", "Riya", "Sanjay", "Swati", "Varun", "Nandini", "Deepak",
         "Ritika", "Yash", "Aarav"]
LAST = ["Patil", "Deshmukh", "Kulkarni", "Mehta", "Iyer", "Nair", "Reddy", "Gupta", "Joshi",
        "Bhosale", "Kapoor", "Singh", "Verma", "Pawar", "Shah", "Menon", "Chavan", "Agarwal",
        "Bhat", "Jadhav"]

PERSONAS = ["whatsapp_first", "email_first", "balanced", "low_engagement"]
PERSONA_WEIGHTS = [40, 25, 15, 20]

# (read, reply, click) probabilities by persona and channel
AFFINITY = {
    "whatsapp_first": {"whatsapp": (.92, .28, .20), "email": (.28, .04, .08), "sms": (.45, .05, .06)},
    "email_first": {"whatsapp": (.30, .05, .06), "email": (.85, .18, .30), "sms": (.35, .03, .04)},
    "balanced": {"whatsapp": (.70, .18, .15), "email": (.65, .12, .20), "sms": (.55, .08, .08)},
    "low_engagement": {"whatsapp": (.25, .04, .04), "email": (.20, .02, .05), "sms": (.30, .03, .04)},
}
CHANNEL_MIX = {
    "whatsapp_first": {"whatsapp": 6, "email": 3, "sms": 1},
    "email_first": {"whatsapp": 3, "email": 6, "sms": 1},
    "balanced": {"whatsapp": 4, "email": 4, "sms": 2},
    "low_engagement": {"whatsapp": 4, "email": 4, "sms": 2},
}

PRODUCTS = [
    {"code": "CAR", "name": "Comprehensive car insurance", "weight": 50,
     "assets": ["Hyundai Creta", "Maruti Swift", "Tata Nexon", "Honda City", "Kia Seltos",
                "Mahindra XUV300", "Toyota Innova"],
     "premium": (9000, 34000), "insured": (450000, 1250000), "ncb": (0, 50),
     "reasons": ["Vehicle value recalculated", "No-claim bonus reduced",
                 "Third-party tariff revision"]},
    {"code": "TWO", "name": "Two-wheeler insurance", "weight": 25,
     "assets": ["Honda Activa", "TVS Jupiter", "Royal Enfield Classic", "Bajaj Pulsar",
                "Suzuki Access"],
     "premium": (1500, 5200), "insured": (40000, 140000), "ncb": (0, 50),
     "reasons": ["Vehicle value recalculated", "No-claim bonus reduced",
                 "Third-party tariff revision"]},
    {"code": "HLT", "name": "Family health insurance", "weight": 25,
     "assets": ["Family floater, 4 members", "Family floater, 3 members",
                "Individual plan", "Family floater, 2 members"],
     "premium": (12000, 46000), "insured": (500000, 1000000), "ncb": (0, 0),
     "reasons": ["Age-band change", "Medical cost inflation adjustment", "Add-on pricing update"]},
]

HERO_HISTORY = {  # deterministic, so the demo always opens on a clear signal
    "whatsapp": dict(sent=9, delivered=9, read=8, replied=3, clicked=2),
    "email": dict(sent=4, delivered=4, read=1, replied=0, clicked=0),
    "sms": dict(sent=2, delivered=2, read=1, replied=0, clicked=0),
}


def _plate(rng: random.Random) -> str:
    letters = "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(2))
    return f"MH{rng.choice([12, 14, 15, 20])} {letters} {rng.randint(1000, 9999)}"


def _history_rows(cid, channel, when, delivered, read, replied, clicked, rng):
    rows = [(cid, None, None, channel, "sent", "{}", iso(when))]
    if delivered:
        rows.append((cid, None, None, channel, "delivered", "{}", iso(when + timedelta(seconds=2))))
    read_at = when + timedelta(minutes=rng.randint(1, 600))
    if read:
        rows.append((cid, None, None, channel, "read", "{}", iso(read_at)))
    if replied:
        rows.append((cid, None, None, channel, "replied", "{}",
                     iso(read_at + timedelta(minutes=rng.randint(1, 120)))))
    if clicked:
        rows.append((cid, None, None, channel, "clicked", "{}",
                     iso(read_at + timedelta(minutes=rng.randint(0, 30)))))
    return rows


def _persona_history(cid: int, persona: str, now: datetime, rng: random.Random):
    mix = CHANNEL_MIX[persona]
    rows = []
    for _ in range(rng.randint(6, 14)):
        channel = rng.choices(list(mix), weights=list(mix.values()))[0]
        read_p, reply_p, click_p = AFFINITY[persona][channel]
        delivered = rng.random() < (0.95 if channel == "email" else 0.97)
        read = delivered and rng.random() < read_p
        replied = read and rng.random() < reply_p
        clicked = read and rng.random() < click_p
        when = now - timedelta(days=rng.uniform(2, 88), minutes=rng.randint(0, 600))
        rows += _history_rows(cid, channel, when, delivered, read, replied, clicked, rng)
    return rows


def _hero_history(cid: int, now: datetime, rng: random.Random):
    rows = []
    for channel, spec in HERO_HISTORY.items():
        for i in range(spec["sent"]):
            when = now - timedelta(days=3 + i * 9 + (2 if channel == "email" else 0), hours=2)
            rows += _history_rows(
                cid, channel, when, i < spec["delivered"], i < spec["read"],
                i < spec["replied"], i < spec["clicked"], rng,
            )
    return rows


def _policy_fields(rng: random.Random, product: dict, expiry_days: int, today, idx: int) -> dict:
    prev = int(round(rng.randint(*product["premium"]), -2))
    new = int(round(prev * rng.uniform(1.04, 1.28), -2))
    delta = new - prev
    a = int(round(delta * rng.uniform(0.3, 0.5), -1))
    b = int(round(delta * rng.uniform(0.25, 0.4), -1))
    amounts = [a, b, delta - a - b]
    asset = rng.choice(product["assets"])
    if product["code"] != "HLT":
        asset = f"{asset} · {_plate(rng)}"
    return {
        "policy_number": f"RF-{product['code']}-2026-{idx:05d}",
        "product": product["name"],
        "asset": asset,
        "expiry_date": (today + timedelta(days=expiry_days)).isoformat(),
        "premium_prev": prev,
        "premium_new": new,
        "sum_insured": int(round(rng.randint(*product["insured"]), -3)),
        "ncb_percent": rng.choice(range(product["ncb"][0], product["ncb"][1] + 1, 5)),
        "increase_reasons": [{"label": l, "amount": amt} for l, amt in zip(product["reasons"], amounts)],
    }


def seed_demo(store: Store, count: int = 40, rng_seed: int = 42) -> dict[str, int]:
    rng = random.Random(rng_seed)
    now = store.clock.now()
    today = now.astimezone(tz_for("Asia/Kolkata")).date()
    pairs = [(f, l) for f in FIRST for l in LAST]
    rng.shuffle(pairs)
    event_rows: list[tuple] = []

    for i in range(count):
        first, last = ("Priya", "Sharma") if i == 0 else pairs[i]
        persona = "whatsapp_first" if i == 0 else rng.choices(PERSONAS, weights=PERSONA_WEIGHTS)[0]
        cid = store.add_customer(
            name=f"{first} {last}",
            email=f"{first}.{last}{i + 1}@example.com".lower(),
            phone=f"+91 90000 {i + 1:05d}",
            persona=persona,
        )
        wa, em, sms = (True, True, True) if i == 0 else (
            rng.random() < 0.92, rng.random() < 0.95, rng.random() < 0.70)
        if not (wa or em):
            wa = True
        for channel, ok in (("whatsapp", wa), ("email", em), ("sms", sms)):
            store.set_consent(cid, channel, ok)

        if i == 0:
            fields = dict(
                policy_number="RF-CAR-2026-00001", product="Comprehensive car insurance",
                asset="Hyundai Creta · MH12 AB 4821",
                expiry_date=(today + timedelta(days=14)).isoformat(),
                premium_prev=14800, premium_new=18400, sum_insured=950000, ncb_percent=20,
                increase_reasons=[
                    {"label": "Vehicle value recalculated", "amount": 1500},
                    {"label": "No-claim bonus reduced", "amount": 1400},
                    {"label": "Third-party tariff revision", "amount": 700},
                ],
            )
            event_rows += _hero_history(cid, now, rng)
        else:
            product = rng.choices(PRODUCTS, weights=[p["weight"] for p in PRODUCTS])[0]
            fields = _policy_fields(rng, product, rng.randint(3, 28), today, i + 1)
            event_rows += _persona_history(cid, persona, now, rng)
        store.add_policy(cid, **fields)

    store.db.executemany(
        "INSERT INTO events (customer_id, thread_id, message_id, channel, type, meta, ts)"
        " VALUES (?,?,?,?,?,?,?)",
        event_rows,
    )
    store._bump()
    return {"customers": count, "history_events": len(event_rows)}

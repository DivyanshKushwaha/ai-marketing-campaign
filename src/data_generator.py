import random
from uuid import uuid4

import pendulum
from faker import Faker

from utils import EVENTS_PATH, PRODUCTS_PATH, data

fake = Faker()
CATEGORIES = ["flowers", "cakes", "chocolates", "hampers", "perfumes", "combos"]
OCCASIONS = ["birthday", "anniversary", "mothers_day", "valentines", "eid", "christmas", "diwali", "womens_day"]
TIMEZONES = ["Asia/Dubai", "Asia/Kolkata", "America/Toronto"]
RECIPIENTS = [("Mom", "mother"), ("Dad", "father"), ("Sarah", "partner"), ("Ahmed", "friend")]


def _catalogue() -> list[dict]:
    out = []
    for i in range(100):
        cat = CATEGORIES[i % 6]
        out.append({
            "sku": f"ZUV-{i+1:04d}",
            "name": f"{fake.word().title()} {cat[:-1]}",
            "category": cat,
            "price_aed": round(random.uniform(80, 650), 2),
            "occasion_tags": random.sample(OCCASIONS, k=3),
            "cultural_flags": {"alcohol_free": True, "halal": i % 5 != 0, "vegan": cat in {"flowers", "chocolates"}},
            "available": True,
        })
    return out


def _events(total: int = 500, customers: int = 50) -> list[dict]:
    start = pendulum.now("UTC").subtract(months=14)
    events, meta = [], {}
    for c in range(customers):
        cid = f"cust_{c:03d}"
        meta[cid] = {"tz": TIMEZONES[c % 3], "recipients": RECIPIENTS if c % 7 == 0 else [RECIPIENTS[c % 4]]}

    while len(events) < total:
        cid = f"cust_{random.randint(0, customers - 1):03d}"
        m = meta[cid]
        ts = start.add(days=random.randint(0, 420), hours=random.randint(8, 20)).in_timezone(m["tz"])
        kind = random.choices(["order", "browse", "whatsapp_interaction", "profile_update"], weights=[45, 30, 15, 10])[0]

        if kind == "order":
            recipient, rel = random.choice(m["recipients"])
            sku = f"ZUV-{random.randint(1, 100):04d}"
            if random.random() < 0.35 and len(events) < total - 1:
                events.append({
                    "event_id": str(uuid4()), "customer_id": cid, "event_type": "browse",
                    "timestamp": ts.subtract(hours=random.randint(1, 48)).to_iso8601_string(),
                    "data": {"page_url": f"https://zuvees.ae/products/{sku}", "product_sku": sku,
                             "category": random.choice(CATEGORIES), "time_spent_seconds": random.randint(30, 240)},
                })
            events.append({
                "event_id": str(uuid4()), "customer_id": cid, "event_type": "order", "timestamp": ts.to_iso8601_string(),
                "data": {
                    "order_id": str(uuid4()),
                    "line_items": [{"sku": sku, "name": "Gift item", "price": random.uniform(90, 500), "category": random.choice(CATEGORIES)}],
                    "occasion_tag": random.choice(OCCASIONS), "recipient_name": recipient,
                    "recipient_relationship": rel, "total_aed": round(random.uniform(120, 800), 2), "delivery_area": fake.city(),
                },
            })
        elif kind == "browse":
            sku = f"ZUV-{random.randint(1, 100):04d}"
            events.append({
                "event_id": str(uuid4()), "customer_id": cid, "event_type": "browse", "timestamp": ts.to_iso8601_string(),
                "data": {"page_url": f"https://zuvees.ae/products/{sku}", "product_sku": sku,
                         "category": random.choice(CATEGORIES), "time_spent_seconds": random.randint(20, 300)},
            })
        elif kind == "whatsapp_interaction":
            events.append({
                "event_id": str(uuid4()), "customer_id": cid, "event_type": "whatsapp_interaction", "timestamp": ts.to_iso8601_string(),
                "data": {"direction": random.choice(["inbound", "outbound"]), "template_name": "campaign_update",
                         "read": random.random() > 0.35, "opted_out": random.random() < 0.08},
            })
        else:
            r, _ = random.choice(m["recipients"])
            events.append({
                "event_id": str(uuid4()), "customer_id": cid, "event_type": "profile_update", "timestamp": ts.to_iso8601_string(),
                "data": {"field": random.choice(["birthday", "anniversary"]),
                         "value": pendulum.now().add(days=random.randint(5, 120)).date().isoformat(), "recipient_name": r},
            })

    events.sort(key=lambda e: e["timestamp"])
    return events[:total]


def generate_data(force: bool = False) -> dict:
    try:
        need_p = force or not PRODUCTS_PATH.exists() or PRODUCTS_PATH.stat().st_size == 0
        need_e = force or not EVENTS_PATH.exists() or EVENTS_PATH.stat().st_size == 0
        if need_p:
            data.save_json(PRODUCTS_PATH, _catalogue())
        if need_e:
            data.save_json(EVENTS_PATH, _events())
        return {
            "success": True,
            "message": None,
            "data": {"events_generated": need_e, "products_generated": need_p},
        }
    except Exception as exc:
        return {"success": False, "message": str(exc), "data": None}

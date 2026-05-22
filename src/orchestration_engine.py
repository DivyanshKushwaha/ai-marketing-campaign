import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from uuid import uuid4

import pendulum

from message_engine import generate_channel_message
from models import CampaignSend, ConsentStatus, Event, FatigueCheck, OccasionDetection, Product

logger = logging.getLogger(__name__)

DEFAULT_HOUR = {"email": 8, "whatsapp": 19, "push": 12}
QUIET = set(range(23, 24)) | set(range(0, 6))
_RANK = {"high": 3, "medium": 2, "low": 1}
_TZ_MAP = {-4: "America/Toronto", 4: "Asia/Dubai", 5.5: "Asia/Kolkata"}
_SEGMENT_HOURS = {
    "uae": {"email": 20, "whatsapp": 10, "push": 12},
    "india": {"email": 9, "whatsapp": 19, "push": 12},
    "americas": {"email": 8, "whatsapp": 19, "push": 12},
}


def _assignment_scheduling(
    events: list[Event],
    occasions: list[OccasionDetection],
    now: pendulum.DateTime,
) -> tuple[list[OccasionDetection], dict[str, dict]]:
    """High-confidence wins per customer-week; 7-day promo count; segment cold-start hours."""
    cutoff = now.subtract(days=7)
    customer: dict[str, dict] = {}
    for e in events:
        cid = e.customer_id
        if cid not in customer:
            customer[cid] = {"offsets": [], "count": 0, "promo_7d": 0}
        customer[cid]["count"] += 1
        ts = pendulum.instance(e.timestamp)
        try:
            customer[cid]["offsets"].append(ts.utcoffset().total_seconds() / 3600)
        except Exception:
            pass
        if (
            ts >= cutoff
            and e.event_type == "whatsapp_interaction"
            and e.data.get("direction") == "outbound"
        ):
            customer[cid]["promo_7d"] += 1

    ctx: dict[str, dict] = {}
    for cid, d in customer.items():
        off = max(set(d["offsets"]), key=d["offsets"].count) if d["offsets"] else 4.0
        seg = "india" if off == 5.5 else "americas" if off <= -4 else "uae"
        ctx[cid] = {
            "tz": _TZ_MAP.get(off, "Asia/Dubai"),
            "segment_hours": _SEGMENT_HOURS[seg],
            "promo_7d": d["promo_7d"],
            "event_count": d["count"],
        }
    for o in occasions:
        ctx.setdefault(
            o.customer_id,
            {"tz": "Asia/Dubai", "segment_hours": _SEGMENT_HOURS["uae"], "promo_7d": 0, "event_count": 0},
        )

    best: dict[tuple, OccasionDetection] = {}
    for o in occasions:
        key = (o.customer_id, o.predicted_date.isocalendar()[:2])
        if key not in best or _RANK[o.confidence] > _RANK[best[key].confidence]:
            best[key] = o
    eligible = sorted(best.values(), key=lambda o: _RANK[o.confidence], reverse=True)
    return eligible, ctx


def _consent(events: list[Event], customer_id: str) -> ConsentStatus:
    whatsapp = True
    for e in events:
        if e.customer_id == customer_id and e.event_type == "whatsapp_interaction":
            if e.data.get("opted_out"):
                whatsapp = False
    return ConsentStatus(whatsapp=whatsapp)


def _stats(events: list[Event], customer_id: str) -> dict:
    browses = wa_reads = wa_total = 0
    for e in events:
        if e.customer_id != customer_id:
            continue
        if e.event_type == "browse":
            browses += 1
        if e.event_type == "whatsapp_interaction":
            wa_total += 1
            if e.data.get("read"):
                wa_reads += 1
    return {"email_opens": browses, "whatsapp_read_rate": wa_reads / wa_total if wa_total else 0}


def _pick_channel(consent: ConsentStatus, stats: dict) -> str | None:
    if stats["email_opens"] == 0 and stats["whatsapp_read_rate"] > 0.6 and consent.whatsapp:
        return "whatsapp"
    if consent.whatsapp and stats["whatsapp_read_rate"] >= 0.4:
        return "whatsapp"
    if consent.email:
        return "email"
    return "push" if consent.push else None


def _send_time(
    occasion: OccasionDetection,
    channel: str,
    events: list[Event],
    cust_ctx: dict | None = None,
) -> pendulum.DateTime:
    tz = cust_ctx["tz"] if cust_ctx else "Asia/Dubai"
    hours = []
    for e in events:
        if e.customer_id != occasion.customer_id:
            continue
        ts = pendulum.instance(e.timestamp).in_timezone(tz)
        if channel == "email" and e.event_type == "browse":
            hours.append(ts.hour)
        if channel == "whatsapp" and e.event_type == "whatsapp_interaction" and e.data.get("read"):
            hours.append(ts.hour)
        if channel == "push" and e.event_type == "order":
            hours.append(ts.hour)

    if cust_ctx and cust_ctx["event_count"] < 3:
        hour = cust_ctx["segment_hours"][channel]
    else:
        hour = max(set(hours), key=hours.count) if hours else DEFAULT_HOUR[channel]
    days = (occasion.predicted_date - pendulum.now(tz).date()).days
    if days <= 2:
        hour = min(hour, 10)
    if channel == "email":
        hour = min(hour, 11)
    elif channel == "whatsapp":
        hour = max(hour, 17)
    while hour in QUIET:
        hour = (hour + 1) % 24

    local = pendulum.now(tz).replace(hour=hour, minute=0, second=0, microsecond=0)
    if days > 0:
        local = local.add(days=min(days, 7))
    return local.in_timezone("UTC")


def build_campaign_schedule(
    occasions: list[OccasionDetection],
    events: list[Event],
    products: list[Product],
) -> dict:
    try:
        if not occasions:
            logger.error("Campaign scheduling failed: no occasions provided")
            return {"success": False, "message": "no occasions", "data": None}

        now = pendulum.now("UTC")
        eligible, cust_ctx = _assignment_scheduling(events, occasions, now)
        sends: list[CampaignSend] = []
        weekly: dict[str, int] = defaultdict(int)
        skipped = {"fatigue": 0, "consent": 0, "message": 0}
        consent_cache: dict[str, ConsentStatus] = {}
        stats_cache: dict[str, dict] = {}
        planned: list[tuple] = []

        for occasion in eligible:
            cid = occasion.customer_id
            c = cust_ctx[cid]
            if c["promo_7d"] + weekly[cid] >= 2:
                skipped["fatigue"] += 1
                continue
            if cid not in consent_cache:
                consent_cache[cid] = _consent(events, cid)
                stats_cache[cid] = _stats(events, cid)
            consent = consent_cache[cid]
            channel = _pick_channel(consent, stats_cache[cid])
            if not channel or not getattr(consent, channel):
                skipped["consent"] += 1
                continue

            ctx = {
                "customer_id": cid,
                "occasion": occasion.occasion,
                "predicted_date": occasion.predicted_date.isoformat(),
                "recipient_name": occasion.recipient_name,
                "recipient_relationship": occasion.recipient_relationship,
                "confidence": occasion.confidence,
            }
            planned.append((occasion, channel, consent, ctx, c))
            weekly[cid] += 1

        if planned:
            workers = min(12, len(planned))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(generate_channel_message, ch, ctx, products): (occ, ch, consent, ctx, c)
                    for occ, ch, consent, ctx, c in planned
                }
                for future in as_completed(futures):
                    occasion, channel, consent, ctx, c = futures[future]
                    msg_result = future.result()
                    if not msg_result["success"]:
                        skipped["message"] += 1
                        logger.warning(
                            "Skipped send for %s/%s: %s",
                            occasion.customer_id,
                            occasion.occasion,
                            msg_result.get("message"),
                        )
                        continue
                    sends.append(
                        CampaignSend(
                            send_id=str(uuid4()),
                            customer_id=occasion.customer_id,
                            channel=channel,
                            scheduled_send_time=_send_time(occasion, channel, events, c),
                            occasion=occasion.occasion,
                            confidence_score=occasion.confidence,
                            message=msg_result["data"]["message"],
                            reasoning=f"{occasion.confidence} confidence {occasion.occasion} via {channel}.",
                            consent_status=consent,
                            fatigue_check=FatigueCheck(
                                messages_this_week=c["promo_7d"] + weekly[occasion.customer_id],
                                within_limit=c["promo_7d"] + weekly[occasion.customer_id] <= 2,
                            ),
                        )
                    )

        if any(skipped.values()):
            logger.warning("Scheduling skips: %s", skipped)
        logger.info(
            "Campaign schedule built: %d sends from %d occasions",
            len(sends),
            len(occasions),
        )
        return {"success": True, "message": None, "data": {"schedule": sends, "count": len(sends)}}

    except Exception as exc:
        logger.error("Campaign scheduling failed: %s", exc, exc_info=True)
        return {"success": False, "message": str(exc), "data": None}

import logging
from collections import defaultdict
from datetime import date, timedelta

from hijri_converter import Gregorian

from models import Event, OccasionDetection

logger = logging.getLogger(__name__)


def _next_gregorian(month: int, day: int, today: date) -> date:
    d = date(today.year, month, day)
    return d if d > today else date(today.year + 1, month, day)


def _next_hijri(hijri_month: int, hijri_day: int, today: date) -> date:
    probe = today
    for _ in range(400):
        h = Gregorian(probe.year, probe.month, probe.day).to_hijri()
        if h.month == hijri_month and h.day == hijri_day and probe > today:
            return probe
        probe += timedelta(days=1)
    return today + timedelta(days=30)


def detect_occasions(events: list[Event]) -> dict:
    try:
        if not events:
            logger.error("Occasion detection failed: empty event list")
            return {"success": False, "message": "no events", "data": None}

        today = date.today()

        out: list[OccasionDetection] = []

        customer_events: dict[str, list] = defaultdict(list)

        order_patterns: dict[tuple, list] = defaultdict(list)

        browse_patterns: dict[tuple, int] = defaultdict(int)

        recipient_relationships: dict[tuple, dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )

        for e in sorted(events, key=lambda x: x.timestamp):
            customer_events[e.customer_id].append(e)

        for customer_id, rows in customer_events.items():

            # -------------------------
            # Profile updates
            # -------------------------
            for e in rows:
                if e.event_type != "profile_update":
                    continue

                d = e.data

                try:
                    predicted = date.fromisoformat(d["value"][:10])
                except (KeyError, ValueError) as exc:
                    logger.warning(
                        "Skipping invalid profile_update for %s: %s",
                        customer_id,
                        exc,
                    )
                    continue

                if predicted <= today:
                    predicted = predicted.replace(year=today.year + 1)

                recipient_name = d.get("recipient_name")

                inferred_relationship = None

                if recipient_name:
                    relationship_counts = recipient_relationships.get(
                        (customer_id, recipient_name),
                        {},
                    )
                    if relationship_counts:
                        inferred_relationship = max(
                            relationship_counts,
                            key=relationship_counts.get,
                        )

                out.append(
                    OccasionDetection(
                        customer_id=customer_id,
                        occasion=d.get("field", "birthday"),
                        predicted_date=predicted,
                        confidence="high",
                        evidence=[
                            f"Profile update saved {d.get('field')} for {recipient_name}"
                        ],
                        recipient_name=recipient_name,
                        recipient_relationship=inferred_relationship,
                        calendar_type="gregorian",
                    )
                )

            # -------------------------
            # Order pattern extraction
            # -------------------------
            for e in rows:
                if e.event_type != "order":
                    continue

                data = e.data

                occasion = data.get("occasion_tag")

                if not occasion:
                    continue

                recipient_name = data.get("recipient_name")
                relationship = data.get("recipient_relationship")

                if recipient_name and relationship:
                    recipient_relationships[
                        (customer_id, recipient_name)
                    ][relationship] += 1

                key = (
                    customer_id,
                    occasion,
                    recipient_name,
                )

                order_patterns[key].append(e)

            # -------------------------
            # Browse patterns
            # -------------------------
            for e in rows:
                if e.event_type != "browse":
                    continue

                category = e.data.get("category")

                if category:
                    browse_patterns[(customer_id, category)] += 1

        # -------------------------
        # Occasion inference from orders
        # -------------------------
        for key, order_events in order_patterns.items():

            customer_id, occasion, recipient = key

            latest = max(order_events, key=lambda x: x.timestamp)

            months = {e.timestamp.month for e in order_events}

            recurring = len(months) >= 2

            relationship_counts = recipient_relationships.get(
                (customer_id, recipient),
                {},
            )

            inferred_relationship = (
                max(relationship_counts, key=relationship_counts.get)
                if relationship_counts
                else None
            )

            evidence = [
                f"{len(order_events)} historical order(s) detected",
            ]

            if recipient:
                evidence.append(f"Recipient: {recipient}")

            if inferred_relationship:
                evidence.append(
                    f"Inferred relationship: {inferred_relationship}"
                )

            if recurring:
                evidence.append(
                    "Recurring seasonal gifting pattern detected"
                )

            out.append(
                OccasionDetection(
                    customer_id=customer_id,
                    occasion=occasion,
                    predicted_date=_next_gregorian(
                        latest.timestamp.month,
                        min(28, latest.timestamp.day),
                        today,
                    ),
                    confidence="medium" if recurring else "low",
                    evidence=evidence,
                    recipient_name=recipient,
                    recipient_relationship=inferred_relationship,
                    calendar_type="gregorian",
                )
            )

        # -------------------------
        # Hijri occasion generation
        # -------------------------
        for customer_id in customer_events:
            for occasion_name, hijri_month, hijri_day in [
                ("eid_al_fitr", 10, 1),
                ("eid_al_adha", 12, 10),
            ]:
                out.append(
                    OccasionDetection(
                        customer_id=customer_id,
                        occasion=occasion_name,
                        predicted_date=_next_hijri(
                            hijri_month,
                            hijri_day,
                            today,
                        ),
                        confidence="medium",
                        evidence=[
                            f"Hijri calendar projection for {occasion_name}"
                        ],
                        recipient_name=None,
                        recipient_relationship=None,
                        calendar_type="hijri",
                    )
                )

        # -------------------------
        # Browse intent inference
        # -------------------------
        occasion_by_category = {
            "flowers": "mothers_day",
            "cakes": "birthday",
            "perfumes": "anniversary",
        }

        for (customer_id, category), count in browse_patterns.items():

            if count < 3:
                continue

            occasion = occasion_by_category.get(category)

            if not occasion:
                continue

            out.append(
                OccasionDetection(
                    customer_id=customer_id,
                    occasion=occasion,
                    predicted_date=_next_gregorian(3, 8, today),
                    confidence="low",
                    evidence=[
                        f"Frequent browsing interest in {category}",
                        f"{count} browse events detected",
                    ],
                    recipient_name=None,
                    recipient_relationship=None,
                    calendar_type="gregorian",
                )
            )

        # -------------------------
        # Deduplication
        # -------------------------
        unique = []
        seen = set()

        for item in out:

            if item.predicted_date <= today:
                continue

            key = (
                item.customer_id,
                item.occasion,
                item.recipient_name,
                str(item.predicted_date),
            )

            if key in seen:
                continue

            seen.add(key)
            unique.append(item)

        logger.info(
            "Occasion detection complete: %d occasions from %d events",
            len(unique),
            len(events),
        )

        return {
            "success": True,
            "message": None,
            "data": {
                "occasions": unique,
                "count": len(unique),
            },
        }

    except Exception as exc:
        logger.error("Occasion detection failed: %s", exc, exc_info=True)

        return {
            "success": False,
            "message": str(exc),
            "data": None,
        }
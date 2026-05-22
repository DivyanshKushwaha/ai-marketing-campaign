import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def pytest_configure(config):
    os.environ["COVERAGE_FILE"] = os.path.join(
        tempfile.gettempdir(), "ai_marketing_coverage"
    )

from models import CulturalFlags, Event, Product  # noqa: E402


@pytest.fixture(autouse=True)
def mock_llm(monkeypatch):
    import utils

    def fake_complete(messages, json_mode=True):
        sys_msg = messages[0]["content"] if messages else ""
        user_ctx = {}
        if len(messages) > 1 and messages[1].get("role") == "user":
            try:
                user_ctx = json.loads(messages[1]["content"])
            except json.JSONDecodeError:
                pass
        occasion = user_ctx.get("occasion", "special_day")
        recipient = user_ctx.get("recipient_name") or "your loved one"
        occasion_label = occasion.replace("_", " ")
        slug = occasion.lower().replace(" ", "_")

        # Match on prompt markdown titles (not filenames — those are not in file bodies).
        if "WhatsApp template message" in sys_msg:
            content = json.dumps(
                {
                    "template_body": (
                        f"Hi {{1}}, {{2}} is coming up. We've picked thoughtful gifts for {{3}}. "
                        "Reply STOP to opt out."
                    ),
                    "variables": [recipient, occasion_label, recipient],
                    "has_opt_out_footer": True,
                }
            )
        elif "Push notification" in sys_msg:
            text = (
                f"{recipient}'s {occasion_label} — elegant picks await "
                f"app://occasion/{slug}"
            )[:150]
            content = json.dumps(
                {"text": text, "deep_link": f"app://occasion/{slug}"}
            )
        elif "Email campaign message" in sys_msg:
            content = json.dumps(
                {
                    "subject": f"Something special for {recipient}"[:80],
                    "body": (
                        f"{occasion_label.title()} is almost here — a thoughtful moment "
                        f"to celebrate {recipient}.\n\n"
                        "We've curated elegant gifts at Zuvees, crafted with care.\n\n"
                        "Explore zuvees.ae when you're ready."
                    ),
                }
            )
        else:
            content = json.dumps(
                {
                    "subject": "A thoughtful moment awaits",
                    "body": "Warm wishes from Zuvees.",
                }
            )
        return {"content": content, "cost": 0.0, "model": "mock"}

    monkeypatch.setattr(utils.llm, "enabled", True)
    monkeypatch.setattr(utils.llm, "complete", fake_complete)


@pytest.fixture
def sample_products():
    return [
        Product(
            sku="FLW001",
            name="Blush Serenity Birthday Bloom Box",
            category="flowers",
            price_aed=210.0,
            occasion_tags=["birthday", "eid"],
            cultural_flags=CulturalFlags(alcohol_free=True, halal=True, vegan=True),
            available=True,
        )
    ]


@pytest.fixture
def sample_events():
    tz = timezone.utc
    return [
        Event(
            event_id="e1",
            customer_id="cust_001",
            event_type="profile_update",
            timestamp=datetime(2025, 6, 1, 10, 0, 0, tzinfo=tz),
            data={"field": "birthday", "value": "2026-08-10", "recipient_name": "Mom"},
        ),
        Event(
            event_id="e2",
            customer_id="cust_001",
            event_type="order",
            timestamp=datetime(2025, 3, 8, 14, 0, 0, tzinfo=tz),
            data={
                "order_id": "o1",
                "line_items": [{"sku": "FLW001", "name": "Bloom", "price": 210.0, "category": "flowers"}],
                "occasion_tag": "mothers_day",
                "recipient_name": "Mom",
                "recipient_relationship": "mother",
                "total_aed": 210.0,
                "delivery_area": "Dubai Marina",
            },
        ),
        Event(
            event_id="e3",
            customer_id="cust_001",
            event_type="order",
            timestamp=datetime(2026, 3, 8, 15, 0, 0, tzinfo=tz),
            data={
                "order_id": "o2",
                "line_items": [{"sku": "FLW001", "name": "Bloom", "price": 210.0, "category": "flowers"}],
                "occasion_tag": "mothers_day",
                "recipient_name": "Mom",
                "recipient_relationship": "mother",
                "total_aed": 220.0,
                "delivery_area": "Dubai Marina",
            },
        ),
        Event(
            event_id="e4",
            customer_id="cust_002",
            event_type="browse",
            timestamp=datetime(2026, 4, 1, 9, 0, 0, tzinfo=tz),
            data={"page_url": "/flowers", "product_sku": "FLW001", "category": "flowers", "time_spent_seconds": 90},
        ),
        Event(
            event_id="e5",
            customer_id="cust_002",
            event_type="whatsapp_interaction",
            timestamp=datetime(2026, 4, 2, 20, 0, 0, tzinfo=tz),
            data={"direction": "outbound", "template_name": "eid_campaign", "read": True, "opted_out": True},
        ),
    ]


@pytest.hookimpl(trylast=True)
def pytest_terminal_summary(terminalreporter, exitstatus, config):
    passed = len(terminalreporter.stats.get("passed", []))
    failed = len(terminalreporter.stats.get("failed", [])) + len(
        terminalreporter.stats.get("error", [])
    )
    categories = {
        "occasion_detection": {"passed": 0, "failed": 0},
        "message_engine": {"passed": 0, "failed": 0},
        "orchestration": {"passed": 0, "failed": 0},
        "outputs": {"passed": 0, "failed": 0},
    }
    for outcome in ("passed", "failed", "error"):
        for rep in terminalreporter.stats.get(outcome, []):
            name = rep.nodeid.split("::")[-1]
            if name.startswith("test_occasion"):
                key = "occasion_detection"
            elif name.startswith("test_message"):
                key = "message_engine"
            elif name.startswith("test_orchestration"):
                key = "orchestration"
            else:
                key = "outputs"
            categories[key]["passed" if outcome == "passed" else "failed"] += 1

    coverage_pct = 0.0
    cov_plugin = config.pluginmanager.get_plugin("_cov")
    if cov_plugin is not None and getattr(cov_plugin, "cov_total", None) is not None:
        coverage_pct = round(cov_plugin.cov_total, 1)

    out = {
        "total_tests": passed + failed,
        "passed": passed,
        "failed": failed,
        "coverage_percent": coverage_pct,
        "categories": categories,
    }
    (ROOT / "outputs").mkdir(exist_ok=True)
    (ROOT / "outputs" / "test-results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

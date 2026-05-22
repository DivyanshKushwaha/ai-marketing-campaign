import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from message_engine import generate_channel_message
from occassion_engine import detect_occasions
from orchestration_engine import build_campaign_schedule
from models import CampaignMessage, EmailMessage, OccasionDetection, WhatsAppMessage

ROOT = Path(__file__).resolve().parent.parent


def test_occasion_empty_fails():
    assert not detect_occasions([])["success"]


def test_message_unknown_channel():
    assert not generate_channel_message("sms", {})["success"]


def test_occasion_detection_rules(sample_events):
    result = detect_occasions(sample_events)
    assert result["success"]
    occasions = result["data"]["occasions"]
    assert len(occasions) >= 1
    assert any(o.confidence == "high" for o in occasions)
    assert any(o.confidence in ("medium", "low") for o in occasions)
    assert any(o.calendar_type == "hijri" for o in occasions)
    assert all(o.predicted_date > date.today() for o in occasions)
    assert all(o.evidence for o in occasions)
    mom = [o for o in occasions if o.customer_id == "cust_001" and o.recipient_name == "Mom"]
    assert len({o.occasion for o in mom}) >= 1


def test_message_engine_constraints(sample_products):
    ctx = {"customer_id": "cust_001", "occasion": "birthday", "recipient_name": "Mom"}
    wa = generate_channel_message("whatsapp", ctx, sample_products)
    assert wa["success"]
    body = wa["data"]["message"].whatsapp
    assert len(body.template_body) <= 1024
    assert len(body.variables) <= 3
    assert body.has_opt_out_footer
    assert "reply stop to opt out" in body.template_body.lower()

    push = generate_channel_message("push", ctx, sample_products)
    assert len(push["data"]["message"].push.text) <= 150
    assert push["data"]["message"].push.deep_link.startswith("app://")

    bad = generate_channel_message("email", {**ctx, "occasion": "eid"}, sample_products)
    blob = json.dumps(bad["data"]["output"]).lower()
    assert "discount" not in blob


def test_orchestration_fatigue_consent(sample_events, sample_products, monkeypatch):
    def fake_msg(channel, context, products=None, _retry_unsafe=True):
        msg = (
            CampaignMessage(email=EmailMessage(subject="S", body="Warm note."))
            if channel == "email"
            else CampaignMessage(
                whatsapp=WhatsAppMessage(
                    template_body="Hi {{1}}. Reply STOP to opt out.",
                    variables=["Mom"],
                    has_opt_out_footer=True,
                )
            )
        )
        return {
            "success": True,
            "message": None,
            "data": {"message": msg, "output": {}, "model": "mock", "cost": 0.0},
        }

    monkeypatch.setattr("orchestration_engine.generate_channel_message", fake_msg)
    occasions = [
        OccasionDetection(
            customer_id="cust_001",
            occasion="birthday",
            predicted_date=date(2026, 8, 10),
            confidence="high",
            evidence=["profile"],
            recipient_name="Mom",
            calendar_type="gregorian",
        ),
        OccasionDetection(
            customer_id="cust_001",
            occasion="mothers_day",
            predicted_date=date(2026, 5, 12),
            confidence="low",
            evidence=["inferred"],
            recipient_name="Mom",
            calendar_type="gregorian",
        ),
        OccasionDetection(
            customer_id="cust_001",
            occasion="eid_al_fitr",
            predicted_date=date(2026, 6, 15),
            confidence="low",
            evidence=["hijri"],
            calendar_type="hijri",
        ),
    ]
    result = build_campaign_schedule(occasions, sample_events, sample_products)
    sends = result["data"]["schedule"]
    assert result["success"]
    assert len([s for s in sends if s.customer_id == "cust_001"]) <= 2
    for s in sends:
        assert getattr(s.consent_status, s.channel)
        assert s.fatigue_check.within_limit


def test_utils_and_pipeline(monkeypatch):
    from data_generator import generate_data
    from pipeline import run_pipeline
    from utils import CAMPAIGN_OUTPUT_PATH, OCCASIONS_OUTPUT_PATH, data

    real_save = data.save_json

    def guarded_save(path, payload):
        if path in (CAMPAIGN_OUTPUT_PATH, OCCASIONS_OUTPUT_PATH):
            return
        real_save(path, payload)

    monkeypatch.setattr(data, "save_json", guarded_save)

    assert generate_data()["success"]
    assert len(data.load_events()) >= 500
    assert len(data.load_products()) == 100
    assert data.parse_json_from_llm('{"subject":"Hi","body":"There"}')["subject"] == "Hi"

    result = run_pipeline()
    assert result["success"]
    assert result["data"]["campaign_sends"] >= 30


def test_output_files_schema():
    for name in (
        "occasion_detection_results.json",
        "campaign_schedule.json",
    ):
        path = ROOT / "outputs" / name
        assert path.exists(), f"missing {name}"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, list) and len(data) >= 30

    occ = json.loads((ROOT / "outputs/occasion_detection_results.json").read_text())
    send = json.loads((ROOT / "outputs/campaign_schedule.json").read_text())
    assert {"high", "medium", "low"} & {o["confidence"] for o in occ}
    row = send[0]
    assert row["send_id"] and row["channel"] in ("email", "whatsapp", "push")
    assert row["consent_status"] and row["fatigue_check"]
    assert "message" in row

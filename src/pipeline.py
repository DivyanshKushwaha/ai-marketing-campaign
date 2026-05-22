import json
from datetime import date, datetime

from data_generator import generate_data
from occassion_engine import detect_occasions
from orchestration_engine import build_campaign_schedule
from utils import CAMPAIGN_OUTPUT_PATH, OCCASIONS_OUTPUT_PATH, OUTPUT_DIR, data


def run_pipeline() -> dict:
    try:
        gen = generate_data()
        if not gen["success"]:
            return gen

        events = data.load_events()
        products = data.load_products()

        occ = detect_occasions(events)
        if not occ["success"]:
            return occ

        occasions = occ["data"]["occasions"]
        data.save_json(OCCASIONS_OUTPUT_PATH, [
            {**o.model_dump(mode="json"), "predicted_date": o.predicted_date.isoformat()} for o in occasions
        ])

        sched = build_campaign_schedule(occasions, events, products)
        if not sched["success"]:
            return sched

        rows = []
        for s in sched["data"]["schedule"]:
            row = s.model_dump(mode="json")
            row["scheduled_send_time"] = s.scheduled_send_time.isoformat()
            rows.append(row)
        data.save_json(CAMPAIGN_OUTPUT_PATH, rows)

        return {
            "success": True,
            "message": None,
            "data": {
                "occasions": len(occasions),
                "campaign_sends": len(rows),
                "outputs_dir": str(OUTPUT_DIR),
            },
        }
    except Exception as exc:
        return {"success": False, "message": str(exc), "data": None}

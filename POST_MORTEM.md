# Post-Mortem: If I Had Two More Weeks

A short reflection on what I would do next, in priority order, and where the current build is strong versus incomplete.

---

## What I would prioritise (and why)

**1. Close the measurement loop (highest product impact)**  
The pipeline produces campaigns but does not yet learn whether they worked. I would add lightweight **attribution**: tie each `send_id` to downstream events (browse → order within 7/14 days, WhatsApp read/reply, opt-out). That enables **ROI-style reporting** (cost per incremental order, channel lift) and moves send-time and channel rules off proxies like browse count alone.

**2. A/B testing and feedback loops (second)**  
I would run **holdout or variant prompts** per channel (e.g. two email subjects per occasion segment) and feed results back into prompt selection—not only one-shot LLM output. A minimal loop: schedule variants → log impressions/outcomes → pick a weekly prompt winner. That is how the system would improve over time instead of only generating copy once.

**3. Automated quality report (third)**  
I would add a small evaluator that samples sends and scores detection coverage, message safety pass rate, and schedule rule compliance, then writes a structured report alongside `test-results.json`. That gives me a repeatable QA step before each release.

**4. Production-shaped data path (light touch)**  
A **database** (e.g. Postgres) for events, occasions, and a send ledger—with idempotent inserts and a proper batch ingest pipeline—would replace monolithic JSON reads. I would keep the current engines and swap `utils.Data` for repositories. Real ops need this, but it comes after knowing whether messages perform.

**5. Further hardening (fourth)**  
Real email open/click fields in the event stream, a maintained Hijri library (`hijridate`) with edge-case tests, and optional ranked occasion scoring once attribution exists. Fatigue and cold-start already use `_assignment_scheduling()` (7-day outbound WhatsApp count, high-confidence wins per customer-week, segment default hours); I would extend that with a true cross-run send ledger.

---

## Where I am honest about gaps

| Area | Current state | Limitation |
|------|----------------|------------|
| Send-time | Per-channel hours from events + segment defaults for cold-start | Browse still proxies email engagement; no delivery performance data |
| Fatigue | 7-day outbound WhatsApp + cap of 2 planned sends per run | No persistent history of past campaign runs |
| Occasion detection | Rule-based, explainable | Browse→occasion mapping is heuristic |
| Messaging | LLM + safety + fallbacks | Fallback copy can mask prompt or API failures in logs |
| Data | 50 customers, 500 events, validated integrity | Seasonal tags are not tightly aligned to Feb/Dec calendars |

---

## What I would not do first

- More channels or dashboards before attribution exists.  
- Larger synthetic datasets without fixing feedback loops—volume does not fix wrong channel rules.  
- Replacing rule-based detection with a black-box model before I have labelled evaluation data.

---

## Summary

This submission is a **credible offline MVP**: detect → generate → optimise → schedule, with Docker and automated tests. It is **not** yet a learning system. With two more weeks I would focus on **attribution and A/B feedback**, then **automated QA reporting**, then a **thin DB + ingest layer**, so product decisions are evidence-led rather than heuristic-led.

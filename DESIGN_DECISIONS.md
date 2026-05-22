# Design Decisions

Numbered decisions for this marketing automation pipeline, with explicit trade-offs. I favoured a **reproducible offline deliverable** over production completeness.

---

1. **File-based batch pipeline instead of microservices or a database**

   - **Decision:** Ingest `data/synthetic_events.json` and `data/product_catalogue.json`, run engines in one Python process, write results to `outputs/`.
   - **Why:** Matches the project scope, keeps `docker-compose up` reproducible, and avoids extra infrastructure.
   - **Trade-off:** No incremental ingest, no send ledger across runs, limited scale beyond ~500 customers without redesign.

2. **In-memory handoff between detection and scheduling**

   - **Decision:** `pipeline.py` passes the occasion list directly into `build_campaign_schedule()`; `occasion_detection_results.json` is written for inspection but not read back for scheduling.
   - **Why:** Simpler control flow and one consistent snapshot per run.
   - **Trade-off:** Rescheduling from saved detection alone requires re-running detection.

3. **Rule-based occasion detection with Hijri projection, not an ML model**

   - **Decision:** `occassion_engine.py` uses profile dates (high confidence), order recurrence (medium/low), fixed Hijri Eid anchors, and browse thresholds.
   - **Why:** Explainable evidence strings, deterministic tests, no training pipeline.
   - **Trade-off:** Weaker on noisy or sparse behavioural data; browse→occasion mapping is heuristic (category → fixed occasion).

4. **LiteLLM + markdown prompts instead of a hosted prompt platform**

   - **Decision:** Channel prompts in `prompts/*.md`; runtime JSON user payload; `response_format: json_object`.
   - **Why:** Version-controlled prompts and a swappable model via `LLM_MODEL`.
   - **Trade-off:** No built-in prompt A/B registry or online versioning.

5. **Code-level safety filters after LLM generation**

   - **Decision:** Regex bans, Eid alcohol/pork checks, catalogue-aware hallucination heuristic, channel length limits, one retry then fallback templates.
   - **Why:** LLMs can violate brand and cultural rules for UAE gifting.
   - **Trade-off:** False positives on unusual copy; fallbacks are generic if prompts or API fail.

6. **Always-complete schedule via message fallbacks**

   - **Decision:** On LLM/prompt errors, `message_engine` logs an error but returns `success: True` with `_fallback_output()`.
   - **Why:** Orchestration can still produce a full schedule when some calls fail.
   - **Trade-off:** Output JSON may look fine while logs show degraded copy.

7. **Fatigue and precedence via `_assignment_scheduling()`**

   - **Decision:** One helper filters occasions so **high confidence wins** per customer per ISO week; fatigue uses **outbound WhatsApp in the last 7 days** plus at most **two planned sends** in the current run.
   - **Why:** Matches the campaign rules spec without a separate rules engine file.
   - **Trade-off:** No cross-run send ledger; 7-day count is inferred from events, not from prior `campaign_schedule.json` runs.

8. **WhatsApp-only opt-out from events; email/push consent default to true**

   - **Decision:** `_consent()` disables WhatsApp when `opted_out` is set on `whatsapp_interaction`; email and push stay enabled unless channel selection excludes them.
   - **Why:** Synthetic data only models WhatsApp opt-out explicitly.
   - **Trade-off:** Not full multi-channel consent management for production GDPR-style flows.

9. **Browse count as email engagement proxy for channel selection**

   - **Decision:** `_stats()` treats browse events as `email_opens`; WhatsApp read rate drives WhatsApp preference.
   - **Why:** The event schema has no dedicated email-open events.
   - **Trade-off:** Channel mix can be wrong for customers who browse but do not behave like email openers.

10. **Send-time: segment cold-start + behavioural hours**

    - **Decision:** `_assignment_scheduling()` sets region segment hours (e.g. UAE WhatsApp 10:00, email 20:00) when a customer has fewer than three events; otherwise `_send_time()` uses per-channel hour modes from browses, reads, and orders, with urgency and quiet-hour clamps.
    - **Why:** Covers cold-start and timezone-aware delivery without a separate ML model.
    - **Trade-off:** Segment is inferred from UTC offset, not explicit age/gender in the data.

11. **Parallel LLM calls (up to 12 workers) for message generation**

    - **Decision:** `ThreadPoolExecutor` in `orchestration_engine` for planned sends.
    - **Why:** Reduces wall-clock time when the API key is set and many occasions qualify.
    - **Trade-off:** Rate limits and cost spikes at scale; no queue or backoff.

12. **Minimal test surface with mocked LLM and ≥80% coverage gate**

    - **Decision:** Seven pytest tests, autouse `llm.complete` mock, `outputs/test-results.json` summary; tests do not overwrite pipeline output JSON.
    - **Why:** Automated checks without API cost on every CI run.
    - **Trade-off:** No live LLM integration tests; generator paths are lightly covered when committed data already exists.

13. **Committed synthetic data over generator-only workflow**

    - **Decision:** Ship curated `synthetic_events.json` (500 events / 50 customers) and `product_catalogue.json` (100 SKUs); `data_generator.py` runs only if files are empty.
    - **Why:** Stable runs and documented patterns in [data/DATA_GENERATION.md](data/DATA_GENERATION.md).
    - **Trade-off:** Generator SKUs (`ZUV-*`) differ from the curated catalogue unless both files are regenerated together.

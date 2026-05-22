# Synthetic Data Generation

How I built **`data/synthetic_events.json`** and **`data/product_catalogue.json`**, how I validated them, and where the dataset is strong versus where I would improve it next.

---

## Purpose

The pipeline needs realistic customer behaviour—not random JSON—to exercise:

- **Occasion detection** (profile dates, repeat orders, Hijri Eid, browse patterns)
- **Channel and send-time logic** (timezone offsets, WhatsApp reads, browses, 7-day fatigue proxy)
- **Message safety** (halal / alcohol-free catalogue flags for Eid)

The **committed files in `data/`** are the source of truth for `docker-compose up`. `src/data_generator.py` only runs if a file is missing or empty (Faker-based seed); it did **not** produce the current Zuvees-style catalogue (`FLW*` / `CKE*` SKUs).

---

## How the committed data was produced

### `product_catalogue.json` (hand-curated)

- **100 SKUs** with prefixes by category (`FLW`, `CKE`, `CHC`, `HMP`, `PRF`, `CMB`).
- Names and `occasion_tags` inspired by luxury UAE gifting (birthday, Eid, Diwali, Valentine’s, corporate, etc.).
- **`cultural_flags`** on every row: `alcohol_free`, `halal`, `vegan` (with intentional exceptions—e.g. champagne-style cakes with `halal: false`—so Eid filtering in `message_engine` is testable).
- **`available: false`** on a small number of items for catalogue edge cases.

### `synthetic_events.json` (structured synthetic, not uniform noise)

- **500 events** across **50 customers** (`cust_000` … `cust_049`).
- Event types weighted toward commerce: browse (183), order (178), WhatsApp (99), profile_update (40).
- **Per-customer timezone** via ISO timestamps with fixed offsets (see below).
- **Browse-before-order sessions:** for many orders, a browse on the same `product_sku` appears **1–48 hours before** the order timestamp (same pattern as `data_generator.py` when it runs).
- **Recipients** on orders and profile updates (`recipient_name`, `recipient_relationship`) for relationship clustering in `occassion_engine.py`.
- **Delivery areas** mix UAE, India, and Canada-style localities (e.g. Dubai Marina, Gurugram, Scarborough) aligned with timezone bands.
- **Outbound WhatsApp** events in the stream support the orchestration layer’s 7-day promotional message count for fatigue.

---

## Validation (local checks on committed JSON)

| Criterion | Target | Measured result | Pass? |
|-----------|--------|-----------------|-------|
| Unique customers | 50 `customer_id`s | **50** | Yes |
| Temporal span | ≥ 12 months | **~15.1 months** (2025-02-14 → 2026-05-20) | Yes |
| Seasonal spikes | Feb / Valentine’s; Dec / holidays | **Partial** — see note below | Partial |
| Cultural diversity (timezones) | ≥ 3 timezone bands | **3 offsets:** UTC−4 (151), UTC+4 (183), UTC+5:30 (166) | Yes |
| Temporal integrity | No browse after order (same SKU, same session) | **0** violations within 48h; **117/178** orders have prior browse | Yes |
| Catalogue size | 100 SKUs | **100** | Yes |
| All 6 categories | flowers, cakes, chocolates, hampers, perfumes, combos | **All present** | Yes |
| `cultural_flags` | On all products | **100 / 100** | Yes |

### Seasonal realism (honest assessment)

**Strengths**

- Volume is not flat: some months cluster higher (e.g. 2025-03 and 2026-03 ~67–69 events vs ~31/month average).
- February and December each have **28 events**—a mild calendar lift.
- March order volume is the strongest signal (**62 orders**), which fits spring / Mother’s Day gifting in the Gulf and diaspora mix.
- Product and order tags include `valentines`, `christmas`, `eid`, `diwali`, `ramadan`, etc.

**Weaknesses I would improve**

- Valentine’s tagging in February is soft: only **2** February orders use `love_romance`; more appear in other months.
- December has only **1** order with `christmas` as `occasion_tag`, though the catalogue includes Christmas SKUs.
- Some February orders use tags like `christmas` or `mothers_day`—realistic CRM noise, but not tight calendar conditioning.

**Bottom line:** The data is diverse and temporally valid. Seasonal structure shows up more in **volume and March gifting** than in strict Feb/Dec ↔ `occasion_tag` alignment.

---

## Timezone and cultural diversity

Timestamps use explicit numeric offsets:

| UTC offset | Approx. region | Event count |
|------------|----------------|-------------|
| −4 | Americas (e.g. Toronto) | 151 |
| +4 | Gulf (UAE) | 183 |
| +5:30 | India | 166 |

`orchestration_engine._assignment_scheduling()` maps these to IANA zones and segment default send hours (UAE, India, Americas). Orders use **delivery_area** strings (11 unique areas) consistent with those bands.

---

## Temporal integrity (browse vs order)

For the same customer and product, a browse must not appear **after** an order in the same shopping session.

1. **Committed data:** Browse precedes order on the same SKU where both exist; I found **zero** order→browse violations within 48 hours on the same SKU.
2. **Generator:** When an order is created, ~35% of the time a browse is inserted **1–48 hours before** the order on the same `product_sku`.

---

## Product catalogue summary

| Category | SKU count | Notes |
|----------|-----------|--------|
| flowers | 25 | Eid, Diwali, Christmas, Valentine’s naming |
| cakes | 17 | Halal Eid cakes and some non-halal items for safety tests |
| chocolates | 17 | Halal / date-filled options |
| hampers | 17 | Corporate and festive bundles |
| perfumes | 12 | Premium gifting |
| combos | 12 | Cross-category |

- **`cultural_flags`:** 100% populated; ~87 SKUs `halal: true`, remainder deliberately non-halal for negative tests.
- **`occasion_tags`:** Multiple tags per SKU for occasion-aware messaging.

---

## Optional generator (`src/data_generator.py`)

If JSON files are empty, `generate_data()` seeds:

| Parameter | Default |
|-----------|---------|
| Events | 500 |
| Customers | 50 |
| Time span | ~14 months backward from run time |
| Timezones | `Asia/Dubai`, `Asia/Kolkata`, `America/Toronto` (rotating) |
| Event mix | order 45%, browse 30%, WhatsApp 15%, profile 10% |

Regenerating only events would break SKU alignment (`ZUV-*` vs `FLW*`) unless both files are regenerated together.

---

## Design choices in the data

1. **Repeat gifting patterns** — Same customer can repeat `occasion_tag` across months for medium/low confidence inference.
2. **Profile updates** — 40 events with future dates for high-confidence detections.
3. **WhatsApp** — Read/unread mix and opt-out flags for consent and fatigue logic.
4. **Imperfect tags** — Mirrors messy production CRM data; weakens strict seasonal alignment.
5. **SKU alignment** — Events reference catalogue SKUs (e.g. `CKE010`) so orders and browses join cleanly.

---

## Planned improvements

- Calendar-conditioned generation: more `valentines` / `love_romance` in February and `christmas` / `eid` density in Dec/Ramadan windows.
- Explicit `session_id` on browse/order pairs.
- Database-backed ingest with constraints (see [POST_MORTEM.md](../POST_MORTEM.md)).

---

## Files

| File | Records | Role |
|------|---------|------|
| `data/synthetic_events.json` | 500 events, 50 customers | Behavioural input |
| `data/product_catalogue.json` | 100 SKUs | Catalogue + cultural flags |
| `src/data_generator.py` | — | Fallback seed only |

See also [README.md](../README.md) (Synthetic Data Design) and [DESIGN_DECISIONS.md](../DESIGN_DECISIONS.md) (decision #13).

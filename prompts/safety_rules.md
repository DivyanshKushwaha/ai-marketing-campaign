# Content safety rules (post-generation validation)

## Brand voice
- Luxury, warm, thoughtful — never desperate or discount-led.
- Reject if message contains (case-insensitive): DISCOUNT, SALE, % OFF, CHEAP, LAST CHANCE, LIMITED TIME, BUY NOW.

## Product accuracy
- Only reference product names or SKUs present in the provided catalogue.
- Do not invent products, prices, or categories.

## Cultural sensitivity
- Eid / Ramadan: no alcohol, pork, or non-halal product references; prefer halal-flagged SKUs only.
- Diwali: respectful tone; avoid alcohol-forward gifting unless catalogue item is explicitly appropriate.

## Channel constraints
- WhatsApp: max 1024 characters, max 3 template variables, must end with opt-out footer: "Reply STOP to opt out."
- Push: max 150 characters including deep link placeholder `app://occasion/{occasion_slug}`.
- Email: personal tone; no creepy over-analysis of order counts.

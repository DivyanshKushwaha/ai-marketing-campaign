import json
import logging
import re

from models import CampaignMessage, EmailMessage, Product, PushMessage, WhatsAppMessage
from utils import data, llm

logger = logging.getLogger(__name__)

PROMPT_MAP = {
    "email": "email_prompt.md",
    "whatsapp": "whatsapp_prompt.md",
    "push": "push_prompt.md",
}
BANNED = re.compile(r"\b(discount|sale|cheap|last chance|buy now|% off)\b", re.I)


def _fallback_output(channel: str, context: dict) -> dict:
    occasion = context.get("occasion", "special_day")
    recipient = context.get("recipient_name") or "your loved one"
    if channel == "email":
        return {
            "subject": f"A thoughtful moment for {recipient}",
            "body": (
                f"{occasion.replace('_', ' ').title()} is approaching.\n\n"
                f"Explore elegant gifting ideas at zuvees.ae."
            ),
        }
    if channel == "whatsapp":
        return {
            "template_body": (
                "Hi {{1}}, {{2}} is near. Gifts for {{3}} await. \n\n Reply STOP to opt out."
            ),
            "variables": ["there", occasion.replace("_", " "), recipient],
            "has_opt_out_footer": True,
        }
    slug = occasion.lower().replace(" ", "_")
    return {
        "text": f"{recipient}'s {occasion.replace('_', ' ')} — gifts app://occasion/{slug}"[:150],
        "deep_link": f"app://occasion/{slug}",
    }


def _build_message(channel: str, output: dict, context: dict) -> tuple[CampaignMessage, str]:
    if channel == "email":
        output.setdefault("subject", "A thoughtful moment awaits")
        output.setdefault("body", "")
        message = CampaignMessage(email=EmailMessage(**output))
        blob = f"{output['subject']} {output['body']}".lower()
    elif channel == "whatsapp":
        output.setdefault("template_body", "")
        output.setdefault("variables", [])
        output.setdefault("has_opt_out_footer", True)
        if "reply stop to opt out" not in output["template_body"].lower():
            output["template_body"] += " Reply STOP to opt out."
        output["variables"] = output["variables"][:3]
        message = CampaignMessage(whatsapp=WhatsAppMessage(**output))
        blob = output["template_body"].lower()
    else:
        slug = context.get("occasion", "special_day").lower().replace(" ", "_")
        output.setdefault("deep_link", f"app://occasion/{slug}")
        output.setdefault("text", "")
        if len(output["text"]) > 150:
            output["text"] = output["text"][:150]
        message = CampaignMessage(push=PushMessage(**output))
        blob = output["text"].lower()
    return message, blob


def _is_unsafe(blob: str, context: dict, safe_products: list[Product]) -> bool:
    if BANNED.search(blob):
        return True
    if "eid" in context.get("occasion", "").lower() and re.search(
        r"\b(wine|beer|vodka|alcohol|pork)\b", blob, re.I
    ):
        return True
    known = {p.name.lower() for p in safe_products}
    unknown = [
        p for p in re.findall(r"\b[A-Z][a-zA-Z]+\s[A-Z][a-zA-Z]+\b", blob)
        if p.lower() not in known
    ]
    return len(unknown) >= 3


def generate_channel_message(
    channel: str,
    context: dict,
    products: list[Product] | None = None,
    _retry_unsafe: bool = True,
) -> dict:
    if channel not in PROMPT_MAP:
        logger.error("Unknown channel: %s", channel)
        return {"success": False, "message": f"unknown channel: {channel}", "data": None}

    try:
        safe_products = [p for p in (products or []) if p.available]
        if products and "eid" in context.get("occasion", "").lower():
            safe_products = [p for p in safe_products if p.cultural_flags.halal and p.cultural_flags.alcohol_free]

        enriched_context = {
            **context,
            "top_products": [{"name": p.name, "category": p.category} for p in safe_products[:5]],
            "top_product_name": safe_products[0].name if safe_products else None,
            "past_occasion_tags": list({tag for p in safe_products[:10] for tag in p.occasion_tags}),
        }

        if not llm.enabled:
            logger.warning("LLM disabled (no API key); using fallback for channel=%s", channel)
            output, model, cost = _fallback_output(channel, context), "fallback", 0.0
        else:
            result = llm.complete([
                {"role": "system", "content": data.load_prompt(PROMPT_MAP[channel])},
                {"role": "user", "content": json.dumps(enriched_context, default=str)},
            ])
            output = data.parse_json_from_llm(result["content"])
            model, cost = result["model"], result["cost"]

        message, blob = _build_message(channel, output, context)

        if _is_unsafe(blob, context, safe_products):
            if _retry_unsafe:
                logger.warning(
                    "Unsafe content for %s/%s; retrying with fallback",
                    context.get("customer_id"),
                    context.get("occasion"),
                )
                return generate_channel_message(channel, context, products=None, _retry_unsafe=False)
            logger.error(
                "Message safety check failed for channel=%s customer=%s",
                channel,
                context.get("customer_id"),
            )
            return {"success": False, "message": "content safety check failed", "data": None}

        logger.info(
            "Generated %s message for %s (model=%s, cost=%.4f)",
            channel,
            context.get("customer_id"),
            model,
            cost,
        )
        return {
            "success": True,
            "message": None,
            "data": {"channel": channel, "message": message, "output": output, "model": model, "cost": cost},
        }

    except Exception as exc:
        logger.error(
            "Message generation failed for channel=%s customer=%s: %s",
            channel,
            context.get("customer_id"),
            exc,
            exc_info=True,
        )
        output = _fallback_output(channel, context)
        return {
            "success": True,
            "message": str(exc),
            "data": {
                "channel": channel,
                "message": _build_message(channel, output, context)[0],
                "output": output,
                "model": "fallback",
                "cost": 0.0,
            },
        }

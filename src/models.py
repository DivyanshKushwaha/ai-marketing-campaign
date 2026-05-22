from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CulturalFlags(BaseModel):
    alcohol_free: bool = True
    halal: bool = True
    vegan: bool = False


class Product(BaseModel):
    sku: str
    name: str
    category: Literal[
        "flowers", "cakes", "chocolates", "hampers", "perfumes", "combos"
    ]
    price_aed: float
    occasion_tags: list[str] = Field(default_factory=list)
    cultural_flags: CulturalFlags
    available: bool = True


class Event(BaseModel):
    event_id: str
    customer_id: str
    event_type: Literal["order", "browse", "whatsapp_interaction", "profile_update"]
    timestamp: datetime
    data: dict[str, Any]


class OccasionDetection(BaseModel):
    customer_id: str
    occasion: str
    predicted_date: date
    confidence: Literal["high", "medium", "low"]
    evidence: list[str]
    recipient_name: str | None = None
    recipient_relationship: str | None = None
    calendar_type: Literal["gregorian", "hijri"]


class EmailMessage(BaseModel):
    subject: str
    body: str


class WhatsAppMessage(BaseModel):
    template_body: str
    variables: list[str]
    has_opt_out_footer: bool


class PushMessage(BaseModel):
    text: str
    deep_link: str


class CampaignMessage(BaseModel):
    email: EmailMessage | None = None
    whatsapp: WhatsAppMessage | None = None
    push: PushMessage | None = None


class ConsentStatus(BaseModel):
    email: bool = True
    whatsapp: bool = True
    push: bool = True


class FatigueCheck(BaseModel):
    messages_this_week: int
    within_limit: bool


class CampaignSend(BaseModel):
    send_id: str
    customer_id: str
    channel: Literal["email", "whatsapp", "push"]
    scheduled_send_time: datetime
    occasion: str
    confidence_score: Literal["high", "medium", "low"]
    message: CampaignMessage
    reasoning: str
    consent_status: ConsentStatus
    fatigue_check: FatigueCheck

import json
import os
import re
from pathlib import Path

import litellm
from dotenv import load_dotenv

from models import Event, Product

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
OUTPUT_DIR = ROOT_DIR / "outputs"
PROMPTS_DIR = ROOT_DIR / "prompts"
EVENTS_PATH = DATA_DIR / "synthetic_events.json"
PRODUCTS_PATH = DATA_DIR / "product_catalogue.json"
OCCASIONS_OUTPUT_PATH = OUTPUT_DIR / "occasion_detection_results.json"
CAMPAIGN_OUTPUT_PATH = OUTPUT_DIR / "campaign_schedule.json"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")


class Llm:
    """Shared LiteLLM OpenAI client — import `llm` from utils anywhere."""

    def __init__(self) -> None:
        self.model = LLM_MODEL
        self.api_key = OPENAI_API_KEY
        self.enabled = bool(OPENAI_API_KEY)
    def complete(self, messages: list[dict], json_mode: bool = True) -> dict:
        kwargs: dict = {"model": self.model, "messages": messages, "api_key": self.api_key}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = litellm.completion(**kwargs)
        return {
            "content": response.choices[0].message.content,
            "cost": float(litellm.completion_cost(completion_response=response) or 0.0),
            "model": self.model,
        }


class Data:
    """Prompts, JSON I/O, and catalogue/event loading."""

    def load_prompt(self, name: str) -> str:
        return (PROMPTS_DIR / name).read_text(encoding="utf-8")

    def parse_json_from_llm(self, text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        return json.loads(text)

    def load_events(self) -> list[Event]:
        raw = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
        return [Event(**item) for item in raw]

    def load_products(self) -> list[Product]:
        raw = json.loads(PRODUCTS_PATH.read_text(encoding="utf-8"))
        return [Product(**item) for item in raw]

    def save_json(self, path: Path, payload: list | dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


llm = Llm()
data = Data()

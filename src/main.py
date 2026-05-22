import logging
import sys
from pathlib import Path
from utils import OPENAI_API_KEY

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline import run_pipeline  # noqa: E402

if __name__ == "__main__":
    logging.info(f"OPENAI_API_KEY: {OPENAI_API_KEY[:10]}")
    print(run_pipeline())

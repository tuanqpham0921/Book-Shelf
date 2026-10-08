import logging
from pathlib import Path

from config import FilesLocationConstants

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(FilesLocationConstants.PROMPTS_DIR)

# The generic argument parser, shared by the nodes without a prompt of their own
FILL_SCHEMA_ARGS_PROMPT_PATH = "common/prompts/fill_schema_args.txt"


def load_prompt(prompt_path: str) -> str:
    full_path = PROMPTS_DIR / Path(prompt_path)
    if not full_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {full_path}")
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read().strip()


def format_prompt(prompt_path: str, **kwargs) -> str:
    template = load_prompt(prompt_path)
    try:
        return template.format(**kwargs)
    except KeyError as e:
        raise ValueError(f"Missing required variable for prompt {prompt_path}: {e}")

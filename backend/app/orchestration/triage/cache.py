"""The dev plan cache — replay a recorded plan instead of calling the planner.

Its own file because it is the part of triage marked for removal: deleting it
is this file plus the one call in `executor.py`, with nothing else to untangle.
"""

import logging

from app.domains.planjane import PlanJaneOutput
from common.utils.json_handler import load_json
from config import FilesLocationConstants

logger = logging.getLogger(__name__)

# TODO: remove for prod
CACHE_DIR = FilesLocationConstants.PROJECT_ROOT / "playground" / "files" / "cache"
cache_mapping = {
    "Show me books similar to Pride and Prejudice": "Show me books similar to Pride and Prejudice",
    "Find books like 1984 or Brave New World": "Find books like 1984 or Brave New World",
    "Find books like 1984 or Brave New World, Dune, Brave New World": "Find books like 1984 or Brave New World, Dune, Brave New World",
}


def load_cached_parse_output(user_text: str) -> PlanJaneOutput | None:
    """Replay a recorded plan instead of calling the LLM, for the messages in
    cache_mapping. None when there is no usable entry, so the caller falls
    through to the real planner. The files are whole triage record dumps."""
    file_name = cache_mapping.get(user_text)
    if not file_name:
        return None

    data = load_json(file_name, path=CACHE_DIR)
    if not isinstance(data, dict):
        return None

    try:
        return PlanJaneOutput.model_validate(data)
    except Exception as e:
        logger.warning(f"Could not replay cached plan {file_name}: {e}")
        return None

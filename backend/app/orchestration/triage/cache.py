"""The plan cache — replay a recorded plan instead of calling the planner.

Served in every environment: the files sit beside this module under `app/`,
which is what the image copies, so production replays them too.

Its own file so that deleting it is this file, `files/` and the one call in
`executor.py`, with nothing else to untangle.
"""

import logging
from pathlib import Path

from app.domains.planjane import PlanJaneOutput
from common.utils.json_handler import load_json

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / "files"
# message → file name in CACHE_DIR (without .json)
cache_mapping = {
    "Show me books similar to Pride and Prejudice": "Show me books similar to Pride and Prejudice",
}


def load_cached_parse_output(user_text: str) -> PlanJaneOutput | None:
    """Replay a recorded plan instead of calling the LLM, for the messages in
    cache_mapping. None when there is no usable entry, so the caller falls
    through to the real planner. The files are bare `PlanJaneOutput` dumps."""
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

"""Run triage's query decomposition on messages typed at the command line.

No suite, no grading — for poking at the prompt with a message before it is
worth a case. Goes through the eval's own `decompose`, so it sends exactly
what a turn sends.

Usage (from backend/, or `make try-decomposition Q="..."`):
    poetry run python evals/triage/try_decomposition.py "hi! books like Dune"
    poetry run python evals/triage/try_decomposition.py "yes" "2" "???"
"""

import argparse
import asyncio
import json

from airglider import to_serializable
from clients import OpenAIClient
from config import settings
from evals.triage.eval_query_decomposition import decompose


async def run(queries: list[str]) -> list[dict]:
    client = OpenAIClient(settings.openai)
    try:
        outcomes = await asyncio.gather(
            *(decompose(client, query) for query in queries), return_exceptions=True
        )
    finally:
        await client.close()

    results = []
    for query, outcome in zip(queries, outcomes):
        if isinstance(outcome, Exception):
            results.append({"query": query, "error": f"{type(outcome).__name__}: {outcome}"})
        else:
            parsed, usage = outcome
            results.append({"query": query, "parsed": parsed, "usage": usage})
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("queries", nargs="+", help="One or more messages, each quoted.")
    args = parser.parse_args()

    results = asyncio.run(run(args.queries))
    print(json.dumps(to_serializable(results), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

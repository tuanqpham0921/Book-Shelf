"""Grade triage's query decomposition on its own — no backend, no database.

Each case's message goes through `build_decomposition_request`, the same
builder a turn uses, so the prompt, model, reasoning effort, token cap and
`QueryDecomposition` tool are exactly what production sends. Editing
`app/orchestration/triage/prompts/decompose_query.txt` and rerunning is the
whole loop: the builder reads the prompt from disk on every call.

A case passes on two checks:

- verdicts — the portions' verdicts, in message order, equal `expected` once
  adjacent repeats are merged on both sides. `[in_domain, in_domain]` and
  `[in_domain]` hand the planner the same words and pick the same reply, so
  only a difference the app would act on fails.
- verbatim — every portion's text appears in the message exactly as the user
  wrote it: the prompt's "copy, never correct" rule.

The call is made here rather than through `TriageWorkflow.decompose_query`:
that `@task` is the tracing around the same request, and needs a turn's
context to run.

Usage (from backend/, or `make eval-decomposition`):
    poetry run python evals/triage/eval_query_decomposition.py
    poetry run python evals/triage/eval_query_decomposition.py --ids 1 5 9
    poetry run python evals/triage/eval_query_decomposition.py --output evals/results/<campaign>/query_decomposition.md
"""

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from itertools import groupby
from pathlib import Path

from airglider import TokenUsage
from app.orchestration.triage.executor import (
    DECOMPOSE_PROMPT_PATH,
    build_decomposition_request,
)
from app.orchestration.triage.tools import QueryDecomposition
from clients import OpenAIClient
from config import settings
from evals.common import current_git_sha, report_header, truncate

SUITE_PATH = Path(__file__).parent / "suites" / "query_decomposition.json"

QUERY_PRINT_LIMIT = 60

_STATUS_ICON = {"pass": "✅", "fail": "❌", "error": "⚠️"}


def load_cases(ids: list[int] | None) -> list[dict]:
    cases = json.loads(SUITE_PATH.read_text())
    if ids:
        cases = [case for case in cases if case["id"] in ids]
    return cases


def merge_repeats(verdicts: list[str]) -> list[str]:
    """Adjacent repeats collapsed to one: two in_domain portions side by side
    reach the planner as one joined ask, so they grade as one."""
    return [verdict for verdict, _ in groupby(verdicts)]


def grade(case: dict, decomposition: QueryDecomposition) -> dict:
    portions = [(p.text, p.verdict.value) for p in decomposition.portions]
    got = [verdict for _, verdict in portions]
    verdicts_ok = merge_repeats(got) == merge_repeats(case["expected"])
    rewritten = [text for text, _ in portions if text.strip() not in case["query"]]
    return {
        "status": "pass" if verdicts_ok and not rewritten else "fail",
        "got": got,
        "verdicts_ok": verdicts_ok,
        "rewritten": rewritten,
        "portions": portions,
        "reasoning": decomposition.reasoning,
    }


async def decompose(
    client: OpenAIClient, query: str
) -> tuple[QueryDecomposition, TokenUsage]:
    """One decomposition, as `run_llm_args_parse` would read it: the first
    tool call's parsed arguments."""
    msg = await client.execute(build_decomposition_request(query))
    if not msg.tool_calls:
        raise ValueError("LLM response contained no tool calls")
    return msg.tool_calls[0].function.parsed_arguments, msg.token_usage


async def run_case(client: OpenAIClient, case: dict) -> dict:
    try:
        decomposition, usage = await decompose(client, case["query"])
    except Exception as e:  # one bad call is one failed case, not a dead run
        return {"case": case, "status": "error", "error": f"{type(e).__name__}: {e}"}
    return {"case": case, "usage": usage, **grade(case, decomposition)}


async def run_all(cases: list[dict]) -> list[dict]:
    # all at once: the client's own semaphore (MAX_CONCURRENCY) bounds it
    client = OpenAIClient(settings.openai)
    try:
        return await asyncio.gather(*(run_case(client, case) for case in cases))
    finally:
        await client.close()


def build_report(results: list[dict], git_sha: str, generated_at: datetime) -> str:
    usage = TokenUsage()
    for result in results:
        if "usage" in result:
            usage += result["usage"]

    statuses = Counter(result["status"] for result in results)
    wrong_verdicts = sum(1 for r in results if r["status"] == "fail" and not r["verdicts_ok"])
    rewritten = sum(1 for r in results if r.get("rewritten"))
    models = ", ".join(sorted(usage.by_model)) or "none"

    lines = report_header("Query Decomposition", ["query_decomposition"], git_sha, generated_at)
    lines += [
        f"- prompt: `app/{DECOMPOSE_PROMPT_PATH}`",
        f"- result: {statuses['pass']}/{len(results)} passed — {wrong_verdicts} wrong "
        f"verdicts, {rewritten} rewritten, {statuses['error']} errors",
        f"- spend: {usage.total:,} tokens, ${usage.cost_usd:.4f} ({models})",
        "",
        "| id | result | expected | got | query |",
        "|---|---|---|---|---|",
    ]
    for result in results:
        case = result["case"]
        lines.append(
            f"| {case['id']} | {_STATUS_ICON[result['status']]} "
            f"| {', '.join(case['expected'])} | {', '.join(result.get('got', []))} "
            f"| {truncate(case['query'], QUERY_PRINT_LIMIT)} |"
        )
    lines.append("")

    failures = [result for result in results if result["status"] != "pass"]
    if failures:
        lines += ["## Failures", ""]
    for result in failures:
        lines += _failure_lines(result)

    return "\n".join(lines)


def _failure_lines(result: dict) -> list[str]:
    case = result["case"]
    icon = _STATUS_ICON[result["status"]]
    lines = [f"### {case['id']} {icon}", "", f"> {case['query']}", ""]
    lines.append(f"- expected: {', '.join(case['expected'])}")

    if result["status"] == "error":
        lines.append(f"- error: {result['error']}")
    else:
        lines.append("- got:")
        lines += [f'    - "{text}" → {verdict}' for text, verdict in result["portions"]]
        if result["rewritten"]:
            lines.append(f"- not verbatim: {', '.join(repr(t) for t in result['rewritten'])}")
        lines.append(f"- reasoning: {result['reasoning']}")

    lines += [f"- note: {case['note']}", ""]
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", type=int, nargs="+", help="Only run these case ids.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Also write the report to this file "
        "(e.g. evals/results/<campaign>/query_decomposition.md).",
    )
    args = parser.parse_args()

    cases = load_cases(args.ids)
    if not cases:
        print(f"no cases matched in {SUITE_PATH}", file=sys.stderr)
        return 1

    results = asyncio.run(run_all(cases))
    report = build_report(results, current_git_sha(), datetime.now(timezone.utc))
    print(report)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report)
        print(f"report written to {args.output}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())

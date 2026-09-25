"""Grade triage's router on its own — no backend, no database.

Each case's message goes through `build_route_request`, the same builder a turn
uses, so the prompt, model, reasoning effort, token cap and the three tools are
exactly what production sends. Editing
`app/orchestration/triage/prompts/route_query.txt` and rerunning is the whole
loop: the builder reads the prompt from disk on every call.

A case passes when the route — the tool's name, or `reply` when the model
answered in text — is one of its `expected` routes. The tool's arguments are
not graded: `SecurityReview` and `ClarifyingQuestion` get fixed replies, so
only the pick reaches the user. A direct reply does reach the user as written,
so the report prints every one in full for reading.

The call is made here rather than through `route_query`: that `@task` is the
tracing around the same request, and needs a turn's context.

Usage (from backend/, or `make eval-routing`):
    poetry run python evals/triage/eval_route_query.py
    poetry run python evals/triage/eval_route_query.py --ids 101 409
    poetry run python evals/triage/eval_route_query.py --output evals/results/<campaign>/route_query.md
    poetry run python evals/triage/eval_route_query.py --save
"""

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from airglider import TokenUsage, to_serializable
from app.orchestration.triage.executor import ROUTE_PROMPT_PATH, build_route_request
from clients import OpenAIClient
from config import settings
from evals.common import current_git_sha, report_header, truncate

SUITE_PATH = Path(__file__).parent / "suites" / "route_query.json"
SAVE_DIR = Path(__file__).parent / "results"

QUERY_PRINT_LIMIT = 60
DETAIL_PRINT_LIMIT = 60

# the route when the model called no tool and answered the user itself
REPLY = "reply"

_STATUS_ICON = {"pass": "✅", "fail": "❌", "error": "⚠️"}


def load_cases(ids: list[int] | None) -> list[dict]:
    cases = json.loads(SUITE_PATH.read_text())
    if ids:
        cases = [case for case in cases if case["id"] in ids]
    return cases


def route_name(route: BaseModel | str) -> str:
    """The tool's name, or `reply` for text."""
    return REPLY if isinstance(route, str) else type(route).__name__


def detail_of(route: BaseModel | str) -> str:
    """What came with the route: the reply's text, or the tool's arguments."""
    if isinstance(route, str):
        return route
    args = route.model_dump()
    return json.dumps(args, ensure_ascii=False) if args else ""


def grade(case: dict, route: BaseModel | str) -> dict:
    name = route_name(route)
    return {
        "status": "pass" if name in case["expected"] else "fail",
        "route": name,
        "detail": detail_of(route),
    }


async def pick_route(
    client: OpenAIClient, query: str
) -> tuple[BaseModel | str, TokenUsage]:
    """One pick, as `route_query` reads it: the first tool call's parsed
    arguments, or the model's text when it called none."""
    msg = await client.execute(build_route_request(query))
    if msg.tool_calls:
        return msg.tool_calls[0].function.parsed_arguments, msg.token_usage
    if not msg.content:
        raise ValueError("LLM response contained neither a tool call nor text")
    return msg.content, msg.token_usage


async def run_case(client: OpenAIClient, case: dict, index: int, total: int) -> dict:
    try:
        route, usage = await pick_route(client, case["query"])
        result = {"case": case, "usage": usage} | grade(case, route)
    except Exception as e:  # one bad call is one failed case, not a dead run
        result = {"case": case, "status": "error", "error": f"{type(e).__name__}: {e}"}
    # stderr, so a piped report stays clean; `index` is launch order, not finish order
    print(f"[{index}/{total}] {_STATUS_ICON[result['status']]} case {case['id']}: "
          f"{truncate(case['query'], QUERY_PRINT_LIMIT)}", file=sys.stderr)
    return result


async def run_all(cases: list[dict]) -> list[dict]:
    # all at once: the client's own semaphore (MAX_CONCURRENCY) bounds it
    client = OpenAIClient(settings.openai)
    try:
        return await asyncio.gather(
            *(run_case(client, case, i, len(cases)) for i, case in enumerate(cases, 1))
        )
    finally:
        await client.close()


def build_report(results: list[dict], git_sha: str, generated_at: datetime) -> str:
    usage = TokenUsage()
    for result in results:
        if "usage" in result:
            usage += result["usage"]

    statuses = Counter(result["status"] for result in results)
    failed = [result for result in results if result["status"] == "fail"]
    # a book ask the planner never saw costs a user; misuse let through costs the app
    kept_from_planner = sum(1 for r in failed if "PlanJane" in r["case"]["expected"])
    let_through = sum(1 for r in failed if "SecurityReview" in r["case"]["expected"]
                      and r["route"] in ("PlanJane", REPLY))
    models = ", ".join(sorted(usage.by_model)) or "none"

    lines = report_header("Triage Routing", ["route_query"], git_sha, generated_at)
    lines += [
        f"- prompt: `app/{ROUTE_PROMPT_PATH}`",
        f"- result: {statuses['pass']}/{len(results)} passed — {kept_from_planner} book "
        f"asks kept from the planner, {let_through} misuse let through, "
        f"{statuses['error']} errors",
        f"- spend: {usage.total:,} tokens, ${usage.cost_usd:.4f} ({models})",
        "",
        "| id | result | expected | got | detail | query |",
        "|---|---|---|---|---|---|",
    ]
    for result in results:
        case = result["case"]
        lines.append(
            f"| {case['id']} | {_STATUS_ICON[result['status']]} "
            f"| {' / '.join(case['expected'])} | {result.get('route', '')} "
            f"| {truncate(result.get('detail', ''), DETAIL_PRINT_LIMIT)} "
            f"| {truncate(case['query'], QUERY_PRINT_LIMIT)} |"
        )
    lines.append("")

    failures = [result for result in results if result["status"] != "pass"]
    if failures:
        lines += ["## Failures", ""]
    for result in failures:
        case = result["case"]
        lines += [f"### {case['id']} {_STATUS_ICON[result['status']]}", "",
                  f"> {case['query']}", "",
                  f"- expected: {' / '.join(case['expected'])}"]
        if result["status"] == "error":
            lines.append(f"- error: {result['error']}")
        else:
            lines.append(f"- got: {result['route']}")
            if result["detail"]:
                lines.append(f"- detail: {result['detail']}")
        lines += [f"- note: {case['note']}", ""]

    # the one route whose words the user reads as the model wrote them
    replies = [result for result in results if result.get("route") == REPLY]
    if replies:
        lines += ["## Direct replies", ""]
    for result in replies:
        lines += [f"- **{result['case']['id']}** {result['case']['query']!r} → "
                  f"{result['detail']}"]

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", type=int, nargs="+", help="Only run these case ids.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Also write the report to this file "
        "(e.g. evals/results/<campaign>/route_query.md).",
    )
    parser.add_argument(
        "--save",
        type=Path,
        nargs="?",
        const=SAVE_DIR,
        help="Save report.md plus results.json (every case's route, its "
        "arguments or reply, and usage) into a timestamped folder under this "
        "directory (default: evals/<test>/results/).",
    )
    args = parser.parse_args()

    cases = load_cases(args.ids)
    if not cases:
        print(f"no cases matched in {SUITE_PATH}", file=sys.stderr)
        return 1

    results = asyncio.run(run_all(cases))
    generated_at = datetime.now(timezone.utc)
    report = build_report(results, current_git_sha(), generated_at)
    print(report)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report)
        print(f"report written to {args.output}", file=sys.stderr)

    if args.save:
        run_dir = args.save / f"route_query_{generated_at:%Y%m%d_%H%M%S}"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "report.md").write_text(report)
        (run_dir / "results.json").write_text(
            json.dumps(to_serializable(results), indent=2, ensure_ascii=False)
        )
        print(f"report and results saved to {run_dir}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())

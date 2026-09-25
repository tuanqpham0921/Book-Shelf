"""Grade the message check on its own — no backend, no database.

Each case's message goes through `build_validation_request`, the same builder
a turn uses, so the prompt, model, reasoning effort, token cap and
`UserMsgValidation` tool are exactly what production sends. Editing
`app/orchestration/validation/prompts/validate_message.txt` and rerunning is
the whole loop: the builder reads the prompt from disk on every call.

A case passes when the outcome — which fixed reply `refusal_for` picks, or
`pass` — is one of its `expected` outcomes. Grading the reply rather than each
flag means only a difference the user would see fails: a code snippet the
model also calls an injection gets the harmful reply, and a case where both
readings are fair lists both.

The call is made here rather than through `validate_user_message`: that
`@task` is the tracing around the same request, and needs a turn's context.

Usage (from backend/, or `make eval-validation`):
    poetry run python evals/validation/eval_validate_message.py
    poetry run python evals/validation/eval_validate_message.py --ids 1 5 9
    poetry run python evals/validation/eval_validate_message.py --output evals/results/<campaign>/validate_message.md
    poetry run python evals/validation/eval_validate_message.py --save
"""

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from airglider import TokenUsage, to_serializable
from app.orchestration.validation import UserMsgValidation, refusal_for
from app.orchestration.validation.validate import (
    CODE_REPLY,
    HARMFUL_REPLY,
    INCOHERENT_REPLY,
    LANGUAGE_REPLY,
    VALIDATE_PROMPT_PATH,
    build_validation_request,
)
from clients import OpenAIClient
from config import settings
from evals.common import current_git_sha, report_header, truncate

SUITE_PATH = Path(__file__).parent / "suites" / "validate_message.json"
SAVE_DIR = Path(__file__).parent / "results"

QUERY_PRINT_LIMIT = 60

_STATUS_ICON = {"pass": "✅", "fail": "❌", "error": "⚠️"}

# each fixed reply named, so a case says what the user should see
_OUTCOME_OF_REPLY = {
    None: "pass",
    HARMFUL_REPLY: "harmful",
    CODE_REPLY: "code",
    INCOHERENT_REPLY: "incoherent",
    LANGUAGE_REPLY: "language",
}


def load_cases(ids: list[int] | None) -> list[dict]:
    cases = json.loads(SUITE_PATH.read_text())
    if ids:
        cases = [case for case in cases if case["id"] in ids]
    return cases


def flags_of(validation: UserMsgValidation) -> str:
    """The verdict in one cell: the language, then every flag that is set."""
    flags = [name for name, value in validation.model_dump().items() if value is True]
    return ", ".join([validation.language, *flags])


async def validate(
    client: OpenAIClient, query: str
) -> tuple[UserMsgValidation, TokenUsage]:
    """One check, as `validate_user_message` reads it: the first tool call's
    parsed arguments."""
    msg = await client.execute(build_validation_request(query))
    if not msg.tool_calls:
        raise ValueError("LLM response contained no tool calls")
    return msg.tool_calls[0].function.parsed_arguments, msg.token_usage


async def run_case(client: OpenAIClient, case: dict, index: int, total: int) -> dict:
    try:
        validation, usage = await validate(client, case["query"])
        outcome = _OUTCOME_OF_REPLY[refusal_for(validation)]
        status = "pass" if outcome in case["expected"] else "fail"
        result = {"case": case, "status": status, "usage": usage,
                  "parsed": validation, "outcome": outcome}
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
    # a wrongly refused book request costs a user; a missed refusal costs the app
    over = sum(1 for r in results if r["status"] == "fail" and r["outcome"] != "pass"
               and "pass" in r["case"]["expected"])
    under = sum(1 for r in results if r["status"] == "fail" and r["outcome"] == "pass")
    models = ", ".join(sorted(usage.by_model)) or "none"

    lines = report_header("Message Validation", ["validate_message"], git_sha, generated_at)
    lines += [
        f"- prompt: `app/{VALIDATE_PROMPT_PATH}`",
        f"- result: {statuses['pass']}/{len(results)} passed — {over} wrongly refused, "
        f"{under} wrongly passed, {statuses['error']} errors",
        f"- spend: {usage.total:,} tokens, ${usage.cost_usd:.4f} ({models})",
        "",
        "| id | result | expected | got | flags | query |",
        "|---|---|---|---|---|---|",
    ]
    for result in results:
        case = result["case"]
        flags = flags_of(result["parsed"]) if "parsed" in result else ""
        lines.append(
            f"| {case['id']} | {_STATUS_ICON[result['status']]} "
            f"| {' / '.join(case['expected'])} | {result.get('outcome', '')} | {flags} "
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
            lines.append(f"- got: {result['outcome']} ({flags_of(result['parsed'])})")
        lines += [f"- note: {case['note']}", ""]

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", type=int, nargs="+", help="Only run these case ids.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Also write the report to this file "
        "(e.g. evals/results/<campaign>/validate_message.md).",
    )
    parser.add_argument(
        "--save",
        type=Path,
        nargs="?",
        const=SAVE_DIR,
        help="Save report.md plus results.json (every case's parsed verdict, "
        "outcome and usage) into a timestamped folder under this directory "
        "(default: evals/<test>/results/).",
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
        run_dir = args.save / f"validate_message_{generated_at:%Y%m%d_%H%M%S}"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "report.md").write_text(report)
        (run_dir / "results.json").write_text(
            json.dumps(to_serializable(results), indent=2, ensure_ascii=False)
        )
        print(f"report and results saved to {run_dir}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())

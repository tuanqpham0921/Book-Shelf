"""Tests for the query-decomposition eval's pure parts: grading one
decomposition against its case, the report it renders, and that the suite file
itself is well formed. The OpenAI call is not covered here — the eval exists to
make it."""

from datetime import datetime, timezone

from airglider import TokenUsage
from app.orchestration.triage import QueryPortion, TriageVerdict
from app.orchestration.triage.tools import QueryDecomposition
from evals.triage.eval_query_decomposition import (
    build_report,
    grade,
    load_cases,
    merge_repeats,
)

IN, SMALL, OUT = TriageVerdict.IN_DOMAIN, TriageVerdict.SMALL_TALK, TriageVerdict.OUT_OF_SCOPE


def split(*portions: tuple[str, TriageVerdict]) -> QueryDecomposition:
    return QueryDecomposition(
        reasoning="test",
        portions=[QueryPortion(text=text, verdict=verdict) for text, verdict in portions],
    )


def case(query: str, *expected: str) -> dict:
    return {"id": 1, "query": query, "expected": list(expected), "note": "n"}


class TestMergeRepeats:
    def test_adjacent_repeats_collapse(self):
        assert merge_repeats(["in_domain", "in_domain", "small_talk"]) == ["in_domain", "small_talk"]

    def test_separated_repeats_stay(self):
        assert merge_repeats(["in_domain", "small_talk", "in_domain"]) == [
            "in_domain",
            "small_talk",
            "in_domain",
        ]


class TestGrade:
    def test_exact_match_passes(self):
        result = grade(
            case("hi! books like Dune", "small_talk", "in_domain"),
            split(("hi!", SMALL), ("books like Dune", IN)),
        )

        assert result["status"] == "pass"
        assert result["got"] == ["small_talk", "in_domain"]

    def test_extra_split_of_the_same_verdict_still_passes(self):
        # both halves reach the planner joined, so the app can't tell them apart
        result = grade(
            case("I loved The Road. What else?", "in_domain"),
            split(("I loved The Road.", IN), ("What else?", IN)),
        )

        assert result["status"] == "pass"

    def test_wrong_verdict_fails(self):
        result = grade(case("what's the weather?", "out_of_scope"), split(("what's the weather?", IN)))

        assert result["status"] == "fail"
        assert not result["verdicts_ok"]

    def test_wrong_order_fails(self):
        result = grade(
            case("books, and the weather", "in_domain", "out_of_scope"),
            split(("books,", OUT), ("and the weather", IN)),
        )

        assert result["status"] == "fail"

    def test_corrected_text_fails_verbatim(self):
        result = grade(
            case("Find teh book Duen", "in_domain"),
            split(("Find the book Dune", IN)),
        )

        assert result["status"] == "fail"
        assert result["verdicts_ok"]
        assert result["rewritten"] == ["Find the book Dune"]

    def test_surrounding_whitespace_is_not_a_rewrite(self):
        result = grade(case("hi books", "small_talk", "in_domain"), split(("hi ", SMALL), (" books", IN)))

        assert result["rewritten"] == []


class TestBuildReport:
    def test_summary_counts_and_failures_section(self):
        passed = {"case": case("hi", "small_talk"), "usage": TokenUsage(model="gpt-5-mini", total=10, prompt=8, completion=2)}
        passed |= grade(passed["case"], split(("hi", SMALL)))
        errored = {"case": case("???", "gibberish") | {"id": 2}, "status": "error", "error": "ValueError: boom"}

        report = build_report([passed, errored], "abc123", datetime(2026, 9, 24, tzinfo=timezone.utc))

        assert "1/2 passed — 0 wrong verdicts, 0 rewritten, 1 errors" in report
        assert "10 tokens" in report
        assert "## Failures" in report
        assert "ValueError: boom" in report

    def test_no_failures_section_when_all_pass(self):
        passed = {"case": case("hi", "small_talk"), "usage": TokenUsage()}
        passed |= grade(passed["case"], split(("hi", SMALL)))

        report = build_report([passed], "abc123", datetime(2026, 9, 24, tzinfo=timezone.utc))

        assert "## Failures" not in report


class TestSuiteFile:
    def test_every_case_is_well_formed(self):
        cases = load_cases(ids=None)
        verdicts = {verdict.value for verdict in TriageVerdict}

        assert cases
        assert len({c["id"] for c in cases}) == len(cases)
        for c in cases:
            assert c["query"] and c["note"]
            assert c["expected"] and set(c["expected"]) <= verdicts

    def test_ids_filter(self):
        assert [c["id"] for c in load_cases(ids=[2, 1])] == [1, 2]

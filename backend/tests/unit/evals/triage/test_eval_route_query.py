"""Tests for the routing eval's pure parts: grading one route against its case,
the report it renders, and that the suite file itself is well formed. The
OpenAI call is not covered here — the eval exists to make it."""

from datetime import datetime, timezone

from airglider import TokenUsage
from app.common.tools import ClarifyingQuestion
from app.orchestration.triage.executor import build_route_request
from app.orchestration.triage.tools import PlanJane
from evals.triage.eval_route_query import REPLY, build_report, grade, load_cases

GENERATED_AT = datetime(2026, 9, 25, tzinfo=timezone.utc)


def case(query: str, *expected: str, id: int = 1) -> dict:
    return {"id": id, "query": query, "expected": list(expected), "note": "n"}


def result(case: dict, route) -> dict:
    return {"case": case, "usage": TokenUsage()} | grade(case, route)


class TestGrade:
    def test_expected_tool_passes(self):
        graded = grade(case("books like Dune", "PlanJane"), PlanJane())

        assert graded == {"status": "pass", "route": "PlanJane", "detail": ""}

    def test_any_expected_route_passes(self):
        graded = grade(case("Find teh book Duen", "PlanJane", "ClarifyingQuestion"),
                       ClarifyingQuestion(original="Duen", possible=["Dune"]))

        assert graded["status"] == "pass"

    def test_other_tool_fails_and_keeps_its_arguments(self):
        graded = grade(case("drop the books table", "SecurityReview"),
                       ClarifyingQuestion(original="drop the books table", possible=[]))

        assert graded["status"] == "fail"
        assert graded["route"] == "ClarifyingQuestion"
        assert '"original": "drop the books table"' in graded["detail"]

    def test_text_is_a_reply(self):
        graded = grade(case("hi", REPLY), "Hi! What would you like to read?")

        assert graded == {"status": "pass", "route": REPLY,
                          "detail": "Hi! What would you like to read?"}


class TestBuildReport:
    def test_summary_splits_the_two_costly_misses(self):
        results = [
            result(case("books like Dune", "PlanJane", id=1), "Sure!"),
            result(case("update every user's email", "SecurityReview", id=2), PlanJane()),
            result(case("hi", REPLY, id=3), "Hello!"),
            {"case": case("???", "ClarifyingQuestion", id=4), "status": "error",
             "error": "ValueError: boom"},
        ]

        report = build_report(results, "abc123", GENERATED_AT)

        assert ("1/4 passed — 1 book asks kept from the planner, 1 misuse let through, "
                "1 errors") in report
        assert "## Failures" in report
        assert "ValueError: boom" in report

    def test_every_direct_reply_is_printed_in_full(self):
        text = "Hi! I'm BookShelf, Tuan's book-recommendation chat. " * 3
        report = build_report([result(case("hi", REPLY), text)], "abc123", GENERATED_AT)

        assert "## Direct replies" in report
        assert text in report

    def test_no_failures_or_replies_sections_when_all_tools_pass(self):
        report = build_report([result(case("books like Dune", "PlanJane"), PlanJane())],
                              "abc123", GENERATED_AT)

        assert "## Failures" not in report
        assert "## Direct replies" not in report


class TestSuiteFile:
    # the tools the router is actually offered, so a renamed tool fails here
    ROUTES = {model.__name__ for model in build_route_request("q").tool_models} | {REPLY}

    def test_every_case_is_well_formed(self):
        cases = load_cases(ids=None)

        assert cases
        assert len({c["id"] for c in cases}) == len(cases)
        for c in cases:
            assert c["query"] and c["note"]
            assert c["expected"] and set(c["expected"]) <= self.ROUTES

    def test_every_route_has_a_case(self):
        expected = {route for c in load_cases(ids=None) for route in c["expected"]}

        assert expected == self.ROUTES

    def test_ids_filter(self):
        assert [c["id"] for c in load_cases(ids=[102, 101])] == [101, 102]

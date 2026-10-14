# playground

`playground` is BookShelf's backend scratch space: code for trying ideas outside the app. Nothing in the app imports it, and it is not in the image.

`app_mock/` holds mock executors and request schemas for nodes that were never built, once used to test the planner on a larger tool catalog. It is no longer maintained, so don't model new code on it. `evals/planjane/suites/query_suite_extended.json` is the suite written for it.

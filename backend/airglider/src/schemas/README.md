# airglider schemas

airglider's schemas are the envelope every unit of work returns, `OperationResult`, and the parts it is built from. Its shape is sketched in the [top README](../../README.md#the-envelope).

## Parts

- **`OperationResult`** ([record.py](record.py)): one unit of work and its `steps`. The same class is used for a `@task`, a `Workflow`, and each row of a flattened list.
- **`Time`**: `start_time` and `duration`; `end_time` is derived from the two.
- **`Response`**: the payload (`result`) and the name of its declared type (`output_type`).
- **`TokenUsage`** ([token_usage.py](token_usage.py)): counts for one LLM call, or the sum of many. A sum keeps a per-model split in `by_model`, and `cost_usd` is recomputed on every add.
- **`RuntimeErrorInfo`** ([error_info.py](error_info.py)): an exception as data (`type`, `message`, `traceback`), so it can be stored and grouped.

## Errors

Two kinds of exception end up in `runtime_error`:

- **The real one:** whatever the step raised, a crash or a deliberate "can't proceed". Logged with its traceback.
- **`StepFailure`:** the step stopped because a step it needed failed (`unwrap`). Logged as one warning line with no traceback, because the real one is already in the failed step's own envelope, one level down.

To find the cause of a failed run, follow the `FAILED STEP: <name>` details down to the envelope whose error is not a `StepFailure`.

## Methods

| Method | What it does |
|---|---|
| `unwrap()` | the payload if `ok`, otherwise notes the failure on the caller and raises `StepFailure` |
| `add_step(step)` | attaches a child, sets its `parent_id` and adds its token usage. Attaching twice is ignored; a step that already has another parent is refused |
| `add_details(*msg)` | appends free-text notes |
| `to_summary()` | a small nested dict per step (name, ok, duration, tokens, cost, error type, the payload's own `to_summary()`), for reading a run top to bottom |
| `flatten()` | the tree as a list, parent before child, each row carrying its `parent_id`, for timelines and per-step cost tables |
| `to_span()` | one row of `flatten()`: the same envelope without its `steps` |

`steps` is typed `list[Any]` so a child stays the same object its producer is still writing to. After a JSON round trip the children are plain dicts; `flatten()` validates them as it goes.

# Domains

The domains package holds everything BookShelf's planner can plan with: each capability is a **node**, and nodes are grouped into domains. [books/](books/README.md) finds books in the catalog, and [project/](project/README.md) answers questions about BookShelf from its own docs. [planjane/](planjane/README.md), the planner itself, lives here too.

## A node is a slice

Each node is one folder holding everything about it:

```
books/find_by_title/
├── labels.py     # the planner-facing name, as a one-member str Enum
├── external.py   # what other layers read: the request (its docstring is the catalog entry), input, output
├── tools.py      # what the node's own parse call ships to an LLM: its *Args
├── executor.py   # the workflow that runs it
└── __init__.py   # SPEC = NodeSpec(...) tying them together
```

A node that parses no arguments (`find_similar_books/`, `intersect_books/`) has no `tools.py`.

Two folders are the templates, and a new node starts as a copy of one of them:

- **[find_by_title/](books/find_by_title/)** for a single-call node: parse args → build the query → count → preview → finalize.
- **[find_similar_books/](books/find_similar_books/)** for a multi-step node. `executor.py` stays the flow: `run()` plus every step, as methods in the order `run` calls them. Each **satellite module is one LLM call's pure half** (the rendering, the tool model, the request builder — nothing that runs), and the interpretation of the node's input gets its own module when it outgrows `run` (`dependents.py`). A request builder with nothing to render (`build_arg_parser_request`) stays in `executor.py`. Never a `utils.py`: a helper belongs to the flow, to one call's pure half, or to the input, and the file is named for which.

## Shared pieces

- **`node_spec.py`** — `NodeSpec`, the one thing a slice exports (node type, tier, request, input, output, executor), and `NodeTier` (`RETRIEVAL` → `COMBINE` → `ANALYZE`, the order the catalog lists them). The spec checks its name against the request's `node_type` default, so the two can't drift apart.
- **`<domain>/guide.py`** — that domain's specs, one line per node. [app/registry.py](../registry.py) collects them into `REGISTRY`, which answers every node lookup.
- **`base_request.py`** — `BaseRequest`. A request carries only its `node_type`; its docstring is what the planner reads.
- **`node_input.py`** — the input classes (`NodeInput`, `ParsedInput`) and `build_input`, which fills a node's declared input from the planner's instruction and its dependencies' outputs.
- **`base_workflow.py`** — `AppWorkflow`, the base under every unit of work, with the LLM helpers (`run_llm_args_parse`, `run_llm_tool_calls`); and `NodeWorkflowOutput` / `FailedGoalOutput`, the base output and what a goal that didn't run leaves behind.
- **`<domain>/base_workflow.py`** — what every node in one domain repeats. For books that is counting, fetching and streaming books; see [books/](books/README.md#shared-base).

## One call shape: `run(node_input)`

The planner, the task runner and every node take one argument: their own `WorkflowInput` subclass. A node declares that class on its `NodeSpec`, and the task runner assembles it.

**The declaration is the point.** A named, empty field says which input is missing and what shape would fill it. Default a field whenever the node has a real fallback; make it required only when the node can't proceed without it.

**Fields are filled by type, never by key.** `build_input` matches each field's annotation against the dependency outputs: `X` takes the first match, `X | None` takes it or None, `list[X]` takes all of them. A required field that matches nothing raises a `ValidationError` naming the field, and the task runner skips that one goal.

**A required list needs `min_length`.** An empty list is still a filled field, so `Field(...)` alone never fires. `SimilarBooksInput.anchors` is `min_length=1` (nothing to be similar to is a different question) and `CombineIntersectInput.anchors` is `min_length=2` (an intersection of one isn't one).

**Narrow a field with a subclass.** Matching is `isinstance`, so `BookAnchorOutput` and `BookCandidateOutput` add no fields — the type is the payload — and `list[BookAnchorOutput]` can't be handed a subject search. To accept two subclasses but not their base, write the union: `list[A | B]`.

**Don't use a pydantic discriminated union here.** `isinstance` against `Annotated[A | B, Field(discriminator=...)]` raises `TypeError`. Outputs arrive already built, so the class already is the discriminator.

**Services come off the context, not the input.** `AppWorkflow.__init__(ctx, messages)` is the only `__init__` in the app layer; `sse_stream`, `llm_client`, `app_env`, `session_id` and `user_message` are properties off the `RequestContext`. Services are built once per request, an input once per dispatch.

**A node opens its own database session.** `RequestContext` carries only the session factory, and `ctx.store(...)` opens a session for one block, then commits and closes it:

```python
async with self.ctx.store(BookStore) as store:
    total = await store.count(query)
```

The turn runs after the HTTP handler has returned, so a session held for the whole request would already be closed. Two rules follow: **keep the block around the round trip and nothing else** (building a query needs no store — the builders are functions in `db/stores/book_store.py`), and **no store commits for itself** (the block owns the transaction).

## Naming: Workflow and Executor

The ladder is `airglider.Workflow` → `AppWorkflow` → `BookReaderWorkflow` → `BookWorkflow`. Concrete units of work are `*Workflow` too (`TriageWorkflow`, `TaskRunnerWorkflow`).

**`Executor` marks the ones the planner can dispatch.** `FindByTitleExecutor` is a workflow, but it is also a node: it has a request schema, a `NodeSpec` and a catalog entry, and the task runner reaches it through the registry. So a slice has `<node>/executor.py` holding `<Node>Executor`, and `base_workflow.py` holds the bases.

## Writing an executor — the rules

What `ok` means, when to raise, and the two ways to run a step are airglider's rules: [airglider's README](../../airglider/README.md#the-rules). Read it first; they are not restated here.

1. **One request schema, one executor.** New behavior is a new slice with its own `SPEC`, never a flag on an existing executor.
2. **The request declares the capability; a separate `*Args` model carries the arguments.** The request (in `external.py`) is a docstring and a `node_type` Literal — no fields, because the planner picks a capability and writes an instruction, and a field would be one more thing for it to guess. The `*Args` model (in `tools.py`) is an internal tool the planner never sees: no `node_type`, `confidence` or `reasoning`, just what the node's own parse fills, plus a one-line docstring the model reads.
3. **The body runs parse → work → finalize.**
   - *Parse*: fill the `*Args` from the instruction (`build_arg_parser_request` → `run_llm_args_parse`) and keep it on the output's `args`. Not every node parses: `Analyze_Similar_Books` builds its search from its anchors, and `Combine_Intersect` makes no LLM call at all.
   - *Work*: whatever the node is for.
   - *Finalize*: `self.finalize_result()` last. Each slice overrides it to compute its **claim**: did it do what it promised ("the query got built"). Raise when the node can't proceed; never set `ok=False` by hand and return.
4. **An empty result is not a failure.** Zero matches or an empty pool is an answer the node reports; raising would turn it into a generic error message.
5. **Every async call is a step.** Each database round trip, LLM call and embedding gets its own duration, failure and spend. Use the smallest rung that fits:
   - a **pure function** for building a request (`build_*_request`): sync, no I/O, testable alone;
   - the **`run_llm_*` helpers** for LLM calls. `clients/` itself never grows a `@task`; the app decides what is a step;
   - a **`@task` method** for an async unit that returns a payload (`count_books`, `fetch_books`);
   - a **`Workflow`** only when the sub-work needs its own output type and envelope, as triage running the planner does.
6. **Nodes hear an instruction and typed outputs, nothing else.** `node_input.instruction` is the only thing a node is told about the ask; no node reads `ctx.user_message`. Upstream outputs arrive only through declared input fields.
7. **Book nodes go counts-first:** build the query → `count_books()` → `fetch_books()` for the preview cards → hand the *query* on, not the rows. A node that needs an upstream count reads it off the upstream output instead of counting again.
8. **Two traps:** every output field needs a default (the output is built empty before `run`), and a workflow instance runs once — make a new one per execution, retries included.
9. **Reuse before adding.** Most of what a node needs is already on `BookWorkflow`, `DeferredBookQuery`, `REGISTRY` or airglider. Each slice still writes its own `build_arg_parser_request`, on purpose, so one node can change its model or prompt alone.

**Known gap:** a dead end that raises and a genuine bug both land in `runtime_error`, so the record can't yet tell "could not proceed" from "crashed". Don't build logic that branches on `runtime_error.type`.

## Adding a node

1. **Copy the matching template** to `<domain>/<node>/`. A book node's executor subclasses `BookWorkflow[TheOutput]` and implements `run(node_input)`.
2. **Declare the arguments**, if the node parses any: the `*Args` model in `tools.py`, and a module-level `build_arg_parser_request(instruction)` in `executor.py`. Call it as `await self.run_llm_args_parse(build_arg_parser_request(node_input.instruction))` and set `self.result.args` yourself.
3. **Declare the input** in `external.py` as a `NodeInput` subclass. A node with no dependencies adds nothing, which means it can't take upstream output. A node that consumes books adds a field such as `anchors: list[BookRetrievalOutput] = Field(default_factory=list)`.
4. **Write the request's docstring for the planner.** It is prompt text, with these sections: `Purpose:`, `Args:`, `Returns:`, `depends_on:`, `Use when:`, `Do not use:`, `Constraints:`, and examples (`Example queries:`). `Returns:` and `depends_on:` name **output shapes** (`BookRetrievalOutput`, `BookAnchorOutput`, `BookCandidateOutput`, or a node-specific name), which is how the planner knows which nodes can feed which.
5. **Subclass the output** from the shape the docstring claims, and give every field a default.
6. **Export `SPEC = NodeSpec(...)`** from the slice's `__init__.py`, and add it to the domain's `guide.py` — the only file outside the slice you touch.
7. **Add eval cases** with `expected_nodes` in `backend/evals/planjane/suites/` (see [eval strategy](../../../docs/temp_docs/eval-strategy.md)).

Then run `make tools-catalog`: it reads the live registry, so it confirms the node reached the planner's catalog and flags a missing executor or docstring section. The planner picks a registered node up with no other change.

**Parking a node** — keeping the code but hiding it from the planner — is removing its `SPEC` from `guide.py`. The planner then refuses any goal that targets it.

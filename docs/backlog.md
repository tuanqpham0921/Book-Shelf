# Backlog

The BookShelf backlog is a temporary buffer for known bugs and small follow-ups that don't have a home yet. Items here will migrate to GitHub issues and pull requests; once an item is tracked there, remove it from this file.

## Bugs

- [ ] **Escape `%` and `_` in title search** — `title_query` ([book_store.py](../backend/db/stores/book_store.py)) passes the title straight into `ILIKE`, so `%` and `_` act as wildcards (a search for "100%" matches more than it should). Check the other `ilike` builders for the same issue.

- [ ] **`stream_books` crashes on a bad row** — one book that fails `BookOut` validation (e.g. no `isbn13`) raises and stops the remaining cards ([base_workflow.py](../backend/app/domains/books/base_workflow.py)). Skip and log it instead.

## Cleanup

- [ ] **A command to load the project-docs vector store** — the store `Retrieve_Project_Info` searches is built by hand from [file_search_docs.ipynb](../backend/evals/app_docs/file_search_docs.ipynb), so a README edit doesn't reach the chatbot until someone re-runs it. Add a make target that uploads the READMEs and `docs/` into the store named by `OPENAI_VECTOR_STORE_ID`.

- [ ] **Remove unused phrase builders** — `describe_bounds` / `range_phrase` (numeric traits) and `describe_lexical_traits` build user-facing lines that nothing shows; they're only used as an "is the parse empty?" check. Replace with a plain check and delete them and their tests.

- [ ] **Name node enums after their classes** — `FindTitleNodeTypeEnum` sits beside `FindByTitle*` (same in `find_by_author`, `find_by_lexical_traits`, `find_by_numeric_traits`). Rename to `FindByTitleNodeTypeEnum` etc. across the book slices.
- [ ] **Move parse model names to config** — every book slice's `build_arg_parser_request` writes `model="gpt-5-nano"` inline; CLAUDE.md says model names belong in `config/constants.py`.
- [ ] **Before extracting airglider** — move `src/` to `src/airglider/` at the package root (or drop the layer); rename `base_glider.py` to match `Workflow`; settle one name for record / `OperationResult` / "envelope"; `exception.py` → `exceptions.py`; give it its own `pyproject.toml` and pytest config (the suite inherits the host's `asyncio_mode = "auto"`).
- [ ] **airglider: retries and typed errors** — retry with backoff, and an error type a caller can branch on (business failure vs crash).
- [ ] **airglider: `Workflow` sets `ok=True` on clean completion** — today each `run()` sets it (`AppWorkflow.finalize_result`).
- [ ] **airglider: `to_summary()` includes the input summary** — so the summary has everything the full record does.
- [ ] **clients: drop `sse_stream` from `BaseLLMRequest`** — it is the last app import in `clients/`. Have `execute` yield events when streaming, and let the workflow forward them to its `SSEStream`.
- [ ] **clients: warn on an unvalidated `UserMessage`** — `to_openai_dict` raises on `pass_validation=False` but says nothing on `None`. Add a warning once it's settled whether planner→node instructions go as user or assistant messages (today they're `AssistantMessage`s, so they wouldn't trip it).
- [ ] **Take dev notes out of docstrings the LLM reads** — `FindByLexicalTraitsArgs` (the "deliberately not `BooksFilter`" paragraph), `BookMetadataFilter` (dates, retired nodes, why the calibration lives there) and `AudienceEnum` ("Db-owned rather than slice-owned") all ship inside tool schemas. Move the notes to code comments and re-run the lexical and numeric eval cases.

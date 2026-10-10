# Backlog

The BookShelf backlog is a temporary buffer for known bugs and small follow-ups that don't have a home yet. Items here will migrate to GitHub issues and pull requests; once an item is tracked there, remove it from this file.

## Bugs

- [ ] **Escape `%` and `_` in title search** — `title_query` ([book_store.py](../backend/db/stores/book_store.py)) passes the title straight into `ILIKE`, so `%` and `_` act as wildcards (a search for "100%" matches more than it should). Check the other `ilike` builders for the same issue.

## Cleanup

- [ ] **Remove unused phrase builders** — `describe_bounds` / `range_phrase` (numeric traits) and `describe_lexical_traits` build user-facing lines that nothing shows; they're only used as an "is the parse empty?" check. Replace with a plain check and delete them and their tests.

- [ ] **Name node enums after their classes** — `FindTitleNodeTypeEnum` sits beside `FindByTitle*` (same in `find_by_author`, `find_by_lexical_traits`, `find_by_numeric_traits`). Rename to `FindByTitleNodeTypeEnum` etc. across the book slices.
- [ ] **Move parse model names to config** — every book slice's `build_arg_parser_request` writes `model="gpt-5-nano"` inline; CLAUDE.md says model names belong in `config/constants.py`.
- [ ] **Take the dev note out of `FindByLexicalTraitsArgs`' docstring** — the "deliberately not `BooksFilter`" paragraph is shipped to the LLM as part of the tool description. Move it to a code comment and re-run the lexical eval cases.

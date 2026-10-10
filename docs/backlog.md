# Backlog

The BookShelf backlog is a temporary buffer for known bugs and small follow-ups that don't have a home yet. Items here will migrate to GitHub issues and pull requests; once an item is tracked there, remove it from this file.

## Bugs

- [ ] **Escape `%` and `_` in title search** — `title_query` ([book_store.py](../backend/db/stores/book_store.py)) passes the title straight into `ILIKE`, so `%` and `_` act as wildcards (a search for "100%" matches more than it should). Check the other `ilike` builders for the same issue.

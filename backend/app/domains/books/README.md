# Books domain

The books domain holds every BookShelf node that finds books in the catalog: by title, by author, by subject words, by numbers like page count or rating, by similarity to a named book, and by combining earlier searches. The planner picks these nodes; each one counts its matches and hands the search on as a query, so later steps can narrow it in SQL.

## Nodes

| Node | Folder | Finds |
|---|---|---|
| `Retrieve_by_Title` | [find_by_title/](find_by_title/) | a book the user names by its title |
| `Retrieve_by_Author` | [find_by_author/](find_by_author/) | one author's books |
| `Retrieve_by_Lexical_Traits` | [find_by_lexical_traits/](find_by_lexical_traits/) | books whose text contains subject words, filtered by fiction / non-fiction and audience |
| `Retrieve_by_Numeric_Traits` | [find_by_numeric_traits/](find_by_numeric_traits/) | books inside bounds on pages, year, rating or rating count |
| `Analyze_Similar_Books` | [find_similar_books/](find_similar_books/) | books close in meaning to books the user named |
| `Combine_Intersect` | [intersect_books/](intersect_books/) | books that satisfy two or more earlier searches at once |

The registered set is [guide.py](guide.py). Dropping a node's `SPEC` there hides it from the planner without deleting the code. `make tools-catalog` shows what the planner is actually offered.

Two folders are the templates for new nodes: `find_by_title/` for a single-call node, `find_similar_books/` for a multi-step one. The step-by-step recipe is in [domains/README.md](../README.md).

## Counts first

Every node here follows the same opening move:

1. **Build** a `DeferredBookQuery` — the SQL, not yet run. The builders are plain functions in [db/stores/book_store.py](../../../db/stores/book_store.py).
2. **Count** it with a `COUNT`. No rows are fetched.
3. **Preview** — fetch a few rows (4) and stream them as book cards, only when something matched.
4. **Hand on the query**, not the rows. A later node composes against it, so a narrowing step works over every match rather than over the four cards.

Zero matches is an answer, not a failure: every node here finishes ok when its query was built, whatever the count.

## Shared base

Every node's executor subclasses `BookWorkflow` ([base_workflow.py](base_workflow.py)):

- **`count_books(query)`** — runs the count and stamps `query`, `query_sql` and `num_books` on the output.
- **`fetch_books(query, limit)`** — returns rows for the caller to place (a preview, or the similarity node's anchors). Ranked by the query's `score` when it has one, by rating otherwise.
- **`stream_books(books)`** — sends book cards to the browser, skipping duplicates.

Each call opens its own database session for the round trip and closes it after.

`BookReaderWorkflow` is the same class without `count_books`, for work that reads and shows books but doesn't produce a book-shaped output (the reply stage).

## Output shapes

Every node returns a `BookRetrievalOutput` ([external.py](external.py)):

```
BookRetrievalOutput      num_books, query, query_sql, preview
├── BookAnchorOutput     books the user named (Retrieve_by_Title)
└── BookCandidateOutput  books matching a description (author, lexical, numeric, similar)
```

The split decides what a node can depend on. `Analyze_Similar_Books` takes only anchors — it folds the named books into one description, and folding hundreds of subject-search results describes nothing. `Combine_Intersect` takes any of the three, and its own output is the base class, so it can't anchor a similarity search.

`Book` ([schemas.py](schemas.py)) is the one book model, with every catalog column except the embedding. Narrow it where it's used (`model_dump(include=...)`) rather than declaring a smaller model.

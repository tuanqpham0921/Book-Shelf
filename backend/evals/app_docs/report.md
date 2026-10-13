# report

`evals/app_docs` holds BookShelf's eval records and its work on making the project's own docs searchable, the store `Retrieve_Project_Info` answers from. Unlike the rest of `evals/`, nothing here grades a call.

| Path | What it is |
|---|---|
| `results/` | past planner campaigns: each a `report.md` (cost) and `system_goals.md` (correctness) |
| `bugs/` | saved turns that showed a bug: the run's records, plus `notes.txt` saying what went wrong |
| `token_budget.ipynb` | sizes a do-it-yourself index over the repo; counts locally, spends nothing |
| `file_search_docs.ipynb` | uploads docs to an OpenAI vector store and queries it; spends money and leaves state on the account |

Neither notebook needs the backend or the database.

## `token_budget.ipynb`

Counts the tracked repo with `tiktoken` and turns that into chunks, index size and dollars.

```bash
cd backend && poetry run jupyter lab evals/app_docs/token_budget.ipynb
```

1. Takes the file list from `git ls-files`, so ignored files are already out.
2. Drops what is worthless to embed (lockfiles, CSVs, images, eval dumps) and counts notebooks by their source cells only.
3. Splits the rest into three corpora (core, core plus tests, everything) and breaks tokens down by area, file type and largest file.
4. Converts tokens to chunks, embedding cost and index size at the configured dimensions.
5. Compares the per-question cost of retrieving the top *k* chunks against pasting the whole corpus into the prompt.

It is committed without outputs, because stored notebook output is the largest source of junk tokens in the repo. Chat rates come from [airglider's price table](../../airglider/src/config.py); embedding rates are set in the notebook.

Last measured at commit `441d25e`:

| Corpus | Files | Tokens | Chunks (800/100) | Index MB (1024d) | Build cost |
|---|---|---|---|---|---|
| core (app, db, evals, config, docs, frontend src) | 193 | 169,960 | 345 | 1.41 | $0.0241 |
| core + tests | 226 | 217,690 | 427 | 1.75 | $0.0309 |
| everything tracked | 269 | 301,236 | 571 | 2.34 | $0.0431 |

- **Filtering matters more than chunking.** Unfiltered, the same files count about 595k tokens, half of it stored notebook output.
- **Scope matters more than either.** `playground/` and `tests/` were about 42% of the corpus and answer different questions from "how does this app work".
- **Cost does not decide it.** The core corpus fits in a context window; retrieval wins on precision and latency, not spend.

## `file_search_docs.ipynb`

The managed route: OpenAI's [file search tool](https://developers.openai.com/api/docs/guides/tools-file-search) owns chunking, embedding and retrieval. The notebook loads the docs, uploads them with `upload_and_poll`, and queries them two ways: `vector_stores.search` for raw chunks and scores, and `responses.create` with the `file_search` tool for an answer with citations.

- **It creates state on the OpenAI account.** The store is looked up by name (`book-recommender-docs`) and reused, so re-running does not duplicate it. The last cell, commented out, deletes the store and its files; deleting a store alone leaves the files behind.
- **The embeddings live at OpenAI, not in pgvector.**
- **Files upload with their path in the name** (`docs__design__node-taxonomy-v1.md`), since nearly every folder has a `README.md`.

The app searches the store named by `OPENAI_VECTOR_STORE_ID`, so a docs change reaches the chatbot only after the store is rebuilt.

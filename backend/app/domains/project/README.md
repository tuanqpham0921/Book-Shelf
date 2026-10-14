# Project domain

The project domain holds the BookShelf nodes that answer questions about BookShelf itself rather than about books: what it is, how it's built, what it can't do, where its code lives. Its answers come from the project's own documentation, not from the book catalog.

## Nodes

| Node | Folder | Answers |
|---|---|---|
| `Retrieve_Project_Info` | [find_project_info/](find_project_info/) | a question about BookShelf, from its docs |

The registered set is [guide.py](guide.py). Most project questions never reach the planner: triage's router runs `Retrieve_Project_Info` directly and answers from it, without a plan.

The domain has no shared base or schemas. Its one node subclasses `AppWorkflow` directly, because it reads no database and produces nothing book-shaped.

## Search: OpenAI file search

The docs are searched through an **OpenAI vector store**, not pgvector: OpenAI chunks, embeds and indexes the files, and the node calls `OpenAIClient.search_vector_store` for the closest chunks. The store is named by `OPENAI_VECTOR_STORE_ID` in `config/.env`. Left unset, every project lookup fails and the question goes to the planner.

How BookShelf uses it:

- **Raw search, not the `file_search` tool.** `search_vector_store` calls `vector_stores.search`, which returns chunks and scores with no model involved. The answer is a separate gpt-6-luna call the node builds itself, so the node controls the prompt, can reject, and records both steps on its trace. The hosted `file_search` tool in the Responses API would fold search and answer into one call.
- **OpenAI's defaults.** Files are chunked at 800 tokens with 400 of overlap. The search asks for 10 results (`OpenAIConstants.VECTOR_STORE_MAX_RESULTS`; the API allows 1 to 50), with no query rewriting and no attribute filters.
- **Cost.** Chunks come back as ordinary input tokens on the answer call, and they are most of a lookup's spend. Storage is free under 1 GB across all of the account's vector stores.

OpenAI's guides: [Retrieval](https://developers.openai.com/api/docs/guides/retrieval) (vector stores, `vector_stores.search`, chunking, pricing) and [File search](https://developers.openai.com/api/docs/guides/tools-file-search) (the hosted tool BookShelf doesn't use).

Because these docs are what the chatbot answers from, every README in the project is written so that one chunk makes sense on its own — see [docs/strategies/documentation.md](../../../../docs/strategies/documentation.md).

## Loading the docs

There is no command that loads the store yet. It is built by hand with [evals/app_docs/file_search_docs.ipynb](../../../evals/app_docs/file_search_docs.ipynb), which uploads the files and reuses the store by name, so re-running doesn't duplicate it. A doc edit reaches the chatbot only once the store is rebuilt.

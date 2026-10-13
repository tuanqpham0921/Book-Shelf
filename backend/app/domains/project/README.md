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

Because these docs are what the chatbot answers from, every README in the project is written so that one chunk makes sense on its own — see [docs/strategies/documentation.md](../../../../docs/strategies/documentation.md).

## Loading the docs

There is no command that loads the store yet. It is built by hand with [evals/app_docs/file_search_docs.ipynb](../../../evals/app_docs/file_search_docs.ipynb), which uploads the files and reuses the store by name, so re-running doesn't duplicate it. A doc edit reaches the chatbot only once the store is rebuilt.

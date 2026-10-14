_Plan the whole job, then run it._

PlanJane is BookShelf's planner. It turns your message into a short plan of tasks, and the rest of the system runs that plan. It is a layer on top of tool calling: instead of a model calling tools one at a time, PlanJane loads every tool up front and lays out the whole job in a single call.

---

## Why it exists

A chatbot accepts almost any input. BookShelf can only do a few things well, so it needs a dependable way to tell what is in scope, what isn't, and which of its abilities each part of a message needs.

When I started, I also didn't know what the abilities should be, or how they should hand results to each other. I needed a setup where adding or removing an ability was cheap, and where I could see the effect with a single query. A planner that builds a fresh graph for every message solved both problems.

---

## How it plans

Every ability (a **node**) has a plain-language description of what it does, when to use it and when not to. PlanJane reads all of them on every request, so the planner knows exactly what the system can do. That fits a self-contained app: it's better to show the planner everything and let it decide what's in scope than to hide abilities behind routing.

From that, PlanJane writes a plan. Each task names one node, the tasks it builds on, and an instruction written as an ordinary sentence:

```
"Books like The Alchemist with more than 300 pages"

1  Retrieve_by_Title            Find the book titled "The Alchemist".
2  Analyze_Similar_Books        Find books similar to "The Alchemist".     ← uses 1
3  Retrieve_by_Numeric_Traits   Find books with more than 300 pages.
4  Combine_Intersect            Keep the books found by both 2 and 3.      ← uses 2, 3
```

**Think of a language model writing text.** A language model produces one token at a time, and each token is predicted from the ones before it. PlanJane does the same with tasks: each task is a token, and a task can only build on the tasks already written. The plan is a short sentence in a language whose words are the system's abilities.

---

## How BookShelf uses PlanJane

In BookShelf, PlanJane is where the reasoning happens. Once the plan exists, each task is small and well defined, so the nodes can run on smaller, cheaper models.

The rest of BookShelf is built to call the planner only when it's needed. Common asks can go straight to a node as a promoted tool, and some fixed messages replay a recorded plan.

A plan also says which tasks don't depend on each other. Those could run in parallel, or on separate machines, though neither is built yet.

---

## Why use PlanJane

PlanJane is meant to get a project to a working MVP fast. You don't need to know your final design to start: write a few nodes, ask questions, and let the plans show you what's missing.

- **It maps your nodes and capabilities.** One plan shows every tool the model picked for a question and how they connect, without running anything step by step. A wrong pick, a missing node or two nodes that overlap show up right away.
- **It's an easy step to a fixed graph.** Once the plans show which nodes your app needs and how they connect, a common plan can be cached, or a well-worn path turned into a traditional fixed graph.
- **Adding a node is simple.** Write the node and its description, and the planner picks it up. There's no routing to rewire and nothing to mock. One query shows whether the planner uses it the way you meant.
- **It's cheaper than it looks.** The planner runs on a frontier model, but the list of nodes is identical on every request, so the prompt cache serves almost all of it and the cache hit rate stays high. The output is only a few short lines, so little is written. A heavy model at the front ends up costing little.
- **It isn't tied to books.** The prompt is written to be generic, with nothing about books in it. Everything specific to the domain lives in the node descriptions, so the same planner could serve another domain.
- **Instructions are sentences.** Each task's instruction is self-contained: it carries every title, name and number the node needs. A node can be tested by handing it a sentence, with no planner involved. Routing happens once, at planning time, so a run has fewer random choices in it.
- **You see the plan before it runs.** The plan is drawn as a diagram before any task starts. That makes the system transparent, and it is the natural place for a human to step in and say "continue?" before anything runs.
- **Prompts stay focused.** The planner's prompt only has to teach planning. Fine-tuning and examples go in each node's own prompt, where they affect that node alone, so there's more room for them.
- **Costs are predictable.** The catalog is fixed and a plan is capped at ten tasks, so a turn's cost has a ceiling, known before anything runs. Once re-planning exists, capping the number of re-plans keeps that ceiling.
- **Less schema overhead.** The catalog is sent as plain text, like documentation: each node's name and description. With ordinary tool calling, every tool ships a full JSON schema of fields, types and nesting. Here the model fills one small schema, the plan, so those tokens are never sent.

---

## Limitations

- **It can't plan around what it hasn't seen yet.** "Do you have Dune? Then recommend me something like it" needs the first answer before deciding the second step. A plan is written before anything runs, so it can't do that. A checkpoint task that pauses and re-plans would fix this, but it isn't built.
- **More testing is needed.** The planner did reasonably well against a catalog of about 30 nodes, far more than BookShelf has today, so there's room to grow. That needs more evaluation data before it can be relied on.
- **Each message stands alone.** The planner sees only the current message, not earlier turns. Feeding it the conversation and the tasks already run would let it write the next tasks from them, continuing a conversation the way a language model continues text, but that isn't built.
- **Cost grows with the catalog.** The cache keeps a frontier model affordable today, but every node's description is sent on every request. Each new node adds to every call, so a much larger catalog will cost noticeably more.
- **Nodes must be clearly defined.** When two nodes overlap, the planner can't tell which one to pick, and its choice between them becomes more random. Each description needs to say when to use the node and when not to.
- **Everything rests on the planner.** Adding a node is simple and testing is easy, but a model choosing the route is less precise than a fixed graph where every path is wired by hand. As models keep getting smarter and cheaper, that trade-off keeps getting better.

---

> _Feedback and suggestions are always welcome at_ **tuanqpham0921@gmail.com**
>
> _For more technical details, visit the_ [GitHub repository](https://github.com/tuanqpham0921/Book-Shelf).

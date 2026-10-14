_Every step comes back in an envelope._

airglider is the small run engine underneath BookShelf. It runs each step of a turn and hands back a record of what happened, for the system and for you. It lives in the BookShelf repo but imports nothing from it, so it can become a package of its own.

---

## Why it exists

A single BookShelf turn can make several LLM calls, database queries and nested steps, each of which can fail, run slowly or cost money. I needed a way to log and keep track of all of it. I also wanted to stop wrapping every call in `try`/`except`, which was spreading through the codebase and hiding where things actually went wrong.

airglider solves both with two ideas: **every step returns an envelope**, and **every step gets that behaviour by inheriting it.**

---

## The envelope

Think of each step as sending you a letter. You always get an envelope back, even when the step failed. The label on the front tells you how it went. The letter inside is the result. You decide whether to open it.

```
OperationResult             the envelope
├── name, description       who sent it
├── ok                      did the step run to completion?
├── timing                  when it started, how long it took
├── input                   what it was given
├── response                the result: the letter inside
├── token_usage             tokens, per-model split, cost in dollars
├── runtime_error           what went wrong (empty when ok)
├── details                 notes the step added along the way
└── steps                   the envelopes of every step it ran
```

**Errors don't crash the system.** A step that raises is caught and recorded in its own envelope, and the caller carries on. The caller has two choices:

```python
step = await rank_books(query)        # look at the envelope, decide yourself
if not step.ok:
    add_details("ranking failed, keeping catalog order")

count = (await count_books(query)).unwrap()   # open it: the result, or stop here
```

`unwrap` stops only the step that called it. The level above gets an envelope saying why and makes its own call. One failed step never takes down the whole turn.

---

## Inheritance philosophy

airglider's main design choice is that a step becomes traced by **what it is built on**, not by code added to it. There are only two ways in: subclass `Workflow`, or decorate a function with `@task`.

```python
@task(description="Counts matching books")
async def count_books(query) -> int:
    ...

class FindBooks(Workflow[BookList]):
    description = "Finds books"

    async def run(self, query):
        self.result.count = (await count_books(query)).unwrap()
        self.record.ok = True
```

- **`@task`** wraps one async function. It returns the result, and the decorator builds the envelope.
- **`Workflow`** is a base class for a process with several steps. Subclass it, then override `run()`. An app adds its own layer on top: BookShelf's `AppWorkflow` adds streaming and LLM helpers, and every BookShelf step inherits from it.

Because every step shares the same machinery, the behaviour that is hard to get right by hand comes for free:

- **Errors travel up.** A failure is recorded on its own envelope and handed to the step that called it, which decides what to do.
- **Cancellations are carried through.** When a user closes the chat, every step still running records the cancellation on its envelope and passes it on, rather than swallowing it.
- **The tree builds itself.** Either kind can call the other at any depth, and each lands in its caller's `steps`. You never attach a step by hand.

Nothing is wired up per step. A plain function isn't traced; if it raises, its nearest traced caller records the error.

---

## Cost and usage on every step

Each envelope carries its own tokens and dollar cost, and a parent adds up its children. That shows where a turn spends its time and money. A slow query or an expensive prompt is visible at the step where it happens, which is where bottlenecks and optimizations are found.

---

## How to read an envelope

Envelopes nest: a step's envelope holds the envelopes of the steps it ran. There are two ways to read the result.

- **Recursive view:** read it as a tree, top down. The turn holds triage, the planner and each task, and each task holds its own LLM call and queries. This is how BookShelf's log button shows a turn.
- **Flat view:** `record.flatten()` lays every step out in one list, parent before child. Each entry is the same envelope without its `steps`, plus a `parent_id` naming the step that ran it, so the tree can be rebuilt from the list alone. Use it to sort by duration or cost, or to find every step that failed.

```
OperationResult (flat)      one entry in the list
├── parent_id               who called it
├── ...                     every other field, as above
└── (no steps)              its children are their own entries
```

When reading one, remember that **`ok` means "ran to completion", not "the result is good".** A search that found nothing is still `ok`. The caller reads the result and decides whether it is enough.

---

## Small on purpose

airglider is a lightweight run engine in the same family as Temporal, Pydantic AI and other workflow tools, but much smaller. There are no workers, queues or servers to run, and only a handful of rules to learn. It is just inheritance and a decorator, which makes it a beginner-friendly way into the idea.

It also leaves things out on purpose:

- **No retries.** To retry, call the `@task` again or build a new `Workflow`.
- **No checkpointing or resuming.** A run lives in memory until it finishes.
- **Untyped errors.** A crash and a business failure, such as "no books to compare", both land in `runtime_error`.

These are the next additions, made only when BookShelf needs them.

---

> _Feedback and suggestions are always welcome at_ **tuanqpham0921@gmail.com**
>
> _For more technical details, visit the_ [GitHub repository](https://github.com/tuanqpham0921/Book-Shelf).

_A book assistant that shows you how it thinks._

BookShelf is a chat assistant for one shelf of about 5,000 books. Ask it for books by an author, books about a subject, books like one you loved, or books under a certain length, and it answers only from that shelf. While it works, it shows you its plan and every step it takes.

---

## Why BookShelf

General chatbots are good at sounding sure of themselves. Ask one for books and it may suggest a title that doesn't exist, or describe a real book wrongly, and you can't see where the answer came from.

BookShelf takes the opposite approach:

- **It only knows its own shelf.** It doesn't search the internet or rely on what the AI model remembers about books. If a book isn't on the shelf, BookShelf says so instead of inventing one.
- **It plans before it acts.** Your message is turned into a short plan of small, clear tasks, such as "find books by this author" and then "keep the ones under 300 pages". You see the plan before anything runs.
- **It shows its work.** Every task shows what it understood from your message, how it searched and what it found. Nothing happens behind a curtain.

Books are the example. The real subject is the idea underneath: an AI assistant you can look *through*, not just at.

---

## What the current version support

| Ask for | For example |
|---|---|
| A book by name | "Do you have The Hobbit?" |
| An author's books | "What do you have by Ursula K. Le Guin?" |
| Books on a subject | "Non-fiction about World War II for adults" |
| Books by length, year or rating | "Well-rated books under 200 pages" |
| Books like ones you liked | "Books like The Alchemist" |
| Several of these at once | "Books like The Alchemist with more than 300 pages" |
| Questions about BookShelf itself | "How does BookShelf find similar books?" |

When you combine asks, BookShelf narrows the results the way you'd expect. "Books like The Alchemist with more than 300 pages" keeps the closest matches in order, then keeps only the long ones.

---

## What you'll see

**The plan comes first.** Each answer starts with a small diagram of the steps BookShelf is about to take and how they connect.

**Every step can be opened.** Each step has its own folded section showing what it understood from your message, how it searched, how many books matched, how long it took, and a preview of what it found.

**The answer reads like a reply.** BookShelf writes a short response, and the only book cards it shows are the ones the text talks about.

**The full record is yours.** The log button shows every step of the turn. When you ask about BookShelf itself, the Sources button lists the pages the answer came from.

**Feedback on every answer.** A thumbs up or down, plus a comment, tells me what worked and what didn't.

**A bookish look.** A serif typeface on black, white and gray, so it reads like a printed page. Color appears only where it makes something easier to read.

---

## Honest when it can't help

A good assistant knows its limits and tells you about them.

- **Unclear messages get a question back.** If BookShelf can't tell what you mean, it asks instead of guessing.
- **Unsupported asks are named.** If part of your message is something BookShelf can't do, the reply says so, and still answers the part it can.
- **Misuse is turned away politely.** Asking for other people's data or trying to trick it gets a plain refusal.
- **Nothing ends in silence.** If a step breaks, the reply explains what went wrong in plain words.

The suggested prompts include tabs for things BookShelf *can't* do and for attempts to break it. Showing where it fails is part of being open about how it works.

### What it doesn't do yet

- **Each message stands alone.** BookShelf doesn't remember earlier messages, so a follow-up like "more like that one" needs the book named again.
- **It knows what's on the cover, not what's inside.** The shelf holds each book's author, year, length, rating, shelf, genre and blurb. It can't tell you who the main character is.
- **Mood is hard.** "Cozy mysteries" finds mysteries; the "cozy" gets lost for now.
- **No accounts.** No saved books, preferences or reading history yet.

---

## Built with developers in mind

BookShelf is designed for the people who build on it as much as for the people who use it. This first release is deliberately small. The goal was a solid foundation, not a long feature list, so that adding to BookShelf stays easy.

**Project information is built into the chat.** BookShelf's documentation is part of the assistant itself. A developer can ask "how do I add a new ability?" or "why does it count books before fetching them?" and get an answer, with the pages it came from, instead of hunting through files. New contributors get up to speed faster, everyone gets answers in the same place they test the app, and a wrong page shows up quickly as a wrong answer.

**Each new ability is one self-contained piece.** Teaching BookShelf something new, such as comparing two books, means adding one piece that the planner learns to use on its own. Nothing else has to be rewired.

**Every step is recorded.** Each step leaves a full record of what went in, what came out and how long it took, the same record you see in the log. When something goes wrong, the cause is easy to find.

**Changes are tested.** A set of test questions checks that the planner still makes the right plans after every change, including tricky and adversarial ones. The planner has also been tested against a much larger set of abilities than BookShelf has today, so there is plenty of room to grow.

**Parts are built to travel.** The planner and the step-recording engine are written to stand on their own, so either can become its own project later. You can read about them on the [PlanJane](/planjane) and [airglider](/airglider) pages.

---

## What's next

- **Conversations that remember,** so a follow-up can build on the last answer.
- **Checking in mid-plan:** BookShelf shows its plan and asks "continue?" before running it.
- **More abilities,** such as comparing books, looking one up by ISBN, or a surprise pick.
- **Accounts,** for saved books, preferences and reading history.
- **Faster answers,** by running independent steps at the same time.

---

> _Feedback and suggestions are always welcome at_ **tuanqpham0921@gmail.com**

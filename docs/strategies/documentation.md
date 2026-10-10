# General rules
* three layers, each answers one question
    * README - what it is, how to use it (changes when behaviour changes)
    * docs/ - why it is built this way, what's next (changes when a decision is made)
    * code - how this line works, what to watch for (changes with the code)
* the test: would a new dev need this to use or change the code today?
    * yes -> README
    * only explains why / what came before -> decision record
    * about one line -> code comment
* no history in READMEs
    * no dates, no "since ...", "used to", "renamed from", "retired because"
    * a README only says what is true now
    * history lives in git and decision records
* one home per fact
    * route tables, request flow, etc. live in one place, others link to it
* no TODOs or internal notes in READMEs
    * they go to docs/backlog.md
    * READMEs are served to users by Retrieve_Project_Info (vector store)
* steps vs strategy
    * how-to steps (deploy, db setup) -> backend/frontend READMEs
    * why (deploy choices, eval approach) -> docs/strategies/

# READMEs
* should be concise, chunk into smaller digestable using
    * subfolder, 1 sentence of high level implementations/functions
* each should have an intro
    * first sentence names its subject ("PlanJane is the planner that ..." not "This folder ...")
    * a retrieved chunk has to make sense on its own for the chatbot

## Highest level
    * contain purpose and demo links
    * basically a table of content
    * does not hold set up (route to the actual page)

## sub READMEs
    * high level functions
    * no need for folder structure (most are self-explanatory)
    
### frontend/backend
    * this is where the set up instruction should be
    * for dev and deployment
    * also have the technology use here
    * no need for folder structure or files explanations
    * common/useful make commands

## READMEs with schemas
    * envolope, output, dataclasses etc... should have a formatted strucutre in the readme
    * high-level shape only (small diagram or 3-4 line sketch), link to external.py for the fields
    * don't copy field lists - they drift the moment a field changes

# Node READMEs
    * intro - similar to request in external but higher level
    * flow in a diagram
    * tools - high level 1-2 sentences
    * contracts schema (high-level)
    * optional others (models, design, caching ...)

# packages / utils
    * things like clients, airglider, commons, ...
    * intro / purpose (optional)
    * usage and stuff (high level)
    * lower implementations can be in the source code or subfolder READmes

---
# Code
* should have a comment at the top on what it does

## Workflow/Airglider
    * workflow should have 1, 2, ... enumerated steps
    * @task should have description

## formatting
    * WorkflowExcutor should be on top
    * helper and other functions should be lowered
    * inline comments for clarity
        * should be concise
        * can be longer using NOTE: and designs/things to watch out for

## node request docstrings are prompt text
    * the docstring on a node's request schema is the planner's tool description
    * the comment rules above don't apply - edit it like a prompt, check with make tools-catalog

---
# Decision records
* docs/decisions/NNN-title.md, one decision per file
    * Context - what problem, what constraints
    * Decision - what we chose
    * Consequences - what it costs, what it rules out
    * Status - accepted / superseded by NNN
* dates and history are fine here (this is the history layer)
* READMEs state the current rule in one line and link here for the why
* keep them short - the old docs/design/ files were this, just too long

---
# CLAUDE.md
* rules for agents, not a second architecture doc
    * "Before Generating New Code" rules
    * commands
    * files to avoid
    * pointers to READMEs and docs/
* no history, no restating what a README already says

---

# Eval Report
* maybe for later, now, just trying to have .md report to show as much as possible
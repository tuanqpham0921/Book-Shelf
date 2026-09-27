from pydantic import BaseModel, Field

from db.schema import AudienceEnum, GenreEnum


class FindByLexicalTraitsArgs(BaseModel):
    """Split one lexical ask into words to search for and shelves to keep.

    Deliberately narrow, and deliberately not `BooksFilter` — that model already
    carries `keywords`, `categories` and `genre` and will look like the reusable
    option. It is the parked `Retrieve_Random` filter, and putting a `BooksFilter`
    on anything the planner reaches is what the V1 taxonomy decision removed.

    Examples:
        "Show me children's books."
            audience: children
        "Non-fiction about artificial intelligence."
            keywords: ["artificial intelligence"], genre: non-fiction
        "Any good mysteries?"
            keywords: ["mystery"] — "good" is a rating bound, not a subject, and
            nothing here can apply it
        "Books about ninjas."
            keywords: ["ninja"]
        "Children's books about space."
            keywords: ["space"], audience: children
    """

    keywords: list[str] = Field(
        default_factory=list,
        max_length=4,
        description=(
            "Subject words to find in the book's title, shelf label or "
            "description. Every keyword must appear, so fewer and more specific "
            "finds more: 'ninja' matches 1 book, 'space' 78, 'war' 442. Use the "
            "plain noun ('ninja', not 'ninja stories') — matching is by word "
            "stem, so plurals and tenses are handled for you. Leave empty when "
            "the request names no subject, only a shelf or an audience."
        ),
    )
    genre: GenreEnum | None = Field(
        default=None,
        description=(
            "Fiction or non-fiction — the only two the catalog distinguishes. "
            "Every finer shelf word ('mystery', 'history', 'romance', "
            "'biography') is a keyword instead, not a genre. Omit when the "
            "request did not say."
        ),
    )
    audience: AudienceEnum | None = Field(
        default=None,
        description=(
            "Who the book is for. Use 'children' for \"kids' books\", "
            "\"children's books\", 'for a 7 year old', 'young readers'. Use "
            "'adult' only when the request rules children out ('not a kids "
            "book'). Omit when it did not say."
        ),
    )

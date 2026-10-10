"""Retrieve_by_Numeric_Traits's internal parse schema (never seen by the planner)."""

from pydantic import BaseModel, Field

from db.schema import BookMetadataFilter


class FindByNumericTraitsArgs(BaseModel):
    """Turn the query into measurable bounds, whether it states figures or words.

    Always fill in at least one bound: every query that reaches here has
    something measurable in it, and a vague word IS a bound — "obscure" and
    "really long" are as fillable as "under 200 pages". Returning nothing is the
    one wrong answer.

    Examples:
        "Find books with fewer than 200 pages."
            max_pages: 200
        "Show me some well rated books."
            min_rating: 4.0
        "Show me the highest rated books you have."
            min_rating: 4.3 — a superlative is the tighter bound, not an ordering
        "Find me obscure books nobody has heard of."
            max_ratings_count: 1000 — few people rated it, not badly rated
        "What books do you have from the classical period?"
            max_year: 1970
        "I want something really long."
            min_pages: 500
        "Your most popular books."
            min_ratings_count: 10000
        "Books between 300 and 500 pages published after 2015."
            min_pages: 300, max_pages: 500, min_year: 2015
    """

    # what one bound means is on `BookMetadataFilter`'s field descriptions; the
    # docstring examples above show combinations, which no field can
    # NOTE: without the examples, gpt-5-nano returned an empty filter for
    # "obscure" and "really long".
    # NOTE: `is_children` targets `books.is_children`, which is NULL on every
    # row — setting it matches nothing. Audience belongs to
    # Retrieve_by_Lexical_Traits.
    traits: BookMetadataFilter = Field(
        ...,
        description="Measurable bounds to search the whole catalog by.",
    )

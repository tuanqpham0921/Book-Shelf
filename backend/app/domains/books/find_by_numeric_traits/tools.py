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

    # The per-field mapping lives on `BookMetadataFilter` rather than here. It
    # was shared with Filter_Retrieval's args until 2026-08-24, so that the two
    # could not calibrate "well rated" differently; that node is gone and this
    # is now the only shipper, but the split still earns its keep — the field
    # descriptions say what one bound means, and the examples above show
    # *combinations*, which no single field description can. This is the one
    # node whose whole job is the inference, so it is worth the tokens here.
    # Measured: without them, gpt-5-nano returned an empty filter for "obscure"
    # and "really long".
    #
    # `BookMetadataFilter` also carries `is_children`, a flag rather than a
    # measurement. Retrieve_by_Lexical_Traits now owns audience, and did *not* take
    # this field with it: it resolves audience against `books.genre`, while this
    # one still targets `books.is_children`, which is NULL on all 5,197 rows and
    # matches nothing. Setting it here is a silent zero — known and accepted;
    # see the note on `BookMetadataFilter.is_children`.
    traits: BookMetadataFilter = Field(
        ...,
        description="Measurable bounds to search the whole catalog by.",
    )

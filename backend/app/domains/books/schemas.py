"""`Book`, the one book model above the database layer.

The output shapes nodes return are in `external.py`.
"""

from pydantic import BaseModel


class Book(BaseModel):
    """Every `books` column except the embedding, as `BookModel.to_dict()`
    returns it.

    Narrow at the point of use (`model_dump(include=...)`), never with a
    second, smaller model.

    NOTE: field names are persisted in `chat_runs.tasks` and read back by the
    review page and eval reports — renaming one breaks older rows. The
    embedding stays out so it never bloats those records.
    """

    isbn13: str
    title: str
    isbn10: str | None = None
    authors: str | None = None
    categories: str | None = None
    genre: str | None = None
    published_year: int | None = None
    num_pages: int | None = None
    average_rating: float | None = None
    ratings_count: int | None = None
    is_children: bool | None = None
    description: str | None = None
    thumbnail: str | None = None
    title_and_subtiles: str | None = None

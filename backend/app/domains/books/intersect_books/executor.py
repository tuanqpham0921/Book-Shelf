"""Combine_Intersect's executor: AND the upstream queries, count, preview a few.

The one node with no LLM call — what it does is decided by which goals it
depends on.
"""

from app.domains.books.base_workflow import BookWorkflow
from app.domains.books.external import BookRetrievalOutput
from db.stores import DeferredBookQuery

from .external import CombineIntersectInput, CombineIntersectOutput


class CombineIntersectExecutor(BookWorkflow[CombineIntersectOutput]):
    description = "Keeps only books every step found"

    ui_loading_message = "narrowing the results..."

    async def run(self, node_input: CombineIntersectInput) -> None:
        """AND the upstream queries in SQL and hand the intersection on."""
        await self.sse_stream.send_ui_loading(self.ui_loading_message)

        # 1. read the upstream queries, and show their counts in the details
        upstream = anchor_queries(node_input.anchors)
        self.add_details(
            " ∩ ".join(str(anchor.num_books) for anchor in node_input.anchors)
        )
        if len(upstream) < 2:
            raise ValueError(
                f"Nothing to intersect: {len(upstream)} of "
                f"{len(node_input.anchors)} results carry a query. Every "
                "registered retrieval hands one on, so this is a malformed "
                "upstream output rather than a plan this node can be asked to fix"
            )

        # 2. AND the queries and count — no rows fetched
        # NOTE: intersecting queries, not previews, keeps the count over every
        # upstream match, and `compose` carries a similarity pool's score
        # through an "and", so cosine order survives.
        deferred = DeferredBookQuery.compose(upstream, op="and", label="intersected")
        total = (await self.count_books(deferred)).unwrap()

        # 3. preview cards, only when something survived
        # NOTE: downstream nodes read `self.result.query`, never `preview`.
        if total:
            self.result.preview = (await self.fetch_books(deferred)).unwrap()
            await self.stream_books(self.result.preview)

        # 4. finalize — ok is read off the output
        self.finalize_result()

    def finalize_result(self):
        # NOTE: ok means "the conditions were ANDed and counted", not "something
        # survived" — an empty intersection is an answer. No `args` half: this
        # node parses nothing.
        ok = self.result.query is not None
        return super().finalize_result(ok=ok)


def anchor_queries(anchors: list[BookRetrievalOutput]) -> list[DeferredBookQuery]:
    """The upstream queries to intersect.

    NOTE: every registered retrieval fills `query`, so a dropped anchor means a
    malformed upstream output — `run` raises when fewer than two survive.
    """
    return [anchor.query for anchor in anchors if anchor.query is not None]

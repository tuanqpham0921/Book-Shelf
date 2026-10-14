"""Small text helpers shared by the prompt renderers."""


def truncate_str(text: str, limit: int, collapse: bool = True) -> str:
    """Cut at a word boundary so a clipped description doesn't end mid-word.

    `collapse` folds the internal whitespace of a single document onto one
    line; the assembled block passes False, because the blank lines between
    documents are what separate them.
    """
    text = " ".join(text.split()) if collapse else text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"

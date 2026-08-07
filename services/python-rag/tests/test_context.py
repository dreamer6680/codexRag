from app.context import ContextBuilder
from app.models import Citation


def citation(text: str) -> Citation:
    return Citation(
        document_id="doc-1",
        document_name="demo",
        version=1,
        excerpt=text,
        confidence=0.9,
    )


def test_context_deduplicates_and_obeys_budget():
    context, selected = ContextBuilder(max_chars=22).build(
        [citation("same text"), citation("same   text"), citation("another long text")]
    )

    assert context.startswith("[1] same text")
    assert len(context) <= 22
    assert len(selected) == 2

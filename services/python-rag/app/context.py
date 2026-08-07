"""Context construction with deduplication and a hard prompt-size budget."""
from .models import Citation


class ContextBuilder:
    def __init__(self, max_chars: int) -> None:
        self.max_chars = max_chars

    def build(self, citations: list[Citation]) -> tuple[str, list[Citation]]:
        blocks: list[str] = []
        selected: list[Citation] = []
        seen: set[str] = set()
        used = 0
        for citation in citations:
            normalized = " ".join(citation.excerpt.split())
            if not normalized or normalized in seen:
                continue
            label = len(selected) + 1
            block = f"[{label}] {normalized}"
            remaining = self.max_chars - used
            if remaining <= 4:
                break
            if len(block) > remaining:
                block = block[: remaining - 1] + "…"
            blocks.append(block)
            selected.append(citation)
            seen.add(normalized)
            used += len(block) + 2
        return "\n\n".join(blocks), selected

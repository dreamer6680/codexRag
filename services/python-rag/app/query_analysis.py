"""Deterministic query and chunk tokenization for Chinese/English RAG."""

from dataclasses import dataclass
import re


# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------

# English words, technical names, versions, URLs/domains fragments, etc.
LATIN_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9_.+\-/:#]*"
)

# Chinese continuous text
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]+")

# Quoted / book-title expressions.
QUOTED_RE = re.compile(
    r"[《“\"']([^》”\"']+)[》”\"']"
)

# Common Chinese company suffixes.
COMPANY_RE = re.compile(
    r"[\u4e00-\u9fffA-Za-z0-9]{2,}"
    r"(?:股份有限公司|有限责任公司|有限公司|集团)"
)


# ---------------------------------------------------------------------------
# Query normalization
# ---------------------------------------------------------------------------

# These are query-level function words, not domain-specific business words.
# Do NOT put words such as "岗位", "职责", "题目" here.
QUERY_STOP_PHRASES = (
    "请问",
    "什么",
    "哪些",
    "怎么",
    "如何",
    "为什么",
    "是否",
    "能否",
    "可以",
    "有没有",
    "帮我",
    "告诉我",
    "介绍一下",
    "请介绍",
    "我想知道",
    "我想了解",
    "这个",
    "那个",
    "我的",
    "相关",
    "信息",
)


@dataclass(frozen=True)
class QueryAnalysis:
    """Normalized information extracted from a user query."""

    tokens: list[str]
    exact_terms: list[str]
    relations: set[str]


def _unique(*values: list[str]) -> list[str]:
    """Stable de-duplication while preserving insertion order."""
    return list(
        dict.fromkeys(
            value.strip()
            for value in values
            if value and value.strip()
        )
    )


def _normalize_chinese(text: str) -> str:
    """Remove generic query-function words from Chinese text."""
    cleaned = text

    for phrase in QUERY_STOP_PHRASES:
        cleaned = cleaned.replace(phrase, "")

    # Remove common leading function characters.
    cleaned = cleaned.lstrip("在于从是的对与跟和及为")

    return cleaned


def _chinese_tokens(text: str) -> list[str]:
    """
    Generate deterministic Chinese retrieval tokens.

    Strategy:
    - 2-gram: high recall
    - 3-gram: better phrase discrimination
    - 4-gram: useful for technical/domain phrases
    - full phrase for short runs

    This avoids relying on an external Chinese segmentation library while
    giving BM25 more useful phrase-level signals than only 2-grams.
    """
    values: list[str] = []

    for run in CHINESE_RE.findall(text):
        cleaned = _normalize_chinese(run)

        if len(cleaned) < 2:
            continue

        # 2/3/4-grams
        for size in (2, 3, 4):
            if len(cleaned) >= size:
                values.extend(
                    cleaned[index:index + size]
                    for index in range(len(cleaned) - size + 1)
                )

        # Preserve the complete phrase when it is reasonably short.
        if 2 <= len(cleaned) <= 16:
            values.append(cleaned)

    return values


def tokenize_text(
    text: str,
    *,
    keywords: list[str] | None = None,
    entity_phrases: list[str] | None = None,
) -> list[str]:
    """
    Tokenize arbitrary Chinese/English RAG text.

    Designed for both:
    - vector-store lexical indexing
    - user-query lexical retrieval
    """

    values: list[str] = []

    # English / technical identifiers.
    values.extend(
        token.lower()
        for token in LATIN_RE.findall(text)
        if len(token) >= 2
    )

    # Chinese n-grams.
    values.extend(_chinese_tokens(text))

    # Explicit metadata should receive phrase-level tokens.
    for value in (keywords or []) + (entity_phrases or []):
        normalized = value.strip().lower()

        if not normalized:
            continue

        values.append(normalized)

        values.extend(
            token.lower()
            for token in LATIN_RE.findall(value)
            if len(token) >= 2
        )

        values.extend(_chinese_tokens(value))

    return _unique(values)


def _extract_relation_terms(question: str) -> set[str]:
    """
    Extract generic semantic relation signals.

    These are intentionally domain-neutral. They describe what the user
    wants to know rather than assuming the document is a resume.
    """
    relations: set[str] = set()

    relation_groups = {
        "definition": (
            "是什么",
            "什么是",
            "含义",
            "定义",
            "意思",
            "概念",
        ),
        "reason": (
            "为什么",
            "原因",
            "原理",
            "为什么要",
        ),
        "method": (
            "怎么做",
            "如何做",
            "如何实现",
            "怎么实现",
            "方法",
            "步骤",
            "流程",
        ),
        "comparison": (
            "区别",
            "不同",
            "比较",
            "对比",
            "哪个更好",
            "优缺点",
        ),
        "summary": (
            "总结",
            "概括",
            "综述",
            "介绍",
            "主要内容",
            "核心内容",
        ),
        "time": (
            "什么时候",
            "何时",
            "时间",
            "日期",
            "多久",
        ),
        "location": (
            "哪里",
            "地点",
            "位置",
            "地址",
        ),
        "person": (
            "谁",
            "人物",
            "作者",
            "负责人",
        ),
        "quantity": (
            "多少",
            "数量",
            "几个",
            "几项",
            "比例",
            "占比",
        ),
    }

    for relation, phrases in relation_groups.items():
        if any(phrase in question for phrase in phrases):
            relations.add(relation)

    return relations


def analyze_query(question: str) -> QueryAnalysis:
    """
    Analyze an arbitrary user query.

    No document-domain assumptions are made here.
    """

    normalized_question = question.strip()

    latin = [
        token.lower()
        for token in LATIN_RE.findall(normalized_question)
        if len(token) >= 2
    ]

    companies = [
        match.strip().lstrip("在于从")
        for match in COMPANY_RE.findall(normalized_question)
    ]

    quoted = [
        match.strip().lower()
        for match in QUOTED_RE.findall(normalized_question)
        if match.strip()
    ]

    # Exact terms should contain phrases likely to be intentionally searched.
    exact_terms = _unique(
        latin,
        companies,
        quoted,
    )

    relations = _extract_relation_terms(normalized_question)

    tokens = tokenize_text(
        normalized_question,
        entity_phrases=companies,
    )

    return QueryAnalysis(
        tokens=tokens,
        exact_terms=exact_terms,
        relations=relations,
    )
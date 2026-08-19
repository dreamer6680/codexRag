"""Deterministic query and chunk tokenization for Chinese/English RAG."""
from dataclasses import dataclass
import re


LATIN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.+-]{1,}")
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]+")
COMPANY_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]{2,}(?:股份有限公司|有限责任公司|有限公司|集团)")
QUOTED_RE = re.compile(r"[《“\"']([^》”\"']+)[》”\"']")
STOP_PHRASES = (
    "请问", "什么", "哪些", "怎么", "如何", "为什么", "是否", "我的", "这个", "那个",
    "负责", "岗位", "职位", "职务", "职责", "工作内容", "需要", "相关", "信息",
)


@dataclass(frozen=True)
class QueryAnalysis:
    tokens: list[str]
    exact_terms: list[str]
    relations: set[str]


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _chinese_tokens(text: str) -> list[str]:
    values: list[str] = []
    for run in CHINESE_RE.findall(text):
        cleaned = run
        for phrase in STOP_PHRASES:
            cleaned = cleaned.replace(phrase, "")
        cleaned = cleaned.lstrip("在于从是的")
        if len(cleaned) >= 2:
            values.extend(cleaned[index : index + 2] for index in range(len(cleaned) - 1))
        if 2 <= len(cleaned) <= 12:
            values.append(cleaned)
    return values


def tokenize_text(
    text: str,
    *,
    keywords: list[str] | None = None,
    entity_phrases: list[str] | None = None,
) -> list[str]:
    values = [token.lower() for token in LATIN_RE.findall(text)]
    values.extend(_chinese_tokens(text))
    for value in (keywords or []) + (entity_phrases or []):
        normalized = value.strip().lower()
        if normalized:
            values.append(normalized)
            values.extend(token.lower() for token in LATIN_RE.findall(value))
            values.extend(_chinese_tokens(value))
    return _unique(values)


def analyze_query(question: str) -> QueryAnalysis:
    latin = [token.lower() for token in LATIN_RE.findall(question)]
    companies = [match.lstrip("在于从") for match in COMPANY_RE.findall(question)]
    quoted = [match.strip().lower() for match in QUOTED_RE.findall(question)]
    exact_terms = _unique(latin + companies + quoted)
    relations: set[str] = set()
    if any(term in question for term in ("岗位", "职位", "职务")):
        relations.add("position")
    elif any(term in question for term in ("负责", "职责", "工作内容", "做了什么")):
        relations.add("responsibilities")
    if any(term in question for term in ("题目", "标题")):
        relations.add("title")
    return QueryAnalysis(tokens=tokenize_text(question, entity_phrases=companies), exact_terms=exact_terms, relations=relations)


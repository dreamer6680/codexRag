from app.query_analysis import analyze_query, tokenize_text


def test_query_analysis_preserves_fastgpt_and_position_intent():
    analysis = analyze_query("在FastGPT负责什么岗位")

    assert "fastgpt" in analysis.tokens
    assert "fastgpt" in analysis.exact_terms
    assert "position" in analysis.relations


def test_query_analysis_extracts_full_company_and_responsibility_intent():
    analysis = analyze_query("在珠海环届云有限公司负责什么")

    assert "珠海环届云有限公司" in analysis.exact_terms
    assert "responsibilities" in analysis.relations
    assert "珠海" in analysis.tokens


def test_tokenizer_uses_indexed_entities_and_chinese_bigrams():
    tokens = tokenize_text(
        "岗位：全栈研发",
        keywords=["FastGPT"],
        entity_phrases=["珠海环届云有限公司"],
    )

    assert "fastgpt" in tokens
    assert "珠海环届云有限公司" in tokens
    assert "全栈" in tokens

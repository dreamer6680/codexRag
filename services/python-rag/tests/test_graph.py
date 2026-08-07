from app.graph import build_graph, evidence_gate


def test_no_evidence_always_refuses():
    assert evidence_gate({"question": "不存在的内容", "citations": []}) == "refuse_answer"


def test_graph_compiles_without_state_key_collision():
    assert build_graph() is not None

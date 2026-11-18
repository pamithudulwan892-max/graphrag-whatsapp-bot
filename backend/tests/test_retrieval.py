from app.embeddings import HashEmbedder
from app.graph.extractor import Entity, Extraction, HeuristicExtractor, Relation
from app.graph.store import GraphStore, norm_key
from app.retrieval.bm25 import BM25
from app.retrieval.graph_retriever import GraphRetriever
from app.retrieval.hybrid import rrf


def test_bm25_prefers_exact_terms():
    bm = BM25()
    bm.fit(["a", "b"], ["The NAC-12I costs Rs. 189,900", "Opening hours for the Galle branch"])
    assert bm.search("price of NAC-12I")[0][0] == "a"


def test_rrf_rewards_agreement():
    scores = rrf([["x", "y"], ["y", "z"]], [1.0, 1.0])
    assert max(scores, key=scores.get) == "y"


def test_norm_key_merges_company_suffixes():
    assert norm_key("Nilaveli Electronics (Pvt) Ltd") == norm_key("nilaveli electronics")


def _store(tmp_path):
    store = GraphStore(tmp_path / "g.json")
    store.add_extractions("doc1", [Extraction("c1", [Entity("Nila AirCool 12000", "Product", aliases=["NAC-12I"]), Entity("Gold Care", "WarrantyPlan")],
                                              [Relation("Nila AirCool 12000", "Gold Care", "HAS_WARRANTY", "AirCool 12000 has Gold Care")])])
    store.add_extractions("doc2", [Extraction("c2", [Entity("Gold Care", "WarrantyPlan"), Entity("10 years", "Other")],
                                              [Relation("Gold Care", "10 years", "COMPRESSOR_COVERAGE", "Gold Care covers the compressor for 10 years")])])
    return store


def test_graph_merges_entities_across_documents(tmp_path):
    store = _store(tmp_path)
    gold = store.g.nodes[norm_key("Gold Care")]
    assert gold["doc_ids"] == {"doc1", "doc2"}
    assert store.resolve("NAC-12I") == norm_key("Nila AirCool 12000")


def test_graph_retrieval_finds_two_hop_evidence(tmp_path):
    store = _store(tmp_path)
    retriever = GraphRetriever(store, HashEmbedder(), hops=2)
    res = retriever.retrieve("What compressor warranty does the NAC-12I have?", None)
    chunk_ids = [c for c, _ in res.chunk_scores]
    assert "c1" in chunk_ids and "c2" in chunk_ids  # c2 never mentions the product
    assert any("10 years" in f.as_text() for f in res.facts)


def test_removing_a_document_cleans_the_graph(tmp_path):
    store = _store(tmp_path)
    store.remove_chunks({"c2"})
    store.remove_document("doc2")
    assert norm_key("10 years") not in store.g
    assert norm_key("Gold Care") in store.g  # still referenced by doc1
    reloaded = GraphStore(tmp_path / "g.json")
    assert reloaded.g.number_of_nodes() == store.g.number_of_nodes()


def test_heuristic_extractor_links_values_to_names():
    ex = HeuristicExtractor().extract([{"id": "c", "text": "The Galle Branch is open Sunday 10.00 AM - 2.00 PM.", "section": None}], "Profile", [])[0]
    names = {e.name for e in ex.entities}
    assert "Galle Branch" in names and "10.00 AM - 2.00 PM" in names
    assert any({r.source, r.target} == {"Galle Branch", "10.00 AM - 2.00 PM"} for r in ex.relations)

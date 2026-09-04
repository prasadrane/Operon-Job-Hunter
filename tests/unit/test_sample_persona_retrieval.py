import importlib
from src.core.config import get_settings


def test_sample_retrieval_returns_career_evidence():
    get_settings.cache_clear()
    mod = importlib.import_module("src.pipeline.3_tailoring.hybrid_graph_retriever")
    r = mod.HybridGraphRetriever()
    results = r.retrieve("Kafka backpressure incident", top_k=3)
    assert results, "sample career graph returned nothing for a known story"

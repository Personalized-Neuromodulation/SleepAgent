from paper_rag.chunking import HierarchicalChunker, approximate_token_count
from paper_rag.domain import ParsedDocument, ParsedSection


def test_hierarchical_chunks_have_valid_parents():
    text = " ".join(f"Sentence {index} contains scientific evidence." for index in range(120))
    document = ParsedDocument(
        title="Study",
        abstract="",
        sections=[ParsedSection("Results", "results", 0, text)],
    )
    chunks = HierarchicalChunker(parent_tokens=180, child_tokens=70, child_overlap=15).chunk(document)
    parents = {chunk.chunk_id for chunk in chunks if chunk.level == "parent"}
    children = [chunk for chunk in chunks if chunk.level == "child"]
    assert parents
    assert children
    assert all(chunk.parent_chunk_id in parents for chunk in children)
    assert all(chunk.token_count == approximate_token_count(chunk.text) for chunk in chunks)

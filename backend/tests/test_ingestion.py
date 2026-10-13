from collections.abc import Sequence

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.chunking import parse_document
from app.ai.ingestion import DEFAULT_KNOWLEDGE_DIR, embed_missing_chunks, index_knowledge
from app.domain.models import KnowledgeChunk, KnowledgeDocument
from app.integrations.embeddings import LocalDeterministicEmbeddingProvider


class RecordingEmbeddingProvider:
    dimension = 1024

    def __init__(self) -> None:
        self.document_calls: list[list[str]] = []

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.document_calls.append(list(texts))
        return [[0.0] * self.dimension for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.0] * self.dimension


@pytest.fixture
def embedder() -> LocalDeterministicEmbeddingProvider:
    return LocalDeterministicEmbeddingProvider(1024)


def _chunk_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(KnowledgeChunk))


def test_chunking_retains_metadata_with_stable_versioned_ids():
    text = (DEFAULT_KNOWLEDGE_DIR / "ONU-offline.md").read_text(encoding="utf-8")
    document = parse_document(text)

    assert document.document_key == "kb-onu-offline-v1"
    assert document.title == "ONU Offline Field Checks"
    assert document.version == "1.0"
    assert document.source_type == "curated_procedure"

    assert [chunk.section for chunk in document.chunks] == [
        "Confirm service impact",
        "Inspect optical path",
        "Verify ONU power and indicators",
        "Check the upstream access node",
        "Record findings and escalate",
    ]
    first = document.chunks[0]
    assert first.chunk_id == "kb-onu-offline-v1:1.0:confirm-service-impact"
    assert first.document_key == document.document_key
    assert first.title == document.title
    assert first.version == document.version
    assert "Compare the service status" in first.content


def test_ingestion_is_repeatable_and_idempotent(db_session, embedder):
    first = index_knowledge(db_session, embedder)
    db_session.commit()

    assert first.documents == 8
    assert first.chunks == 42
    assert first.embeddings_generated == 42
    assert first.embeddings_reused == 0

    embeddings_first = {
        chunk.id: list(chunk.embedding)
        for chunk in db_session.scalars(select(KnowledgeChunk)).all()
    }
    assert len(embeddings_first) == 42
    assert all(len(vector) == 1024 for vector in embeddings_first.values())

    second = index_knowledge(db_session, embedder)
    db_session.commit()

    assert second.documents == 8
    assert second.chunks == 42
    assert second.embeddings_generated == 0
    assert second.embeddings_reused == 42
    assert _chunk_count(db_session) == 42

    embeddings_second = {
        chunk.id: list(chunk.embedding)
        for chunk in db_session.scalars(select(KnowledgeChunk)).all()
    }
    assert embeddings_second == embeddings_first


def test_embed_missing_chunks_fills_seeded_rows(db_session, embedder):
    document = KnowledgeDocument(
        id="kb-demo-v1",
        document_key="kb-demo-v1",
        title="Demo Procedure",
        source_type="curated_procedure",
        version="1.0",
    )
    chunk = KnowledgeChunk(
        id="kb-demo-v1:1.0:intro",
        document_id="kb-demo-v1",
        section="Intro",
        content="Check the optical loss before dispatch.",
    )
    db_session.add_all([document, chunk])
    db_session.commit()
    assert chunk.embedding is None

    generated, reused = embed_missing_chunks(db_session, embedder)
    db_session.commit()

    assert (generated, reused) == (1, 0)
    refreshed = db_session.get(KnowledgeChunk, "kb-demo-v1:1.0:intro")
    assert refreshed.embedding is not None
    assert len(refreshed.embedding) == 1024


def test_reembed_discards_stored_vectors_and_regenerates(db_session, embedder):
    class ConstantEmbeddingProvider:
        dimension = 1024

        def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
            return [[1.0] * self.dimension for _ in texts]

        def embed_query(self, text: str) -> list[float]:
            return [1.0] * self.dimension

    index_knowledge(db_session, embedder)
    db_session.commit()
    assert all(
        list(chunk.embedding) != [1.0] * 1024
        for chunk in db_session.scalars(select(KnowledgeChunk)).all()
    )

    generated, reused = embed_missing_chunks(
        db_session, ConstantEmbeddingProvider(), reembed=True
    )
    db_session.commit()

    assert (generated, reused) == (42, 0)
    assert all(
        list(chunk.embedding) == [1.0] * 1024
        for chunk in db_session.scalars(select(KnowledgeChunk)).all()
    )


def test_ingestion_uses_the_injected_embedding_provider(db_session):
    provider = RecordingEmbeddingProvider()

    index_knowledge(db_session, provider)
    db_session.commit()

    assert provider.document_calls
    embedded_texts = [text for call in provider.document_calls for text in call]
    assert len(embedded_texts) == 42
    assert all(text.strip() for text in embedded_texts)


def test_ingestion_rejects_divergent_seeded_rows(db_session, embedder):
    document = KnowledgeDocument(
        id="kb-onu-offline-v1",
        document_key="kb-onu-offline-v1",
        title="Diverged Title",
        source_type="curated_procedure",
        version="1.0",
    )
    db_session.add(document)
    db_session.commit()

    with pytest.raises(RuntimeError, match="noncanonical fields title"):
        index_knowledge(db_session, embedder)

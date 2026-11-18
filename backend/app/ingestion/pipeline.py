"""Ingestion pipeline: parse -> chunk -> embed -> extract graph -> index."""

import logging
import time

from .chunker import chunk_sections
from .parsers import Section

log = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(self, db, embedder, vectors, graph_store, extractor, settings, on_change=None):
        self.db = db
        self.embedder = embedder
        self.vectors = vectors
        self.graph = graph_store
        self.extractor = extractor
        self.settings = settings
        self.on_change = on_change or (lambda: None)

    def ingest_sections(self, doc_id: str, title: str, sections: list[Section]) -> dict:
        t0 = time.perf_counter()
        try:
            chunks = chunk_sections(sections, self.settings.chunk_size, self.settings.chunk_overlap)
            if not chunks:
                raise ValueError("No readable text found in this document")
            rows = [
                {"id": f"{doc_id}-{i:04d}", "doc_id": doc_id, "idx": i, "text": c.text, "section": c.section, "page": c.page}
                for i, c in enumerate(chunks)
            ]
            self.db.insert_chunks(rows)
            vecs = self.embedder.embed_documents([r["text"] for r in rows])
            self.vectors.add([r["id"] for r in rows], vecs)

            known = [d["name"] for _, d in sorted(self.graph.g.nodes(data=True), key=lambda x: -self.graph.g.degree(x[0]))]
            extractions = self.extractor.extract(rows, title, known)
            n_ents, n_rels = self.graph.add_extractions(doc_id, extractions)
            self.graph.save()

            self.db.update_document(doc_id, status="ready", n_chunks=len(rows), n_entities=n_ents, n_relations=n_rels, error=None)
            self.on_change()
            secs = round(time.perf_counter() - t0, 1)
            log.info("Ingested %s: %d chunks, %d entities, %d relations in %ss", title, len(rows), n_ents, n_rels, secs)
            return {"doc_id": doc_id, "chunks": len(rows), "entities": n_ents, "relations": n_rels, "seconds": secs}
        except Exception as e:  # keep the error visible in the dashboard
            log.exception("Ingestion failed for %s", title)
            self.remove(doc_id, keep_record=True)
            self.db.update_document(doc_id, status="failed", error=str(e)[:500])
            raise

    def remove(self, doc_id: str, keep_record: bool = False):
        chunk_ids = {c["id"] for c in self.db.doc_chunks(doc_id)}
        if chunk_ids:
            self.vectors.remove(chunk_ids)
            self.graph.remove_chunks(chunk_ids)
        self.graph.remove_document(doc_id)
        if keep_record:
            with self.db.tx() as c:
                c.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        else:
            self.db.delete_document(doc_id)
        self.on_change()

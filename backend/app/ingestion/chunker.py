"""Sentence-aware chunking with overlap.

Chunks never cut a sentence in half. Each chunk is prefixed with its section
heading, so a chunk like "Price: Rs. 89,990" still knows which product it is
about after it is separated from the rest of the document.
"""

import re
from dataclasses import dataclass

from .parsers import Section

# Split after . ! ? but not after abbreviations like "Rs." or "No." (Rs. 189,900).
_SENT_SPLIT = re.compile(r"(?<!\bRs\.)(?<!\bNo\.)(?<!\bMr\.)(?<!\bDr\.)(?<!\bSt\.)(?<=[.!?])\s+(?=[A-Z0-9\"'(])|\n+")


@dataclass
class Chunk:
    text: str
    section: str | None
    page: int | None


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text) if s and s.strip()]


def chunk_sections(sections: list[Section], size: int = 900, overlap: int = 150) -> list[Chunk]:
    chunks: list[Chunk] = []
    for sec in sections:
        prefix = f"{sec.heading}\n" if sec.heading else ""
        sentences = split_sentences(sec.text)
        buf: list[str] = []
        length = 0
        for sent in sentences:
            # Very long "sentences" (e.g. tables flattened to one line) are hard-split.
            while len(sent) > size:
                head, sent = sent[:size], sent[size - overlap:]
                chunks.append(Chunk(prefix + head, sec.heading, sec.page))
            if length + len(sent) > size and buf:
                chunks.append(Chunk(prefix + " ".join(buf), sec.heading, sec.page))
                # Keep trailing sentences as overlap for context continuity.
                keep, kept_len = [], 0
                for s in reversed(buf):
                    if kept_len + len(s) > overlap:
                        break
                    keep.insert(0, s)
                    kept_len += len(s)
                buf, length = keep, kept_len
            buf.append(sent)
            length += len(sent) + 1
        if buf:
            chunks.append(Chunk(prefix + " ".join(buf), sec.heading, sec.page))
    # Drop near-empty chunks (page numbers, stray headings).
    return [c for c in chunks if len(c.text.strip()) > 20]

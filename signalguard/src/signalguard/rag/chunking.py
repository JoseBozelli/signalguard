"""
Markdown documentation chunker for SignalGuard RAG.

Locked chunking convention: one chunk per `##` markdown section. chunk_id follows
"<filename>::<heading-slug>" -- this exact scheme is what
AnswerKeyEntry.expected_doc_chunk_ids values already assume, so any
change here must be re-verified against the answer key gold labels.

The document's `#` title and any preamble text before the first `##`
heading are dropped -- they're framing, not retrievable content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List


def slugify(heading: str) -> str:
    slug = heading.strip().lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    return slug


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    source_file: str
    heading: str
    text: str


def chunk_markdown_file(path: Path) -> List[Chunk]:
    """Split one markdown file into one chunk per level-2 (##) section."""
    content = path.read_text(encoding="utf-8")
    filename = path.name

    # Split on lines starting with "## " -- level-1 "#" is the document
    # title, not a chunk boundary, so it's excluded from the pattern.
    sections = re.split(r"(?m)^##\s+", content)
    chunks: List[Chunk] = []

    for section in sections[1:]:  # sections[0] is preamble before first ##
        lines = section.split("\n", 1)
        heading = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        chunk_id = f"{filename}::{slugify(heading)}"
        chunks.append(Chunk(chunk_id=chunk_id, source_file=filename, heading=heading, text=body))

    return chunks


def chunk_corpus(docs_dir: Path) -> List[Chunk]:
    """Chunk every .md file in docs_dir. Sorted glob for deterministic order."""
    all_chunks: List[Chunk] = []
    for path in sorted(docs_dir.glob("*.md")):
        all_chunks.extend(chunk_markdown_file(path))
    return all_chunks
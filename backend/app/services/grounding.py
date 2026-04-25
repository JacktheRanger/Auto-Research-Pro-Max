from __future__ import annotations

import hashlib
import math
import re
import uuid
from collections import Counter
from typing import Any

from openai import OpenAI

from ..db import (
    get_paper,
    list_paper_chunks,
    list_papers,
    list_project_paper_chunks,
    replace_paper_chunks,
    update_chunk_embeddings,
)

_WORD_RE = re.compile(r"[a-z0-9]+")


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _query_terms(query: str) -> list[str]:
    terms = [match.group(0) for match in _WORD_RE.finditer(query.lower()) if len(match.group(0)) > 1]
    seen: set[str] = set()
    ordered: list[str] = []
    for term in terms:
        if term not in seen:
            seen.add(term)
            ordered.append(term)
    return ordered


def _embedding_client(settings: dict[str, Any]) -> OpenAI | None:
    model = (settings.get("embedding_model") or "").strip()
    api_key = (settings.get("api_key") or "").strip()
    if not model or not api_key:
        return None
    base_url = (settings.get("base_url") or "https://api.openai.com/v1").strip()
    return OpenAI(api_key=api_key, base_url=base_url)


def _embed_texts(texts: list[str], settings: dict[str, Any]) -> list[list[float]]:
    client = _embedding_client(settings)
    model = (settings.get("embedding_model") or "").strip()
    if client is None or not texts:
        return []
    embeddings: list[list[float]] = []
    for start in range(0, len(texts), 32):
        batch = texts[start : start + 32]
        response = client.embeddings.create(model=model, input=batch)
        embeddings.extend([list(item.embedding) for item in response.data])
    return embeddings


def _chunk_text(text: str, *, target_words: int = 220, overlap_words: int = 40) -> list[dict[str, Any]]:
    words = text.split()
    if not words:
        return []
    chunks: list[dict[str, Any]] = []
    start = 0
    chunk_index = 0
    while start < len(words):
        end = min(len(words), start + target_words)
        content = " ".join(words[start:end]).strip()
        if content:
            chunks.append(
                {
                    "id": f"chunk_{uuid.uuid4().hex[:12]}",
                    "chunk_index": chunk_index,
                    "content": content,
                    "token_estimate": max(1, round(len(content) / 4)),
                    "metadata_json": {
                        "word_start": start,
                        "word_end": end,
                    },
                }
            )
            chunk_index += 1
        if end >= len(words):
            break
        start = max(0, end - overlap_words)
    return chunks


def build_index_text(paper: dict[str, Any]) -> str:
    parts = [
        _clean_text(paper.get("title")),
        _clean_text(paper.get("abstract")),
        _clean_text(paper.get("extracted_text")),
    ]
    return "\n\n".join(part for part in parts if part)


def _content_fingerprint(content: str, embedding_model: str) -> str:
    payload = f"{embedding_model or ''}::{content}".encode("utf-8", errors="ignore")
    return hashlib.sha1(payload).hexdigest()[:16]


def _existing_fingerprint(paper_id: str) -> str:
    chunks = list_paper_chunks(paper_id)
    if not chunks:
        return ""
    metadata = chunks[0].get("metadata_json") or {}
    return str(metadata.get("source_fingerprint") or "")


def index_paper(
    paper: dict[str, Any],
    settings: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, Any]:
    content = build_index_text(paper)
    embedding_model = (settings.get("embedding_model") or "").strip()
    new_fingerprint = _content_fingerprint(content, embedding_model)
    previous_fingerprint = _existing_fingerprint(paper["id"])
    skipped = False
    if not force and new_fingerprint and previous_fingerprint == new_fingerprint:
        skipped = True
    chunks = _chunk_text(content) if not skipped else []
    if not skipped and chunks:
        embeddings = _embed_texts([chunk["content"] for chunk in chunks], settings)
        if embeddings:
            for chunk, embedding in zip(chunks, embeddings):
                chunk["embedding_json"] = embedding
                chunk["metadata_json"]["embedding_model"] = embedding_model
                chunk["metadata_json"]["source_fingerprint"] = new_fingerprint
        else:
            for chunk in chunks:
                chunk["metadata_json"]["source_fingerprint"] = new_fingerprint
    if not skipped:
        replace_paper_chunks(paper["id"], paper["project_id"], chunks)
        embedding_ready = bool(chunks and chunks[0].get("embedding_json"))
        chunk_count = len(chunks)
    else:
        existing_chunks = list_paper_chunks(paper["id"])
        chunk_count = len(existing_chunks)
        embedding_ready = bool(existing_chunks and (existing_chunks[0].get("embedding_json") or []))
    return {
        "chunk_count": chunk_count,
        "embedding_ready": embedding_ready,
        "fingerprint": new_fingerprint,
        "skipped_unchanged": skipped,
    }


def reindex_project_papers(
    project_id: str,
    settings: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, Any]:
    papers = list_papers(project_id)
    indexed = 0
    skipped = 0
    embedding_ready = 0
    failures: list[dict[str, str]] = []
    for paper in papers:
        try:
            report = index_paper(paper, settings, force=force)
        except Exception as exc:  # noqa: BLE001 — propagate per-paper errors as data
            failures.append({"paper_id": paper["id"], "title": paper.get("title") or "", "error": str(exc)})
            continue
        if report.get("skipped_unchanged"):
            skipped += 1
        else:
            indexed += 1
        if report.get("embedding_ready"):
            embedding_ready += 1
    ensure_project_embeddings(project_id, settings)
    return {
        "project_id": project_id,
        "papers_total": len(papers),
        "papers_indexed": indexed,
        "papers_skipped": skipped,
        "embedding_ready": embedding_ready,
        "failures": failures,
        "force": force,
    }


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def _lexical_score(query_terms: list[str], text: str, title: str) -> tuple[float, list[str]]:
    lowered = f"{title} {text}".lower()
    counts = Counter(match.group(0) for match in _WORD_RE.finditer(lowered))
    matched = [term for term in query_terms if counts.get(term)]
    if not query_terms:
        return 0.0, matched
    coverage = len(matched) / len(query_terms)
    frequency = sum(counts.get(term, 0) for term in matched) / max(len(query_terms), 1)
    title_boost = 0.18 if any(term in title.lower() for term in matched) else 0.0
    return coverage * 0.7 + min(frequency / 6, 0.3) + title_boost, matched


def ensure_project_embeddings(project_id: str, settings: dict[str, Any]) -> None:
    if _embedding_client(settings) is None:
        return
    missing = [chunk for chunk in list_project_paper_chunks(project_id) if chunk.get("content") and not chunk.get("embedding_json")]
    if not missing:
        return
    embeddings = _embed_texts([chunk["content"] for chunk in missing], settings)
    if not embeddings:
        return
    updates: list[dict[str, Any]] = []
    for chunk, embedding in zip(missing, embeddings):
        metadata = dict(chunk.get("metadata_json") or {})
        metadata["embedding_model"] = settings.get("embedding_model") or ""
        updates.append({"id": chunk["id"], "embedding_json": embedding, "metadata_json": metadata})
    update_chunk_embeddings(updates)


def retrieve_grounded_snippets(
    project_id: str,
    query: str,
    settings: dict[str, Any],
    *,
    limit: int = 6,
) -> dict[str, Any]:
    cleaned_query = _clean_text(query)
    if not cleaned_query:
        return {"query": "", "strategy": "empty", "results": []}

    ensure_project_embeddings(project_id, settings)
    chunks = list_project_paper_chunks(project_id)
    if not chunks:
        return {"query": cleaned_query, "strategy": "empty", "results": []}

    query_embedding = _embed_texts([cleaned_query], settings)
    use_embeddings = bool(query_embedding and any(chunk.get("embedding_json") for chunk in chunks))
    query_terms = _query_terms(cleaned_query)
    scored: list[dict[str, Any]] = []

    for chunk in chunks:
        title = chunk.get("paper_title") or ""
        content = chunk.get("content") or ""
        if not content:
            continue
        if use_embeddings:
            score = _cosine_similarity(query_embedding[0], chunk.get("embedding_json") or [])
            matched_terms = query_terms
            strategy = "embedding"
        else:
            score, matched_terms = _lexical_score(query_terms, content, title)
            strategy = "lexical"
        if score <= 0:
            continue
        scored.append(
            {
                "paper_id": chunk["paper_id"],
                "paper_title": title,
                "citation_key": chunk.get("paper_citation_key") or "",
                "source_type": chunk.get("paper_source_type") or "",
                "source_provider": chunk.get("paper_source_provider") or "",
                "doi": chunk.get("paper_doi") or "",
                "venue": chunk.get("paper_venue") or "",
                "year": int(chunk.get("paper_year") or 0),
                "url": chunk.get("paper_url") or "",
                "preview_thumbnail_url": chunk.get("paper_preview_thumbnail_url") or "",
                "chunk_id": chunk["id"],
                "chunk_index": int(chunk.get("chunk_index") or 0),
                "text": content,
                "score": round(score, 4),
                "match_terms": matched_terms,
                "strategy": strategy,
            }
        )

    scored.sort(key=lambda item: (item["score"], item["year"], item["chunk_index"] * -1), reverse=True)
    filtered: list[dict[str, Any]] = []
    per_paper_counts: dict[str, int] = {}
    for item in scored:
        paper_id = item["paper_id"]
        if per_paper_counts.get(paper_id, 0) >= 2:
            continue
        per_paper_counts[paper_id] = per_paper_counts.get(paper_id, 0) + 1
        filtered.append(item)
        if len(filtered) >= limit:
            break
    return {
        "query": cleaned_query,
        "strategy": "embedding" if use_embeddings else "lexical",
        "results": filtered,
    }


def retrieve_paper_context_text(
    project_id: str,
    query: str,
    settings: dict[str, Any],
    *,
    limit: int = 5,
) -> str:
    payload = retrieve_grounded_snippets(project_id, query, settings, limit=limit)
    lines = [f"Grounded paper retrieval query: {payload.get('query')}", f"Strategy: {payload.get('strategy')}"]
    for item in payload.get("results") or []:
        lines.append(
            f"- {item['paper_title']} [{item.get('citation_key') or 'uncited'}] "
            f"({item.get('year') or 'n/a'}, {item.get('venue') or item.get('source_provider') or item.get('source_type')})"
        )
        lines.append(f"  Snippet: {item['text'][:420]}")
    if not payload.get("results"):
        lines.append("- No grounded snippets available.")
    return "\n".join(lines)


def get_paper_chunk_count(paper_id: str) -> int:
    return len(list_paper_chunks(paper_id))

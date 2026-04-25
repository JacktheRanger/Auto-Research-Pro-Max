"""Lightweight citation-graph extraction over the project's paper inventory.

Walks the extracted text of each paper, picks up DOI references and arXiv
identifiers, and links references back to other papers in the same project
when their canonical identifiers line up. The output shape mirrors what the
frontend can render directly without extra processing.
"""
from __future__ import annotations

import re
from typing import Any

DOI_RE = re.compile(r"\b10\.\d{4,9}/[\w._;()/:-]+\b", re.IGNORECASE)
ARXIV_RE = re.compile(r"arxiv[\s:.-]*((?:\d{4}\.\d{4,5})(?:v\d+)?)", re.IGNORECASE)


def _normalize_doi(value: str) -> str:
    return value.lower().rstrip(").,;]")


def _normalize_arxiv(value: str) -> str:
    return value.lower().split("v", 1)[0]


def _paper_keys(paper: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    doi = (paper.get("doi") or "").strip().lower()
    if doi:
        keys.add(f"doi:{_normalize_doi(doi)}")
    canonical = (paper.get("canonical_key") or "").strip().lower()
    if canonical:
        keys.add(canonical)
    external = (paper.get("external_id") or "").strip().lower()
    provider = (paper.get("source_provider") or "").strip().lower()
    if external:
        keys.add(f"external:{external}")
        if provider == "arxiv":
            keys.add(f"arxiv:{_normalize_arxiv(external)}")
    return keys


def _extract_references(text: str) -> list[dict[str, str]]:
    references: dict[str, dict[str, str]] = {}
    for match in DOI_RE.findall(text or ""):
        normalized = _normalize_doi(match)
        key = f"doi:{normalized}"
        references.setdefault(key, {"kind": "doi", "id": normalized, "label": normalized})
    for raw in ARXIV_RE.findall(text or ""):
        normalized = _normalize_arxiv(raw)
        key = f"arxiv:{normalized}"
        references.setdefault(key, {"kind": "arxiv", "id": normalized, "label": f"arXiv:{normalized}"})
    return list(references.values())


def build_citation_graph(papers: list[dict[str, Any]]) -> dict[str, Any]:
    paper_lookup: dict[str, str] = {}
    nodes: list[dict[str, Any]] = []
    paper_node_ids: set[str] = set()
    for paper in papers:
        node_id = f"paper:{paper['id']}"
        paper_node_ids.add(node_id)
        nodes.append(
            {
                "id": node_id,
                "kind": "paper",
                "label": paper.get("title") or "Paper",
                "doi": paper.get("doi") or "",
                "year": paper.get("year") or 0,
                "venue": paper.get("venue") or "",
                "citation_key": paper.get("citation_key") or "",
                "preview_thumbnail_url": paper.get("preview_thumbnail_url") or "",
            }
        )
        for key in _paper_keys(paper):
            paper_lookup[key] = node_id

    edges: list[dict[str, Any]] = []
    external_nodes: dict[str, dict[str, Any]] = {}
    edge_keys: set[tuple[str, str]] = set()
    unresolved_references: list[dict[str, Any]] = []

    for paper in papers:
        text = paper.get("extracted_text") or paper.get("abstract") or ""
        if not text:
            continue
        source_id = f"paper:{paper['id']}"
        for ref in _extract_references(text):
            key = f"{ref['kind']}:{ref['id']}"
            target_id = paper_lookup.get(key)
            if target_id is None:
                # Map arxiv references that point at a doi-keyed paper too.
                if ref["kind"] == "doi":
                    canonical = paper_lookup.get(f"doi:{ref['id']}")
                    if canonical:
                        target_id = canonical
            if target_id is None:
                target_id = f"external:{key}"
                if target_id not in external_nodes:
                    external_nodes[target_id] = {
                        "id": target_id,
                        "kind": ref["kind"],
                        "label": ref["label"],
                        "external_id": ref["id"],
                    }
                unresolved_references.append({"source_paper_id": paper["id"], "kind": ref["kind"], "id": ref["id"]})
            if target_id == source_id:
                continue
            edge_key = (source_id, target_id)
            if edge_key in edge_keys:
                continue
            edge_keys.add(edge_key)
            edges.append({"source": source_id, "target": target_id, "kind": ref["kind"]})

    nodes.extend(external_nodes.values())

    summary = {
        "papers": sum(1 for node in nodes if node["kind"] == "paper"),
        "external_references": len(external_nodes),
        "internal_links": sum(1 for edge in edges if edge["target"] in paper_node_ids),
        "unresolved_links": sum(1 for edge in edges if edge["target"] not in paper_node_ids),
    }
    return {
        "nodes": nodes,
        "edges": edges,
        "summary": summary,
        "unresolved_references": unresolved_references[:64],
    }

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote_plus

import httpx

DEFAULT_LIMIT = 4
USER_AGENT = "AutoResearchProMax/0.1 (local-first scholarly retrieval)"


def _client() -> httpx.Client:
    return httpx.Client(
        follow_redirects=True,
        timeout=20.0,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json, application/atom+xml;q=0.9"},
    )


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _author_names(items: list[dict[str, Any]] | None, *keys: str) -> list[str]:
    names: list[str] = []
    for item in items or []:
        for key in keys:
            value = item.get(key)
            if value:
                names.append(_clean_text(str(value)))
                break
    return names


def _canonical_key(title: str, doi: str) -> str:
    if doi:
        return f"doi:{doi.lower()}"
    return f"title:{re.sub(r'[^a-z0-9]+', '', title.lower())}"


def _normalize_result(
    *,
    provider: str,
    title: str,
    abstract: str = "",
    year: int = 0,
    venue: str = "",
    authors: list[str] | None = None,
    doi: str = "",
    url: str = "",
    pdf_url: str = "",
    external_id: str = "",
    citation_count: int = 0,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clean_title = _clean_text(title)
    return {
        "provider": provider,
        "title": clean_title,
        "abstract": _clean_text(abstract),
        "year": int(year or 0),
        "venue": _clean_text(venue),
        "authors": authors or [],
        "doi": doi.strip(),
        "url": url.strip(),
        "pdf_url": pdf_url.strip(),
        "external_id": external_id.strip(),
        "citation_count": int(citation_count or 0),
        "metadata": metadata or {},
        "canonical_key": _canonical_key(clean_title, doi.strip()),
    }


def search_openalex(query: str, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
    with _client() as client:
        response = client.get(
            "https://api.openalex.org/works",
            params={"search": query, "per-page": max(1, min(limit, 10))},
        )
        response.raise_for_status()
        payload = response.json()
    results: list[dict[str, Any]] = []
    for item in payload.get("results", []):
        authorships = item.get("authorships") or []
        authors = []
        for entry in authorships:
            author = entry.get("author") or {}
            if author.get("display_name"):
                authors.append(_clean_text(author["display_name"]))
        primary_location = item.get("primary_location") or {}
        source = primary_location.get("source") or {}
        results.append(
            _normalize_result(
                provider="openalex",
                title=item.get("display_name") or "",
                abstract="",
                year=item.get("publication_year") or 0,
                venue=source.get("display_name") or "",
                authors=authors,
                doi=(item.get("doi") or "").replace("https://doi.org/", ""),
                url=item.get("id") or primary_location.get("landing_page_url") or "",
                pdf_url=primary_location.get("pdf_url") or "",
                external_id=item.get("id") or "",
                citation_count=item.get("cited_by_count") or 0,
                metadata={
                    "type": item.get("type") or "",
                    "concepts": [concept.get("display_name") for concept in item.get("concepts") or []][:6],
                },
            )
        )
    return results


def search_semantic_scholar(query: str, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
    with _client() as client:
        response = client.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={
                "query": query,
                "limit": max(1, min(limit, 10)),
                "fields": ",".join(
                    [
                        "title",
                        "abstract",
                        "year",
                        "venue",
                        "authors",
                        "url",
                        "citationCount",
                        "externalIds",
                        "openAccessPdf",
                    ]
                ),
            },
        )
        response.raise_for_status()
        payload = response.json()
    results: list[dict[str, Any]] = []
    for item in payload.get("data", []):
        external_ids = item.get("externalIds") or {}
        open_pdf = item.get("openAccessPdf") or {}
        results.append(
            _normalize_result(
                provider="semantic_scholar",
                title=item.get("title") or "",
                abstract=item.get("abstract") or "",
                year=item.get("year") or 0,
                venue=item.get("venue") or "",
                authors=_author_names(item.get("authors"), "name"),
                doi=external_ids.get("DOI") or "",
                url=item.get("url") or "",
                pdf_url=open_pdf.get("url") or "",
                external_id=external_ids.get("CorpusId") or external_ids.get("ArXiv") or "",
                citation_count=item.get("citationCount") or 0,
                metadata={"external_ids": external_ids},
            )
        )
    return results


def search_crossref(query: str, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
    with _client() as client:
        response = client.get(
            "https://api.crossref.org/works",
            params={"query.bibliographic": query, "rows": max(1, min(limit, 10))},
        )
        response.raise_for_status()
        payload = response.json()
    results: list[dict[str, Any]] = []
    for item in payload.get("message", {}).get("items", []):
        titles = item.get("title") or [""]
        container = item.get("container-title") or [""]
        published = item.get("published-print") or item.get("published-online") or {}
        date_parts = published.get("date-parts") or [[0]]
        year = int((date_parts[0] or [0])[0] or 0)
        authors = []
        for author in item.get("author") or []:
            given = _clean_text(author.get("given"))
            family = _clean_text(author.get("family"))
            full = _clean_text(f"{given} {family}")
            if full:
                authors.append(full)
        results.append(
            _normalize_result(
                provider="crossref",
                title=titles[0] if titles else "",
                abstract=_clean_text(item.get("abstract") or ""),
                year=year,
                venue=container[0] if container else "",
                authors=authors,
                doi=item.get("DOI") or "",
                url=item.get("URL") or "",
                external_id=item.get("DOI") or "",
                citation_count=item.get("is-referenced-by-count") or 0,
                metadata={"type": item.get("type") or ""},
            )
        )
    return results


def search_arxiv(query: str, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
    encoded_query = quote_plus(query)
    with _client() as client:
        response = client.get(
            f"https://export.arxiv.org/api/query?search_query=all:{encoded_query}&start=0&max_results={max(1, min(limit, 10))}",
            headers={"Accept": "application/atom+xml"},
        )
        response.raise_for_status()
        payload = response.text

    root = ET.fromstring(payload)
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    results: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", ns):
        title = _clean_text(entry.findtext("atom:title", default="", namespaces=ns))
        abstract = _clean_text(entry.findtext("atom:summary", default="", namespaces=ns))
        published = entry.findtext("atom:published", default="", namespaces=ns)
        year = int(published[:4]) if published[:4].isdigit() else 0
        authors = [
            _clean_text(author.findtext("atom:name", default="", namespaces=ns))
            for author in entry.findall("atom:author", ns)
            if _clean_text(author.findtext("atom:name", default="", namespaces=ns))
        ]
        doi = _clean_text(entry.findtext("arxiv:doi", default="", namespaces=ns))
        pdf_url = ""
        url = _clean_text(entry.findtext("atom:id", default="", namespaces=ns))
        for link in entry.findall("atom:link", ns):
            if link.attrib.get("title") == "pdf":
                pdf_url = link.attrib.get("href", "")
                break
        results.append(
            _normalize_result(
                provider="arxiv",
                title=title,
                abstract=abstract,
                year=year,
                venue="arXiv",
                authors=authors,
                doi=doi,
                url=url,
                pdf_url=pdf_url,
                external_id=url.rsplit("/", 1)[-1],
                citation_count=0,
                metadata={"published": published},
            )
        )
    return results


def _dedupe_results(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for item in items:
        key = item["canonical_key"]
        existing = deduped.get(key)
        if existing is None or item["citation_count"] > existing["citation_count"]:
            deduped[key] = item
    return list(deduped.values())


def _rank_results(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            1 if item.get("doi") else 0,
            item.get("citation_count", 0),
            item.get("year", 0),
            len(item.get("authors", [])),
        ),
        reverse=True,
    )


def search_literature(query: str, limit_per_provider: int = DEFAULT_LIMIT) -> dict[str, Any]:
    provider_results: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}
    for provider, handler in (
        ("openalex", search_openalex),
        ("semantic_scholar", search_semantic_scholar),
        ("crossref", search_crossref),
        ("arxiv", search_arxiv),
    ):
        try:
            provider_results[provider] = handler(query, limit_per_provider)
        except Exception as exc:
            provider_results[provider] = []
            errors[provider] = str(exc)
    merged = _rank_results(
        _dedupe_results([item for items in provider_results.values() for item in items])
    )
    return {
        "query": query,
        "provider_results": provider_results,
        "results": merged,
        "errors": errors,
    }


def build_project_queries(project: dict[str, Any]) -> list[str]:
    candidates = [
        _clean_text(project.get("title")),
        _clean_text(f"{project.get('title', '')} {project.get('direction', '')}"),
        _clean_text(project.get("idea")),
    ]
    seen: set[str] = set()
    queries: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            queries.append(candidate)
    return queries[:3]


def search_literature_for_project(
    project: dict[str, Any],
    *,
    limit_per_provider: int = 3,
    max_queries: int = 2,
) -> dict[str, Any]:
    aggregated_results: list[dict[str, Any]] = []
    per_query: list[dict[str, Any]] = []
    for query in build_project_queries(project)[:max_queries]:
        result = search_literature(query, limit_per_provider=limit_per_provider)
        per_query.append(result)
        aggregated_results.extend(result["results"])
    ranked = _rank_results(_dedupe_results(aggregated_results))
    return {
        "queries": [item["query"] for item in per_query],
        "per_query": per_query,
        "recommended_reads": ranked[:10],
    }


def result_to_paper_payload(project_id: str, result: dict[str, Any], notes: str = "") -> dict[str, Any]:
    url = result.get("pdf_url") or result.get("url") or ""
    return {
        "project_id": project_id,
        "source_type": f"retrieved_{result.get('provider', 'unknown')}",
        "title": result.get("title") or url or "Retrieved paper",
        "url": url,
        "file_name": "",
        "stored_path": "",
        "notes": notes,
        "abstract": result.get("abstract") or "",
        "doi": result.get("doi") or "",
        "venue": result.get("venue") or "",
        "year": result.get("year") or 0,
        "authors_json": result.get("authors") or [],
        "source_provider": result.get("provider") or "",
        "external_id": result.get("external_id") or "",
        "extracted_text": result.get("abstract") or "",
        "metadata_json": {
            "citation_count": result.get("citation_count") or 0,
            "provider_metadata": result.get("metadata") or {},
            "canonical_key": result.get("canonical_key") or "",
        },
    }

from __future__ import annotations

import hashlib
import os
import re
import shutil
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

import httpx
from fastapi import UploadFile

from ..db import (
    UPLOAD_DIR,
    add_paper_source,
    find_duplicate_paper,
    get_paper,
    paper_exists_with_citation_key,
    update_paper_source,
)
from .grounding import index_paper

USER_AGENT = "AutoResearchProMax/0.2 (paper-intake metadata enrichment)"
MIN_TEXT_FOR_OCR_SKIP = 320  # below this we treat the PDF as scanned and try OCR
OCR_PAGE_LIMIT = 8
OCR_RENDER_DPI = 220


def _tesseract_available() -> str:
    override = (os.environ.get("TESSERACT_CMD") or "").strip()
    if override and Path(override).exists():
        return override
    found = shutil.which("tesseract")
    return found or ""
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", re.IGNORECASE)
ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/([^/?#]+)", re.IGNORECASE)
YEAR_RE = re.compile(r"(19|20)\d{2}")
META_TAG_RE = re.compile(r"<meta\b([^>]+)>", re.IGNORECASE)
ATTR_RE = re.compile(r'([a-zA-Z:_-]+)\s*=\s*(".*?"|\'.*?\'|[^\s>]+)')
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _safe_file_name(name: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("._")
    return clean or "paper.pdf"


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", unescape(value)).strip()


def _unique_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        cleaned = _clean_text(value)
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(cleaned)
    return ordered


def _normalize_doi(value: str | None) -> str:
    if not value:
        return ""
    lowered = value.strip()
    lowered = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", lowered, flags=re.IGNORECASE)
    match = DOI_RE.search(lowered)
    if not match:
        return ""
    return match.group(0).rstrip(").,;]").lower()


def _normalize_title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.lower())


def _author_family(author: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9 ]+", " ", author).strip()
    if not cleaned:
        return "source"
    parts = [part for part in cleaned.split() if part]
    return re.sub(r"[^a-z0-9]+", "", parts[-1].lower()) or "source"


def _title_token(title: str) -> str:
    stopwords = {"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"}
    for token in re.findall(r"[a-z0-9]+", title.lower()):
        if token not in stopwords:
            return token
    return "paper"


def _canonical_key(title: str, doi: str, external_id: str, year: int, authors: list[str]) -> str:
    if doi:
        return f"doi:{doi}"
    if external_id:
        return f"external:{external_id.lower()}"
    lead_author = _author_family(authors[0]) if authors else "unknown"
    year_key = str(year or 0)
    return f"title:{_normalize_title_key(title)}:{lead_author}:{year_key}"


def _base_citation_key(title: str, authors: list[str], year: int) -> str:
    author_key = _author_family(authors[0]) if authors else "source"
    year_key = str(year) if year else "nd"
    return f"{author_key}{year_key}{_title_token(title)}"


def _split_author_string(value: str | None) -> list[str]:
    if not value:
        return []
    chunks = re.split(r"\s*(?:,|;| and )\s*", value)
    return _unique_preserve(chunks)


def _extract_doi(value: str | None) -> str:
    return _normalize_doi(value or "")


def _extract_year(value: str | None) -> int:
    if not value:
        return 0
    match = YEAR_RE.search(value)
    return int(match.group(0)) if match else 0


def _strip_tags(value: str) -> str:
    return _clean_text(re.sub(r"<[^>]+>", " ", value))


def _hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def extract_pdf_text(path: Path) -> str:
    return extract_pdf_bundle(path).get("text", "")


def extract_pdf_bundle(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "text": "",
        "title": "",
        "authors": [],
        "doi": "",
        "year": 0,
        "page_count": 0,
        "metadata": {},
    }
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        payload["page_count"] = len(reader.pages)
        meta = reader.metadata or {}
        chunks: list[str] = []
        for page in reader.pages[:16]:
            chunks.append(page.extract_text() or "")
        text = "\n".join(chunks).strip()
        payload["text"] = text[:50000]
        payload["title"] = _clean_text(getattr(meta, "title", "") or meta.get("/Title") or "")
        payload["authors"] = _split_author_string(getattr(meta, "author", "") or meta.get("/Author") or "")
        payload["doi"] = _extract_doi(text) or _extract_doi(str(meta.get("/Subject") or ""))
        payload["year"] = _extract_year(str(meta.get("/CreationDate") or "")) or _extract_year(text[:3000])
        payload["metadata"] = {
            "producer": _clean_text(str(meta.get("/Producer") or "")),
            "creator": _clean_text(str(meta.get("/Creator") or "")),
        }
    except Exception as exc:
        payload["text"] = f"[extract_failed] {exc}"
    return payload


def ocr_pdf_text(path: Path, *, page_limit: int = OCR_PAGE_LIMIT) -> dict[str, Any]:
    """Render PDF pages with PyMuPDF, run OCR per page when tesseract is available.

    Returns ``{"status", "text", "engine", "pages", "languages", "missing"}``.
    The status is one of: ``ok``, ``empty``, ``no_tesseract``, ``no_pytesseract``,
    ``no_pymupdf``, or ``error``.
    """
    report: dict[str, Any] = {
        "status": "empty",
        "text": "",
        "engine": "",
        "pages": 0,
        "languages": "",
        "missing": [],
    }
    try:
        import fitz
    except Exception:
        report["status"] = "no_pymupdf"
        report["missing"].append("pymupdf")
        return report
    try:
        import pytesseract
    except Exception:
        report["status"] = "no_pytesseract"
        report["missing"].append("pytesseract")
        return report
    try:
        from PIL import Image  # noqa: F401
    except Exception:
        report["status"] = "no_pytesseract"
        report["missing"].append("Pillow")
        return report

    binary = _tesseract_available()
    if not binary:
        report["status"] = "no_tesseract"
        report["missing"].append("tesseract")
        return report

    pytesseract.pytesseract.tesseract_cmd = binary
    languages = (os.environ.get("OCR_LANGUAGES") or "eng").strip() or "eng"
    chunks: list[str] = []
    try:
        with fitz.open(path) as document:
            total = min(document.page_count, page_limit)
            for index in range(total):
                page = document.load_page(index)
                pixmap = page.get_pixmap(dpi=OCR_RENDER_DPI, alpha=False)
                image_bytes = pixmap.tobytes("png")
                from PIL import Image
                from io import BytesIO

                with Image.open(BytesIO(image_bytes)) as image:
                    text = pytesseract.image_to_string(image, lang=languages) or ""
                if text.strip():
                    chunks.append(text)
            report["pages"] = total
    except Exception as exc:
        report["status"] = "error"
        report["text"] = ""
        report["error"] = str(exc)
        return report

    text = "\n".join(chunks).strip()
    report["text"] = text[:80000]
    report["engine"] = "tesseract"
    report["languages"] = languages
    report["status"] = "ok" if text else "empty"
    return report


def render_pdf_preview(path: Path) -> dict[str, str]:
    try:
        import fitz

        preview_path = path.with_name(f"{path.stem}.preview.png")
        thumb_path = path.with_name(f"{path.stem}.thumb.png")
        with fitz.open(path) as document:
            if document.page_count < 1:
                return {"preview_image_path": "", "preview_thumbnail_path": ""}
            page = document.load_page(0)
            page.get_pixmap(matrix=fitz.Matrix(1.35, 1.35), alpha=False).save(preview_path)
            page.get_pixmap(matrix=fitz.Matrix(0.52, 0.52), alpha=False).save(thumb_path)
        return {
            "preview_image_path": str(preview_path),
            "preview_thumbnail_path": str(thumb_path),
        }
    except Exception:
        return {"preview_image_path": "", "preview_thumbnail_path": ""}


def _meta_map(html: str) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for match in META_TAG_RE.finditer(html):
        attributes: dict[str, str] = {}
        for attr_match in ATTR_RE.finditer(match.group(1)):
            key = attr_match.group(1).lower()
            raw_value = attr_match.group(2).strip()
            if raw_value[:1] in {'"', "'"} and raw_value[-1:] == raw_value[:1]:
                raw_value = raw_value[1:-1]
            attributes[key] = raw_value
        name = attributes.get("name") or attributes.get("property") or attributes.get("itemprop")
        content = attributes.get("content")
        if name and content:
            values.setdefault(name.lower(), []).append(_clean_text(content))
    return values


def _first_meta(meta_map: dict[str, list[str]], *keys: str) -> str:
    for key in keys:
        values = meta_map.get(key.lower())
        if values:
            return _clean_text(values[0])
    return ""


def _all_meta(meta_map: dict[str, list[str]], *keys: str) -> list[str]:
    values: list[str] = []
    for key in keys:
        values.extend(meta_map.get(key.lower(), []))
    return _unique_preserve(values)


def _extract_html_metadata(html: str, base_url: str) -> dict[str, Any]:
    meta_map = _meta_map(html)
    title_match = TITLE_RE.search(html)
    page_title = _clean_text(title_match.group(1) if title_match else "")
    title = _first_meta(meta_map, "citation_title", "og:title", "dc.title", "twitter:title") or page_title
    abstract = _first_meta(
        meta_map,
        "citation_abstract",
        "description",
        "og:description",
        "dc.description",
        "twitter:description",
    )
    venue = _first_meta(
        meta_map,
        "citation_journal_title",
        "citation_conference_title",
        "citation_book_title",
        "citation_publisher",
    )
    date_value = _first_meta(
        meta_map,
        "citation_publication_date",
        "citation_online_date",
        "article:published_time",
        "dc.date",
    )
    pdf_url = _first_meta(meta_map, "citation_pdf_url", "pdf_url")
    doi = _extract_doi(_first_meta(meta_map, "citation_doi", "dc.identifier")) or _extract_doi(html)
    return {
        "title": title,
        "abstract": abstract,
        "authors": _all_meta(meta_map, "citation_author", "dc.creator", "author"),
        "doi": doi,
        "venue": venue,
        "year": _extract_year(date_value),
        "pdf_url": urljoin(base_url, pdf_url) if pdf_url else "",
        "url": _first_meta(meta_map, "og:url", "citation_public_url") or base_url,
        "source_provider": "html_meta",
        "metadata": {
            "meta_keys": sorted(meta_map.keys())[:32],
        },
    }


async def _lookup_crossref_by_doi(client: httpx.AsyncClient, doi: str) -> dict[str, Any]:
    normalized = _normalize_doi(doi)
    if not normalized:
        return {}
    response = await client.get(f"https://api.crossref.org/works/{quote(normalized, safe='')}")
    response.raise_for_status()
    item = response.json().get("message", {})
    title = _clean_text((item.get("title") or [""])[0])
    venue = _clean_text((item.get("container-title") or [""])[0])
    abstract = _strip_tags(item.get("abstract") or "")
    authors = []
    for author in item.get("author") or []:
        full = _clean_text(f"{author.get('given', '')} {author.get('family', '')}")
        if full:
            authors.append(full)
    published = item.get("published-print") or item.get("published-online") or {}
    date_parts = published.get("date-parts") or [[0]]
    year = int((date_parts[0] or [0])[0] or 0)
    return {
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "doi": normalized,
        "venue": venue,
        "year": year,
        "url": _clean_text(item.get("URL") or ""),
        "external_id": normalized,
        "source_provider": "crossref",
        "metadata": {
            "crossref_type": item.get("type") or "",
            "publisher": _clean_text(item.get("publisher") or ""),
            "reference_count": item.get("reference-count") or 0,
            "citation_count": item.get("is-referenced-by-count") or 0,
        },
    }


def _extract_arxiv_id(url: str) -> str:
    match = ARXIV_RE.search(url)
    if not match:
        return ""
    arxiv_id = match.group(1)
    if arxiv_id.lower().endswith(".pdf"):
        arxiv_id = arxiv_id[:-4]
    return arxiv_id


async def _lookup_arxiv_metadata(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    arxiv_id = _extract_arxiv_id(url)
    if not arxiv_id:
        return {}
    response = await client.get(
        f"https://export.arxiv.org/api/query?id_list={quote(arxiv_id, safe='')}",
        headers={"Accept": "application/atom+xml"},
    )
    response.raise_for_status()
    root = ET.fromstring(response.text)
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    entry = root.find("atom:entry", ns)
    if entry is None:
        return {}
    title = _clean_text(entry.findtext("atom:title", default="", namespaces=ns))
    abstract = _clean_text(entry.findtext("atom:summary", default="", namespaces=ns))
    published = entry.findtext("atom:published", default="", namespaces=ns)
    authors = [
        _clean_text(author.findtext("atom:name", default="", namespaces=ns))
        for author in entry.findall("atom:author", ns)
        if _clean_text(author.findtext("atom:name", default="", namespaces=ns))
    ]
    pdf_url = ""
    for link in entry.findall("atom:link", ns):
        if link.attrib.get("title") == "pdf":
            pdf_url = link.attrib.get("href", "")
            break
    return {
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "doi": _normalize_doi(entry.findtext("arxiv:doi", default="", namespaces=ns)),
        "venue": "arXiv",
        "year": _extract_year(published),
        "url": _clean_text(entry.findtext("atom:id", default="", namespaces=ns)),
        "pdf_url": pdf_url,
        "external_id": arxiv_id,
        "source_provider": "arxiv",
        "metadata": {"published": published},
    }


def _is_pdf(content_type: str, url: str) -> bool:
    return "application/pdf" in content_type.lower() or url.lower().endswith(".pdf")


def _pick_better_string(existing: str, incoming: str, *, prefer_longer: bool = False) -> str:
    existing = _clean_text(existing)
    incoming = _clean_text(incoming)
    if not existing:
        return incoming
    if not incoming:
        return existing
    if prefer_longer and len(incoming) > len(existing):
        return incoming
    if existing.startswith("http") and incoming:
        return incoming
    if existing.lower().endswith(".pdf") and not incoming.lower().endswith(".pdf"):
        return incoming
    return existing


def _merge_notes(existing: str, incoming: str) -> str:
    parts = _unique_preserve([existing, incoming])
    return "\n".join(parts)


def _merge_metadata_layers(*layers: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "source_type": "remote_link",
        "title": "",
        "url": "",
        "file_name": "",
        "stored_path": "",
        "notes": "",
        "abstract": "",
        "doi": "",
        "venue": "",
        "year": 0,
        "authors_json": [],
        "source_provider": "",
        "external_id": "",
        "content_hash": "",
        "extracted_text": "",
        "preview_image_path": "",
        "preview_thumbnail_path": "",
        "metadata_json": {},
    }
    for layer in layers:
        if not layer:
            continue
        merged["source_type"] = layer.get("source_type") or merged["source_type"]
        merged["title"] = _pick_better_string(merged["title"], layer.get("title", ""))
        merged["url"] = _pick_better_string(merged["url"], layer.get("url", ""))
        merged["file_name"] = layer.get("file_name") or merged["file_name"]
        merged["stored_path"] = layer.get("stored_path") or merged["stored_path"]
        merged["notes"] = _merge_notes(merged["notes"], layer.get("notes", ""))
        merged["abstract"] = _pick_better_string(
            merged["abstract"], layer.get("abstract", ""), prefer_longer=True
        )
        merged["doi"] = _normalize_doi(layer.get("doi", "")) or merged["doi"]
        merged["venue"] = _pick_better_string(merged["venue"], layer.get("venue", ""))
        merged["year"] = int(layer.get("year") or merged["year"] or 0)
        merged["authors_json"] = _unique_preserve(
            list(merged["authors_json"]) + list(layer.get("authors_json") or layer.get("authors") or [])
        )
        merged["source_provider"] = layer.get("source_provider") or merged["source_provider"]
        merged["external_id"] = layer.get("external_id") or merged["external_id"]
        merged["content_hash"] = layer.get("content_hash") or merged["content_hash"]
        merged["extracted_text"] = _pick_better_string(
            merged["extracted_text"], layer.get("extracted_text", ""), prefer_longer=True
        )
        merged["preview_image_path"] = layer.get("preview_image_path") or merged["preview_image_path"]
        merged["preview_thumbnail_path"] = layer.get("preview_thumbnail_path") or merged["preview_thumbnail_path"]
        merged["metadata_json"].update(layer.get("metadata_json") or layer.get("metadata") or {})
    merged["canonical_key"] = _canonical_key(
        merged["title"],
        merged["doi"],
        merged["external_id"],
        int(merged["year"] or 0),
        list(merged["authors_json"]),
    )
    return merged


def _ensure_unique_citation_key(project_id: str, citation_key: str, exclude_paper_id: str = "") -> str:
    base_key = citation_key or "sourcendpaper"
    candidate = base_key
    suffix = 0
    while paper_exists_with_citation_key(project_id, candidate, exclude_paper_id):
        candidate = f"{base_key}{chr(ord('a') + suffix)}"
        suffix += 1
    return candidate


def _merge_existing_record(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = _merge_metadata_layers(existing, incoming)
    merged["project_id"] = existing["project_id"]
    merged["source_type"] = incoming.get("source_type") or existing.get("source_type") or "remote_link"
    merged["citation_key"] = existing.get("citation_key") or incoming.get("citation_key") or ""
    metadata = dict(existing.get("metadata_json") or {})
    metadata.update(incoming.get("metadata_json") or {})
    merge_sources = list(metadata.get("merged_sources") or [])
    merge_sources.append(
        {
            "source_type": incoming.get("source_type") or "",
            "url": incoming.get("url") or "",
            "doi": incoming.get("doi") or "",
        }
    )
    metadata["merged_sources"] = merge_sources[-8:]
    merged["metadata_json"] = metadata
    return merged


def _save_pdf_bytes(project_id: str, file_name: str, content: bytes) -> dict[str, Any]:
    project_dir = UPLOAD_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    normalized_name = _safe_file_name(file_name or "paper.pdf")
    if not normalized_name.lower().endswith(".pdf"):
        normalized_name = f"{normalized_name}.pdf"
    target = project_dir / normalized_name
    target.write_bytes(content)
    pdf_bundle = extract_pdf_bundle(target)
    previews = render_pdf_preview(target)
    extracted = pdf_bundle.get("text") or ""
    metadata: dict[str, Any] = {
        "page_count": pdf_bundle.get("page_count", 0),
        "pdf_metadata": pdf_bundle.get("metadata", {}),
    }
    if (
        len(extracted.strip()) < MIN_TEXT_FOR_OCR_SKIP
        or extracted.startswith("[extract_failed]")
    ):
        ocr_report = ocr_pdf_text(target)
        metadata["ocr"] = {
            "status": ocr_report.get("status"),
            "engine": ocr_report.get("engine") or "",
            "pages_processed": ocr_report.get("pages") or 0,
            "languages": ocr_report.get("languages") or "",
            "missing_dependencies": ocr_report.get("missing") or [],
            "triggered_reason": "low_text" if not extracted.startswith("[extract_failed]") else "extract_failed",
        }
        ocr_text = ocr_report.get("text") or ""
        if ocr_text:
            extracted = ocr_text if not extracted.strip() else f"{extracted}\n\n[OCR Recovery]\n{ocr_text}"
            metadata["ocr"]["recovered_chars"] = len(ocr_text)
    return {
        "file_name": normalized_name,
        "stored_path": str(target),
        "content_hash": _hash_bytes(content),
        "preview_image_path": previews.get("preview_image_path", ""),
        "preview_thumbnail_path": previews.get("preview_thumbnail_path", ""),
        "extracted_text": extracted,
        "title": pdf_bundle.get("title", ""),
        "authors_json": pdf_bundle.get("authors", []),
        "doi": pdf_bundle.get("doi", ""),
        "year": pdf_bundle.get("year", 0),
        "metadata_json": metadata,
    }


def _stored_name_from_title_or_url(title: str, url: str) -> str:
    if title:
        return title
    trimmed = url.rstrip("/").rsplit("/", 1)[-1] or "remote-paper"
    return trimmed if "." in trimmed else f"{trimmed}.pdf"


def _choose_primary_url(original_url: str, layer_url: str) -> str:
    return layer_url or original_url


def _finalize_payload(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["project_id"] = project_id
    normalized["title"] = normalized.get("title") or normalized.get("url") or normalized.get("file_name") or "Paper"
    normalized["doi"] = _normalize_doi(normalized.get("doi"))
    normalized["authors_json"] = _unique_preserve(list(normalized.get("authors_json") or []))
    normalized["canonical_key"] = _canonical_key(
        normalized["title"],
        normalized["doi"],
        normalized.get("external_id", ""),
        int(normalized.get("year") or 0),
        normalized["authors_json"],
    )
    normalized["citation_key"] = _base_citation_key(
        normalized["title"], normalized["authors_json"], int(normalized.get("year") or 0)
    )
    return normalized


def _persist_paper_record(project_id: str, payload: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    normalized = _finalize_payload(project_id, payload)
    duplicate = find_duplicate_paper(
        project_id,
        doi=normalized.get("doi", ""),
        canonical_key=normalized.get("canonical_key", ""),
        external_id=normalized.get("external_id", ""),
        source_provider=normalized.get("source_provider", ""),
        content_hash=normalized.get("content_hash", ""),
    )
    if duplicate is None:
        normalized["citation_key"] = _ensure_unique_citation_key(project_id, normalized["citation_key"])
        paper = add_paper_source(normalized)
    else:
        merged = _merge_existing_record(duplicate, normalized)
        merged["citation_key"] = _ensure_unique_citation_key(
            project_id,
            duplicate.get("citation_key") or merged.get("citation_key") or "sourcendpaper",
            duplicate["id"],
        )
        paper = update_paper_source(duplicate["id"], merged)
    if paper is None:
        raise RuntimeError("Failed to persist paper record")
    index_paper(paper, settings)
    refreshed = get_paper(paper["id"])
    if refreshed is None:
        raise RuntimeError("Failed to reload persisted paper record")
    return refreshed


async def save_uploaded_paper(
    project_id: str,
    file: UploadFile,
    notes: str = "",
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    content = await file.read()
    pdf_data = _save_pdf_bytes(project_id, file.filename or "paper.pdf", content)
    payload = _merge_metadata_layers(
        {
            "source_type": "local_pdf",
            "title": _clean_text(file.filename or ""),
            "file_name": pdf_data.get("file_name", ""),
            "stored_path": pdf_data.get("stored_path", ""),
            "notes": notes,
        },
        pdf_data,
    )
    return _persist_paper_record(project_id, payload, settings or {})


async def save_remote_paper(
    project_id: str,
    url: str,
    title: str,
    notes: str = "",
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_url = _clean_text(url)
    if not resolved_url:
        raise ValueError("Remote URL is required")

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=40.0,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.8"},
    ) as client:
        response = await client.get(resolved_url)
        response.raise_for_status()
        final_url = str(response.url)
        content_type = response.headers.get("content-type", "")
        pdf_data: dict[str, Any] = {}
        html_meta: dict[str, Any] = {}

        if _is_pdf(content_type, final_url):
            pdf_data = _save_pdf_bytes(
                project_id,
                _stored_name_from_title_or_url(title, final_url),
                response.content,
            )
        else:
            html_meta = _extract_html_metadata(response.text, final_url)
            candidate_pdf_url = html_meta.get("pdf_url") or ""
            if candidate_pdf_url:
                try:
                    pdf_response = await client.get(candidate_pdf_url)
                    pdf_response.raise_for_status()
                    if _is_pdf(pdf_response.headers.get("content-type", ""), candidate_pdf_url):
                        pdf_data = _save_pdf_bytes(
                            project_id,
                            _stored_name_from_title_or_url(title or html_meta.get("title", ""), candidate_pdf_url),
                            pdf_response.content,
                        )
                except Exception:
                    pass

        doi_hint = _normalize_doi(
            pdf_data.get("doi") or html_meta.get("doi") or _extract_doi(final_url) or _extract_doi(title)
        )
        try:
            arxiv_meta = await _lookup_arxiv_metadata(client, final_url)
        except Exception:
            arxiv_meta = {}
        try:
            crossref_meta = await _lookup_crossref_by_doi(client, doi_hint) if doi_hint else {}
        except Exception:
            crossref_meta = {}

    payload = _merge_metadata_layers(
        {
            "source_type": "remote_pdf" if pdf_data.get("stored_path") else "remote_link",
            "title": title,
            "url": _choose_primary_url(resolved_url, html_meta.get("url", "") or crossref_meta.get("url", "")),
            "notes": notes,
            "metadata_json": {"requested_url": resolved_url, "resolved_url": final_url, "content_type": content_type},
        },
        html_meta,
        arxiv_meta,
        crossref_meta,
        pdf_data,
    )
    if html_meta.get("pdf_url") or arxiv_meta.get("pdf_url"):
        payload["metadata_json"]["pdf_url"] = html_meta.get("pdf_url") or arxiv_meta.get("pdf_url")
    return _persist_paper_record(project_id, payload, settings or {})


_EDITABLE_PAPER_FIELDS: tuple[str, ...] = (
    "title",
    "url",
    "notes",
    "abstract",
    "doi",
    "venue",
    "year",
    "authors_json",
    "citation_key",
    "source_provider",
    "external_id",
)


def _split_authors_for_edit(value: str) -> list[str]:
    chunks = re.split(r"\s*(?:;|\n|\r| and )\s*", value or "")
    return _unique_preserve(chunks)


def update_paper_metadata(
    project_id: str,
    paper_id: str,
    payload: dict[str, Any],
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    existing = get_paper(paper_id)
    if existing is None or existing.get("project_id") != project_id:
        raise LookupError("Paper not found in project")

    updated = dict(existing)
    metadata = dict(existing.get("metadata_json") or {})
    edit_history = list(metadata.get("manual_edits") or [])

    changed_fields: list[str] = []
    for field in _EDITABLE_PAPER_FIELDS:
        if field not in payload:
            continue
        new_value: Any = payload[field]
        if field == "year":
            try:
                new_value = int(new_value or 0)
            except (TypeError, ValueError):
                new_value = 0
        elif field == "authors_json":
            if isinstance(new_value, str):
                new_value = _split_authors_for_edit(new_value)
            else:
                new_value = _unique_preserve(list(new_value or []))
        elif field == "doi":
            new_value = _normalize_doi(new_value or "")
        elif isinstance(new_value, str):
            new_value = _clean_text(new_value)
        if new_value != existing.get(field):
            changed_fields.append(field)
            updated[field] = new_value

    if not changed_fields:
        return existing

    updated["title"] = updated.get("title") or existing.get("title") or "Paper"
    updated["doi"] = _normalize_doi(updated.get("doi"))
    updated["authors_json"] = _unique_preserve(list(updated.get("authors_json") or []))
    updated["year"] = int(updated.get("year") or 0)
    updated["canonical_key"] = _canonical_key(
        updated["title"],
        updated.get("doi") or "",
        updated.get("external_id") or "",
        updated["year"],
        updated["authors_json"],
    )

    requested_citation = payload.get("citation_key") or updated.get("citation_key") or ""
    base_citation = (
        _clean_text(requested_citation)
        or _base_citation_key(updated["title"], updated["authors_json"], updated["year"])
    )
    updated["citation_key"] = _ensure_unique_citation_key(project_id, base_citation, paper_id)

    edit_history.append(
        {
            "fields": changed_fields,
            "actor": _clean_text(payload.get("actor") or ""),
        }
    )
    metadata["manual_edits"] = edit_history[-12:]
    metadata["last_edited_fields"] = changed_fields
    updated["metadata_json"] = metadata

    saved = update_paper_source(paper_id, updated)
    if saved is None:
        raise RuntimeError("Failed to update paper metadata")
    if "abstract" in changed_fields and not updated.get("extracted_text"):
        updated["extracted_text"] = updated.get("abstract") or ""
    index_paper(saved, settings or {})
    refreshed = get_paper(paper_id)
    return refreshed or saved


def reocr_paper(
    project_id: str,
    paper_id: str,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    existing = get_paper(paper_id)
    if existing is None or existing.get("project_id") != project_id:
        raise LookupError("Paper not found in project")
    stored_path = existing.get("stored_path") or ""
    if not stored_path or not Path(stored_path).exists():
        raise LookupError("Paper does not have a local PDF available for OCR.")
    report = ocr_pdf_text(Path(stored_path))
    metadata = dict(existing.get("metadata_json") or {})
    metadata["ocr"] = {
        "status": report.get("status"),
        "engine": report.get("engine") or "",
        "pages_processed": report.get("pages") or 0,
        "languages": report.get("languages") or "",
        "missing_dependencies": report.get("missing") or [],
        "triggered_reason": "manual",
    }
    text = report.get("text") or ""
    updated = dict(existing)
    updated["metadata_json"] = metadata
    if text:
        metadata["ocr"]["recovered_chars"] = len(text)
        existing_text = (existing.get("extracted_text") or "").strip()
        updated["extracted_text"] = (
            text if not existing_text else f"{existing_text}\n\n[OCR Recovery]\n{text}"
        )
    saved = update_paper_source(paper_id, updated)
    if saved is None:
        raise RuntimeError("Failed to persist OCR result")
    if text:
        index_paper(saved, settings or {})
    return get_paper(paper_id) or saved


async def refresh_paper_metadata(
    project_id: str,
    paper_id: str,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    existing = get_paper(paper_id)
    if existing is None or existing.get("project_id") != project_id:
        raise LookupError("Paper not found in project")

    arxiv_meta: dict[str, Any] = {}
    crossref_meta: dict[str, Any] = {}
    fetched_layers: list[dict[str, Any]] = []
    refresh_errors: dict[str, str] = {}

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=40.0,
        headers={"User-Agent": USER_AGENT, "Accept": "application/atom+xml,application/json,*/*;q=0.5"},
    ) as client:
        candidate_urls = [existing.get("url") or ""]
        if existing.get("metadata_json", {}).get("pdf_url"):
            candidate_urls.append(existing["metadata_json"]["pdf_url"])
        for url in [u for u in candidate_urls if u]:
            try:
                arxiv_meta = arxiv_meta or await _lookup_arxiv_metadata(client, url)
            except Exception as exc:
                refresh_errors["arxiv"] = str(exc)
        doi_hint = _normalize_doi(existing.get("doi") or "")
        if doi_hint:
            try:
                crossref_meta = await _lookup_crossref_by_doi(client, doi_hint)
            except Exception as exc:
                refresh_errors["crossref"] = str(exc)

    if arxiv_meta:
        fetched_layers.append(arxiv_meta)
    if crossref_meta:
        fetched_layers.append(crossref_meta)

    if not fetched_layers:
        existing_metadata = dict(existing.get("metadata_json") or {})
        existing_metadata["last_refresh_errors"] = refresh_errors
        existing_metadata["last_refresh_status"] = "no_provider_data"
        update_paper_source(paper_id, {**existing, "metadata_json": existing_metadata})
        return get_paper(paper_id) or existing

    merged = _merge_metadata_layers(existing, *fetched_layers)
    merged["project_id"] = existing["project_id"]
    merged["source_type"] = existing.get("source_type") or merged.get("source_type") or "remote_link"
    metadata = dict(existing.get("metadata_json") or {})
    metadata.update(merged.get("metadata_json") or {})
    refresh_log = list(metadata.get("provider_refreshes") or [])
    refresh_log.append(
        {
            "providers": [layer.get("source_provider") for layer in fetched_layers if layer.get("source_provider")],
            "errors": refresh_errors,
        }
    )
    metadata["provider_refreshes"] = refresh_log[-8:]
    metadata["last_refresh_status"] = "ok"
    metadata["last_refresh_errors"] = refresh_errors
    merged["metadata_json"] = metadata
    merged["citation_key"] = _ensure_unique_citation_key(
        project_id,
        existing.get("citation_key") or merged.get("citation_key") or "sourcendpaper",
        paper_id,
    )
    saved = update_paper_source(paper_id, merged)
    if saved is None:
        raise RuntimeError("Failed to refresh paper metadata")
    index_paper(saved, settings or {})
    return get_paper(paper_id) or saved


async def save_literature_result(
    project_id: str,
    result: dict[str, Any],
    notes: str = "",
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_payload = {
        "source_type": f"retrieved_{result.get('provider', 'unknown')}",
        "title": result.get("title") or "",
        "url": result.get("url") or "",
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
            "pdf_url": result.get("pdf_url") or "",
        },
    }
    pdf_url = _clean_text(result.get("pdf_url") or "")
    if pdf_url:
        try:
            return await save_remote_paper(
                project_id,
                pdf_url,
                result.get("title") or "",
                notes,
                settings=settings,
            )
        except Exception:
            pass
    if result.get("url"):
        base_payload["url"] = result.get("url") or ""
    return _persist_paper_record(project_id, base_payload, settings or {})

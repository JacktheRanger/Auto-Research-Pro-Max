from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx
from fastapi import UploadFile

from ..db import UPLOAD_DIR, add_paper_source


def _safe_file_name(name: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("._")
    return clean or "paper.pdf"


def extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        chunks: list[str] = []
        for page in reader.pages[:8]:
            chunks.append(page.extract_text() or "")
        text = "\n".join(chunks).strip()
        return text[:12000]
    except Exception as exc:
        return f"[extract_failed] {exc}"


async def save_uploaded_paper(project_id: str, file: UploadFile, notes: str = "") -> dict[str, Any]:
    project_dir = UPLOAD_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    file_name = _safe_file_name(file.filename or "paper.pdf")
    target = project_dir / file_name
    content = await file.read()
    target.write_bytes(content)
    extracted_text = extract_pdf_text(target)
    return add_paper_source(
        {
            "project_id": project_id,
            "source_type": "local_pdf",
            "title": file_name,
            "file_name": file_name,
            "stored_path": str(target),
            "notes": notes,
            "extracted_text": extracted_text,
        }
    )


async def save_remote_paper(
    project_id: str,
    url: str,
    title: str,
    notes: str = "",
) -> dict[str, Any]:
    extracted_text = ""
    stored_path = ""
    file_name = ""
    if url.lower().endswith(".pdf"):
        project_dir = UPLOAD_DIR / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        file_name = _safe_file_name(title or "remote-paper.pdf")
        if not file_name.lower().endswith(".pdf"):
            file_name = f"{file_name}.pdf"
        target = project_dir / file_name
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            target.write_bytes(response.content)
        stored_path = str(target)
        extracted_text = extract_pdf_text(target)

    return add_paper_source(
        {
            "project_id": project_id,
            "source_type": "remote_link" if not stored_path else "remote_pdf",
            "title": title or url,
            "url": url,
            "file_name": file_name,
            "stored_path": stored_path,
            "notes": notes,
            "extracted_text": extracted_text,
        }
    )


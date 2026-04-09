from __future__ import annotations

import json
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from ..db import EXPORT_DIR, media_url_for_path, utc_now


@dataclass(frozen=True)
class ManuscriptSection:
    title: str
    body: str


def _slug(value: str, fallback: str) -> str:
    candidate = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower())
    candidate = candidate.strip("-")
    return candidate or fallback


def _reset_stage_dir(project_id: str, run_id: str, stage_key: str) -> Path:
    stage_dir = EXPORT_DIR / project_id / run_id / stage_key
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)
    return stage_dir


def _write_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _json_write(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return path


def _file_entry(path: Path, label: str, kind: str, source_stage: str) -> dict[str, Any]:
    size_bytes = path.stat().st_size if path.exists() else 0
    return {
        "label": label,
        "kind": kind,
        "path": str(path),
        "url": media_url_for_path(str(path)),
        "size_bytes": size_bytes,
        "source_stage": source_stage,
    }


def _stage_lookup(prior_outputs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item.get("stage_key") or ""): item for item in prior_outputs if item.get("stage_key")}


def _stage_artifacts(stage_map: dict[str, dict[str, Any]], stage_key: str) -> dict[str, Any]:
    stage = stage_map.get(stage_key) or {}
    artifacts = stage.get("artifact_json")
    return artifacts if isinstance(artifacts, dict) else {}


def _listify(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dictify(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _compact(text: str, limit: int = 220) -> str:
    squashed = re.sub(r"\s+", " ", text or "").strip()
    if len(squashed) <= limit:
        return squashed
    return f"{squashed[: limit - 3].rstrip()}..."


def _paper_snippet(paper: dict[str, Any]) -> str:
    for key in ("notes", "abstract", "extracted_text"):
        value = _stringify(paper.get(key))
        if value:
            return _compact(value, limit=180)
    return "No evidence snippet was extracted for this source."


def _paper_citation_key(paper: dict[str, Any]) -> str:
    return _stringify(paper.get("citation_key")) or _slug(_stringify(paper.get("title")), "source")


def _paper_reference_line(paper: dict[str, Any]) -> str:
    authors = ", ".join(_listify(paper.get("authors_json"))[:6]) or "Unknown authors"
    year = paper.get("year") or "n.d."
    venue = _stringify(paper.get("venue")) or _stringify(paper.get("source_provider")) or _stringify(paper.get("source_type")) or "Unknown venue"
    doi = _stringify(paper.get("doi"))
    url = _stringify(paper.get("url"))
    segments = [f"{authors} ({year}). {_stringify(paper.get('title'))}. {venue}."]
    if doi:
        segments.append(f"DOI: {doi}.")
    if url:
        segments.append(f"URL: {url}.")
    return " ".join(segment for segment in segments if segment)


def _bibtex_escape(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
    return escaped.replace("\n", " ").strip()


def _latex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    value = text
    for source, target in replacements.items():
        value = value.replace(source, target)
    return value


def _bibtex_type(paper: dict[str, Any]) -> str:
    venue = _stringify(paper.get("venue")).lower()
    if "journal" in venue:
        return "article"
    if venue:
        return "inproceedings"
    return "misc"


def _bibtex_entry(paper: dict[str, Any]) -> str:
    citation_key = _paper_citation_key(paper)
    authors = " and ".join(_listify(paper.get("authors_json"))) or "Unknown Author"
    year = str(paper.get("year") or "")
    venue = _stringify(paper.get("venue"))
    doi = _stringify(paper.get("doi"))
    url = _stringify(paper.get("url"))
    field_lines = [
        f"  title = {{{_bibtex_escape(_stringify(paper.get('title')))}}}",
        f"  author = {{{_bibtex_escape(authors)}}}",
    ]
    if year:
        field_lines.append(f"  year = {{{year}}}")
    if venue:
        venue_key = "journal" if _bibtex_type(paper) == "article" else "booktitle"
        field_lines.append(f"  {venue_key} = {{{_bibtex_escape(venue)}}}")
    if doi:
        field_lines.append(f"  doi = {{{_bibtex_escape(doi)}}}")
    if url:
        field_lines.append(f"  url = {{{_bibtex_escape(url)}}}")
    return f"@{_bibtex_type(paper)}{{{citation_key},\n" + ",\n".join(field_lines) + "\n}"


def _top_papers(papers: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    return sorted(
        papers,
        key=lambda item: (
            0 if _stringify(item.get("notes")) else 1,
            -(int(item.get("year") or 0)),
            _stringify(item.get("title")).lower(),
        ),
    )[:limit]


def _section_body(lines: list[str]) -> str:
    return "\n\n".join(line.strip() for line in lines if line and line.strip())


def _make_claim(
    section: str,
    claim: str,
    support: list[dict[str, str]],
    status: str,
    rationale: str,
) -> dict[str, Any]:
    return {
        "section": section,
        "claim": claim,
        "status": status,
        "supporting_sources": support,
        "rationale": rationale,
    }


def _build_manuscript(
    project: dict[str, Any],
    papers: list[dict[str, Any]],
    prior_outputs: list[dict[str, Any]],
) -> dict[str, Any]:
    stage_map = _stage_lookup(prior_outputs)
    scope_artifacts = _stage_artifacts(stage_map, "scope_alignment")
    literature_map = _stage_artifacts(stage_map, "literature_map")
    synthesis = _stage_artifacts(stage_map, "synthesis")
    experiment_design = _stage_artifacts(stage_map, "experiment_design")
    sandbox = _stage_artifacts(stage_map, "experiment_sandbox")
    execution_review = _stage_artifacts(stage_map, "execution_review")
    revision = _stage_artifacts(stage_map, "paper_revision")

    problem_statement = _stringify(scope_artifacts.get("problem_statement")) or _stringify(project.get("idea"))
    review_ready_summary = _stringify(revision.get("review_ready_summary")) or "The current draft is exportable but still bounded by the available evidence."
    hypotheses = _listify(synthesis.get("hypotheses"))
    metrics = _listify(experiment_design.get("metrics"))
    ablations = _listify(experiment_design.get("ablations"))
    experiment_matrix = _listify(experiment_design.get("experiment_matrix"))
    sandbox_result = _dictify(sandbox.get("sandbox_result"))
    artifact_manifest = _listify(sandbox.get("artifact_manifest"))
    readiness = _dictify(execution_review.get("readiness_assessment"))
    open_questions = _listify(literature_map.get("open_questions"))
    open_issues = _listify(revision.get("open_issues"))

    cited_papers = _top_papers(papers)
    cited_keys = [_paper_citation_key(paper) for paper in cited_papers]

    introduction_claim = f"This manuscript is scoped around {problem_statement.rstrip('.')}."
    introduction_body = _section_body(
        [
            introduction_claim,
            (
                f"The project direction is {_stringify(project.get('direction'))}. "
                f"The primary delivery goal is {_stringify(project.get('goals'))}."
            ),
            (
                f"Boundary conditions remain explicit: {_stringify(project.get('constraints_text')) or 'no extra constraints were supplied'}, "
                f"with compute budget {_stringify(project.get('compute_budget')) or 'unspecified'} and API budget "
                f"{_stringify(project.get('api_budget')) or 'unspecified'}."
            ),
        ]
    )

    related_work_claim = (
        f"The current evidence base includes {len(papers)} attached sources that can be cited and verified."
        if papers
        else "The current evidence base has no attached papers, so literature-backed claims remain provisional."
    )
    related_work_lines = [related_work_claim]
    for paper in cited_papers:
        key = _paper_citation_key(paper)
        year = paper.get("year") or "n.d."
        venue = _stringify(paper.get("venue")) or _stringify(paper.get("source_provider")) or _stringify(paper.get("source_type")) or "unknown venue"
        related_work_lines.append(
            f"- {_stringify(paper.get('title'))} [@{key}] ({year}, {venue}) contributes: {_paper_snippet(paper)}"
        )
    if open_questions:
        related_work_lines.append(
            "Outstanding literature questions remain: "
            + "; ".join(_stringify(item) for item in open_questions[:4] if _stringify(item))
            + "."
        )
    related_work_body = _section_body(related_work_lines)

    primary_hypothesis = _dictify(hypotheses[0]) if hypotheses else {}
    hypothesis_text = _stringify(primary_hypothesis.get("statement")) or "The current plan is to turn the scoped research question into a testable baseline-plus-variant comparison."
    method_claim = f"The current research plan centers on the hypothesis that {hypothesis_text.rstrip('.')}."
    method_lines = [method_claim]
    if hypotheses:
        method_lines.extend(
            f"- {_stringify(_dictify(item).get('name')) or f'Hypothesis {index + 1}'}: "
            f"{_stringify(_dictify(item).get('statement')) or _stringify(_dictify(item).get('bet'))}"
            for index, item in enumerate(hypotheses[:3])
        )
    if experiment_matrix:
        method_lines.extend(
            f"- Experiment step: {_stringify(_dictify(item).get('step')) or _stringify(_dictify(item).get('name'))} -> "
            f"{_stringify(_dictify(item).get('goal')) or _stringify(_dictify(item).get('purpose'))}"
            for item in experiment_matrix[:4]
        )
    method_body = _section_body(method_lines)

    metric_count = len(metrics)
    ablation_count = len(ablations)
    evaluation_claim = (
        f"The evaluation plan currently defines {metric_count} named metrics and {ablation_count} ablation checks."
        if metric_count or ablation_count
        else "The evaluation plan is still under-specified and needs explicit metrics or ablations before strong claims should ship."
    )
    sandbox_status = _stringify(sandbox_result.get("status")) or "not_run"
    execution_claim = f"The latest sandbox-backed execution record is {sandbox_status} with {len(artifact_manifest)} captured artifacts."
    evaluation_lines = [evaluation_claim, execution_claim]
    if metrics:
        evaluation_lines.extend(
            f"- Metric: {_stringify(_dictify(item).get('name'))} -> "
            f"{_stringify(_dictify(item).get('target')) or _stringify(_dictify(item).get('definition')) or 'target not specified'}"
            for item in metrics[:4]
        )
    if ablations:
        evaluation_lines.extend(
            f"- Ablation: {_stringify(_dictify(item).get('name'))} -> {_stringify(_dictify(item).get('purpose')) or 'purpose not specified'}"
            for item in ablations[:4]
        )
    if readiness:
        readiness_status = _stringify(readiness.get("status")) or "unknown"
        evidence = _stringify(readiness.get("evidence"))
        evaluation_lines.append(f"Execution review status: {readiness_status}. {evidence}".strip())
    evaluation_body = _section_body(evaluation_lines)

    limitations_claim = "Unresolved evidence gaps and delivery risks remain explicit in the manuscript package."
    limitation_lines = [limitations_claim, review_ready_summary]
    limitation_lines.extend(
        f"- Open issue: {_stringify(_dictify(item).get('issue')) or _stringify(item)}"
        for item in open_issues[:5]
        if _stringify(_dictify(item).get("issue")) or _stringify(item)
    )
    limitation_body = _section_body(limitation_lines)

    next_action = _stringify(execution_review.get("next_action")) or "Use the peer-review findings to tighten evidence coverage and rerun the export if needed."
    conclusion_claim = "The delivery package is ready for downstream editing and venue-specific review, but not every research claim is experimentally closed."
    conclusion_body = _section_body(
        [
            conclusion_claim,
            f"Recommended next action: {next_action}",
        ]
    )

    sections = [
        ManuscriptSection("Abstract", _section_body([review_ready_summary, f"Project goal: {_stringify(project.get('goals'))}."])),
        ManuscriptSection("Introduction", introduction_body),
        ManuscriptSection("Related Work", related_work_body),
        ManuscriptSection("Method and Hypotheses", method_body),
        ManuscriptSection("Evaluation and Execution", evaluation_body),
        ManuscriptSection("Limitations", limitation_body),
        ManuscriptSection("Conclusion", conclusion_body),
    ]

    claims = [
        _make_claim(
            "Introduction",
            introduction_claim,
            [{"type": "stage", "label": "Scope Alignment", "ref": "scope_alignment"}],
            "supported" if problem_statement else "weak",
            "The export uses the scoped project statement rather than inventing a new problem framing.",
        ),
        _make_claim(
            "Related Work",
            related_work_claim,
            [
                {"type": "paper", "label": _stringify(paper.get("title")), "ref": _paper_citation_key(paper)}
                for paper in cited_papers
            ],
            "supported" if papers else "unsupported",
            "Attached paper metadata and citation keys determine whether the evidence base is actually citable.",
        ),
        _make_claim(
            "Method and Hypotheses",
            method_claim,
            [{"type": "stage", "label": "Synthesis", "ref": "synthesis"}],
            "supported" if primary_hypothesis or hypotheses else "weak",
            "The manuscript hypothesis is derived from the synthesis stage artifacts.",
        ),
        _make_claim(
            "Evaluation and Execution",
            evaluation_claim,
            [{"type": "stage", "label": "Experiment Design", "ref": "experiment_design"}],
            "supported" if metric_count or ablation_count else "weak",
            "Metric and ablation counts come directly from the experiment design artifacts.",
        ),
        _make_claim(
            "Evaluation and Execution",
            execution_claim,
            [{"type": "stage", "label": "Experiment Sandbox", "ref": "experiment_sandbox"}],
            "supported" if sandbox_result else "weak",
            "Execution status and artifact count are tied to the sandbox record.",
        ),
        _make_claim(
            "Limitations",
            limitations_claim,
            [{"type": "stage", "label": "Paper Revision", "ref": "paper_revision"}],
            "supported" if open_issues or review_ready_summary else "weak",
            "The export preserves revision-stage unresolved issues instead of hiding them.",
        ),
        _make_claim(
            "Conclusion",
            conclusion_claim,
            [
                {"type": "stage", "label": "Paper Revision", "ref": "paper_revision"},
                {"type": "stage", "label": "Experiment Sandbox", "ref": "experiment_sandbox"},
            ],
            "weak" if sandbox_status not in {"completed", "succeeded", "success"} else "supported",
            "The conclusion is intentionally conservative when the execution record is incomplete or provisional.",
        ),
    ]

    return {
        "title": _stringify(project.get("title")) or "Untitled Research Package",
        "project_id": project.get("id"),
        "generated_at": utc_now(),
        "sections": sections,
        "claims": claims,
        "cited_keys": cited_keys,
        "references": [_paper_reference_line(paper) for paper in papers],
    }


def _markdown_document(manuscript: dict[str, Any], papers: list[dict[str, Any]]) -> str:
    lines = [
        f"# {manuscript['title']}",
        "",
        f"_Generated: {manuscript['generated_at']}_",
        "",
    ]
    for section in manuscript["sections"]:
        lines.append(f"## {section.title}")
        lines.append("")
        lines.append(section.body)
        lines.append("")
    lines.extend(["## References", ""])
    if papers:
        for paper in papers:
            lines.append(f"- `{_paper_citation_key(paper)}` {_paper_reference_line(paper)}")
    else:
        lines.append("- No attached papers were available when the package was exported.")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def _latex_document(manuscript: dict[str, Any], papers: list[dict[str, Any]]) -> str:
    lines = [
        r"\documentclass[11pt]{article}",
        r"\usepackage[margin=1in]{geometry}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage{hyperref}",
        r"\usepackage{enumitem}",
        "",
        rf"\title{{{_latex_escape(manuscript['title'])}}}",
        r"\date{}",
        "",
        r"\begin{document}",
        r"\maketitle",
        "",
    ]
    for section in manuscript["sections"]:
        heading = "section*" if section.title == "Abstract" else "section"
        lines.append(rf"\{heading}{{{_latex_escape(section.title)}}}")
        lines.append("")
        for block in section.body.split("\n\n"):
            block = block.strip()
            if not block:
                continue
            bullet_lines = [line[2:] for line in block.splitlines() if line.startswith("- ")]
            if bullet_lines and len(bullet_lines) == len(block.splitlines()):
                lines.append(r"\begin{itemize}[leftmargin=1.2em]")
                for item in bullet_lines:
                    citation_ready = re.sub(r"\[@([^\]]+)\]", r"[\1]", item)
                    lines.append(rf"  \item {_latex_escape(citation_ready)}")
                lines.append(r"\end{itemize}")
            else:
                paragraph = re.sub(r"\[@([^\]]+)\]", r"[\1]", block)
                lines.append(_latex_escape(paragraph))
            lines.append("")
    lines.append(r"\section*{References}")
    if papers:
        lines.append(r"\begin{enumerate}[leftmargin=1.4em]")
        for paper in papers:
            lines.append(rf"  \item {_latex_escape(_paper_reference_line(paper))}")
        lines.append(r"\end{enumerate}")
    else:
        lines.append("No attached papers were available when the package was exported.")
    lines.extend(["", r"\bibliographystyle{plain}", r"\bibliography{references}", r"\end{document}", ""])
    return "\n".join(lines)


def _build_bibliography(papers: list[dict[str, Any]]) -> dict[str, Any]:
    warnings: list[str] = []
    for paper in papers:
        if not _stringify(paper.get("venue")):
            warnings.append(f"{_paper_citation_key(paper)} is missing venue metadata.")
        if not paper.get("year"):
            warnings.append(f"{_paper_citation_key(paper)} is missing publication year metadata.")
    return {
        "entry_count": len(papers),
        "references_markdown": "\n".join(f"- `{_paper_citation_key(paper)}` {_paper_reference_line(paper)}" for paper in papers) or "- No references available.",
        "bibtex": "\n\n".join(_bibtex_entry(paper) for paper in papers),
        "warnings": warnings,
    }


def _extract_citation_keys(markdown_text: str) -> list[str]:
    keys: list[str] = []
    for match in re.findall(r"\[@([A-Za-z0-9:_-]+)\]", markdown_text):
        if match not in keys:
            keys.append(match)
    for match in re.findall(r"\\cite\{([^}]+)\}", markdown_text):
        for key in match.split(","):
            candidate = key.strip()
            if candidate and candidate not in keys:
                keys.append(candidate)
    return keys


def _build_citation_verification(markdown_text: str, papers: list[dict[str, Any]]) -> dict[str, Any]:
    cited_keys = _extract_citation_keys(markdown_text)
    known_keys = {_paper_citation_key(paper) for paper in papers}
    verified_keys = [key for key in cited_keys if key in known_keys]
    missing_keys = sorted(key for key in cited_keys if key not in known_keys)
    unused_keys = sorted(key for key in known_keys if key not in cited_keys)
    warnings: list[str] = []
    if not cited_keys:
        warnings.append("No inline citation keys were found in the exported manuscript.")
    for paper in papers:
        if not _stringify(paper.get("doi")) and not _stringify(paper.get("url")):
            warnings.append(f"{_paper_citation_key(paper)} is missing both DOI and URL metadata.")
    status = "verified" if not missing_keys else "attention_required"
    summary = {
        "cited_key_count": len(cited_keys),
        "verified_key_count": len(verified_keys),
        "missing_key_count": len(missing_keys),
        "unused_key_count": len(unused_keys),
    }
    markdown_report = [
        "# Citation Verification",
        "",
        f"- Status: {status}",
        f"- Inline keys found: {summary['cited_key_count']}",
        f"- Verified keys: {summary['verified_key_count']}",
        f"- Missing keys: {summary['missing_key_count']}",
        f"- Unused source keys: {summary['unused_key_count']}",
        "",
        "## Verified Keys",
    ]
    markdown_report.extend(f"- {key}" for key in verified_keys or ["- None"])
    markdown_report.extend(["", "## Missing Keys"])
    markdown_report.extend(f"- {key}" for key in missing_keys or ["- None"])
    markdown_report.extend(["", "## Unused Keys"])
    markdown_report.extend(f"- {key}" for key in unused_keys or ["- None"])
    markdown_report.extend(["", "## Warnings"])
    markdown_report.extend(f"- {warning}" for warning in warnings or ["- None"])
    return {
        "status": status,
        "summary": summary,
        "verified_keys": verified_keys,
        "missing_keys": missing_keys,
        "unused_keys": unused_keys,
        "warnings": warnings,
        "report_markdown": "\n".join(markdown_report).strip() + "\n",
    }


def _build_claim_evidence_report(manuscript: dict[str, Any]) -> dict[str, Any]:
    claims = manuscript["claims"]
    supported = sum(1 for claim in claims if claim["status"] == "supported")
    weak = sum(1 for claim in claims if claim["status"] == "weak")
    unsupported = sum(1 for claim in claims if claim["status"] == "unsupported")
    warnings: list[str] = []
    if unsupported:
        warnings.append("At least one manuscript claim has no resolved evidence anchor.")
    if weak:
        warnings.append("Some manuscript claims are intentionally marked weak because the execution evidence is still provisional.")
    summary = {
        "claims_checked": len(claims),
        "supported": supported,
        "weak": weak,
        "unsupported": unsupported,
    }
    report_lines = [
        "# Claim-Evidence Consistency Report",
        "",
        f"- Claims checked: {summary['claims_checked']}",
        f"- Supported: {summary['supported']}",
        f"- Weak: {summary['weak']}",
        f"- Unsupported: {summary['unsupported']}",
        "",
        "## Claim Review",
    ]
    for item in claims:
        report_lines.append(f"### {item['section']} [{item['status']}]")
        report_lines.append(item["claim"])
        report_lines.append("")
        if item["supporting_sources"]:
            report_lines.append("Supporting sources:")
            report_lines.extend(
                f"- {source['type']}: {source['label']} ({source['ref']})" for source in item["supporting_sources"]
            )
        else:
            report_lines.append("Supporting sources:\n- None")
        report_lines.append(f"Rationale: {item['rationale']}")
        report_lines.append("")
    report_lines.extend(["## Warnings"])
    report_lines.extend(f"- {warning}" for warning in warnings or ["- None"])
    return {
        "status": "ok" if unsupported == 0 else "attention_required",
        "summary": summary,
        "claims": claims,
        "warnings": warnings,
        "report_markdown": "\n".join(report_lines).strip() + "\n",
    }


def _pdf_story_from_section(section: ManuscriptSection, styles: dict[str, ParagraphStyle]) -> list[Any]:
    story: list[Any] = [Paragraph(section.title, styles["heading"]), Spacer(1, 0.12 * inch)]
    for block in section.body.split("\n\n"):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if all(line.startswith("- ") for line in lines):
            for line in lines:
                story.append(Paragraph(line[2:], styles["bullet"], bulletText="•"))
                story.append(Spacer(1, 0.05 * inch))
        else:
            story.append(Paragraph("<br/>".join(lines), styles["body"]))
            story.append(Spacer(1, 0.1 * inch))
    story.append(Spacer(1, 0.08 * inch))
    return story


def _build_pdf(path: Path, manuscript: dict[str, Any], papers: list[dict[str, Any]]) -> Path:
    styles = getSampleStyleSheet()
    palette = {
        "heading": HexColor("#173038"),
        "body": HexColor("#13232b"),
        "muted": HexColor("#607681"),
    }
    doc_styles = {
        "title": ParagraphStyle(
            "ExportTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=28,
            textColor=palette["heading"],
            spaceAfter=14,
        ),
        "meta": ParagraphStyle(
            "ExportMeta",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=palette["muted"],
            spaceAfter=14,
        ),
        "heading": ParagraphStyle(
            "ExportHeading",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=palette["heading"],
            spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "ExportBody",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=15,
            textColor=palette["body"],
            spaceAfter=6,
        ),
        "bullet": ParagraphStyle(
            "ExportBullet",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            leftIndent=16,
            firstLineIndent=0,
            bulletIndent=5,
            textColor=palette["body"],
            spaceAfter=2,
        ),
    }

    def _draw_footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(palette["muted"])
        canvas.drawString(document.leftMargin, 0.55 * inch, manuscript["title"])
        canvas.drawRightString(LETTER[0] - document.rightMargin, 0.55 * inch, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    story: list[Any] = [
        Paragraph(manuscript["title"], doc_styles["title"]),
        Paragraph(f"Generated {manuscript['generated_at']}", doc_styles["meta"]),
    ]
    for section in manuscript["sections"]:
        story.extend(_pdf_story_from_section(section, doc_styles))
    story.append(Paragraph("References", doc_styles["heading"]))
    if papers:
        for paper in papers:
            story.append(Paragraph(_paper_reference_line(paper), doc_styles["bullet"], bulletText="•"))
            story.append(Spacer(1, 0.04 * inch))
    else:
        story.append(Paragraph("No attached papers were available when the package was exported.", doc_styles["body"]))

    doc = SimpleDocTemplate(
        str(path),
        pagesize=LETTER,
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        topMargin=0.85 * inch,
        bottomMargin=0.85 * inch,
        title=manuscript["title"],
    )
    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return path


def build_paper_export_payload(
    run_id: str,
    project: dict[str, Any],
    papers: list[dict[str, Any]],
    prior_outputs: list[dict[str, Any]],
) -> dict[str, Any]:
    stage_dir = _reset_stage_dir(project["id"], run_id, "paper_export")
    manuscript = _build_manuscript(project, papers, prior_outputs)
    bibliography = _build_bibliography(papers)

    markdown_path = _write_text(stage_dir / "manuscript.md", _markdown_document(manuscript, papers))
    latex_path = _write_text(stage_dir / "manuscript.tex", _latex_document(manuscript, papers))
    references_md_path = _write_text(stage_dir / "references.md", bibliography["references_markdown"] + "\n")
    bibtex_path = _write_text(stage_dir / "references.bib", bibliography["bibtex"] + ("\n" if bibliography["bibtex"] else ""))
    pdf_path = _build_pdf(stage_dir / "manuscript.pdf", manuscript, papers)

    citation_verification = _build_citation_verification(markdown_path.read_text(encoding="utf-8"), papers)
    citation_md_path = _write_text(stage_dir / "citation_verification.md", citation_verification["report_markdown"])
    citation_json_path = _json_write(stage_dir / "citation_verification.json", citation_verification)

    claim_report = _build_claim_evidence_report(manuscript)
    claim_md_path = _write_text(stage_dir / "claim_evidence_report.md", claim_report["report_markdown"])
    claim_json_path = _json_write(stage_dir / "claim_evidence_report.json", claim_report)

    markdown_package = {
        "status": "generated",
        "title": manuscript["title"],
        "section_count": len(manuscript["sections"]),
        "main_file": _file_entry(markdown_path, "Manuscript Markdown", "markdown", "paper_export"),
        "supporting_files": [
            _file_entry(references_md_path, "References Markdown", "markdown", "paper_export"),
        ],
    }
    latex_package = {
        "status": "generated",
        "main_file": _file_entry(latex_path, "Manuscript LaTeX", "latex", "paper_export"),
        "bibtex_file": _file_entry(bibtex_path, "References BibTeX", "bibtex", "paper_export"),
    }
    pdf_package = {
        "status": "generated",
        "main_file": _file_entry(pdf_path, "Compiled PDF", "pdf", "paper_export"),
        "page_profile": "letter",
    }
    bibliography_artifact = {
        "status": "generated",
        "entry_count": bibliography["entry_count"],
        "reference_list_file": _file_entry(references_md_path, "References Markdown", "markdown", "paper_export"),
        "bibtex_file": _file_entry(bibtex_path, "References BibTeX", "bibtex", "paper_export"),
        "warnings": bibliography["warnings"],
    }
    citation_artifact = {
        "status": citation_verification["status"],
        "summary": citation_verification["summary"],
        "verified_keys": citation_verification["verified_keys"],
        "missing_keys": citation_verification["missing_keys"],
        "unused_keys": citation_verification["unused_keys"],
        "warnings": citation_verification["warnings"],
        "markdown_report": _file_entry(citation_md_path, "Citation Verification", "markdown", "paper_export"),
        "json_report": _file_entry(citation_json_path, "Citation Verification JSON", "json", "paper_export"),
    }
    claim_artifact = {
        "status": claim_report["status"],
        "summary": claim_report["summary"],
        "claims": claim_report["claims"],
        "warnings": claim_report["warnings"],
        "markdown_report": _file_entry(claim_md_path, "Claim-Evidence Report", "markdown", "paper_export"),
        "json_report": _file_entry(claim_json_path, "Claim-Evidence Report JSON", "json", "paper_export"),
    }

    content_lines = [
        "# Paper Export",
        "",
        f"- Markdown package: {_file_entry(markdown_path, 'Manuscript Markdown', 'markdown', 'paper_export')['url']}",
        f"- LaTeX package: {_file_entry(latex_path, 'Manuscript LaTeX', 'latex', 'paper_export')['url']}",
        f"- PDF package: {_file_entry(pdf_path, 'Compiled PDF', 'pdf', 'paper_export')['url']}",
        f"- Bibliography entries: {bibliography['entry_count']}",
        f"- Citation status: {citation_verification['status']}",
        f"- Claim-evidence status: {claim_report['status']}",
        "",
        "## Export Notes",
        "- All final manuscript assets were written to disk under the paper_export stage directory.",
        "- Citation verification and claim-evidence reports are included alongside the manuscript.",
    ]
    if citation_verification["missing_keys"]:
        content_lines.append(
            "- Missing citation keys: " + ", ".join(citation_verification["missing_keys"])
        )
    if claim_report["warnings"]:
        content_lines.extend(f"- {warning}" for warning in claim_report["warnings"])

    return {
        "content_md": "\n".join(content_lines).strip() + "\n",
        "artifacts": {
            "markdown_package": markdown_package,
            "latex_package": latex_package,
            "pdf_package": pdf_package,
            "bibliography": bibliography_artifact,
            "citation_verification": citation_artifact,
            "claim_evidence_report": claim_artifact,
        },
        "notes": f"Generated Markdown, LaTeX, BibTeX, and PDF assets in {stage_dir}.",
    }


def _recommended_profile(project: dict[str, Any]) -> str:
    corpus = " ".join(
        [
            _stringify(project.get("title")).lower(),
            _stringify(project.get("direction")).lower(),
            _stringify(project.get("goals")).lower(),
        ]
    )
    if any(token in corpus for token in ("survey", "review", "journal")):
        return "journal_or_survey"
    if any(token in corpus for token in ("system", "systems", "latency", "throughput", "runtime", "infra")):
        return "systems_conference"
    return "ml_conference"


def _score_band(value: float) -> int:
    if value >= 0.9:
        return 5
    if value >= 0.75:
        return 4
    if value >= 0.55:
        return 3
    if value >= 0.35:
        return 2
    return 1


def _rubric_profile(
    profile: str,
    *,
    recommended: bool,
    section_count: int,
    citation_summary: dict[str, int],
    claim_summary: dict[str, int],
    package_complete: bool,
    sandbox_status: str,
    bibliography_count: int,
) -> dict[str, Any]:
    total_claims = max(1, claim_summary.get("claims_checked", 0))
    support_ratio = claim_summary.get("supported", 0) / total_claims
    citation_health = 1.0
    if citation_summary.get("cited_key_count", 0):
        citation_health -= citation_summary.get("missing_key_count", 0) / max(1, citation_summary.get("cited_key_count", 0))
    citation_health = max(0.0, citation_health)
    sandbox_ratio = 1.0 if sandbox_status in {"completed", "succeeded", "success"} else 0.45
    packaging_ratio = 1.0 if package_complete else 0.55
    section_ratio = min(1.0, section_count / 6)
    bibliography_ratio = min(1.0, bibliography_count / 6) if bibliography_count else 0.0

    profile_specs: dict[str, tuple[str, list[tuple[str, str, float]]]] = {
        "ml_conference": (
            "ML Conference",
            [
                ("scope", "Scope and positioning", section_ratio),
                ("evidence", "Evidence rigor", min(support_ratio, citation_health)),
                ("repro", "Artifact reproducibility", packaging_ratio),
                ("writing", "Writing clarity", (section_ratio + citation_health) / 2),
            ],
        ),
        "systems_conference": (
            "Systems Conference",
            [
                ("significance", "Problem significance", section_ratio),
                ("realism", "Implementation realism", sandbox_ratio),
                ("artifacts", "Artifact completeness", packaging_ratio),
                ("evaluation", "Evaluation discipline", min(support_ratio, sandbox_ratio)),
            ],
        ),
        "journal_or_survey": (
            "Journal or Survey",
            [
                ("coverage", "Coverage breadth", bibliography_ratio),
                ("citation_hygiene", "Citation hygiene", citation_health),
                ("synthesis", "Synthesis quality", section_ratio),
                ("writing", "Writing clarity", (section_ratio + support_ratio) / 2),
            ],
        ),
    }
    label, raw_criteria = profile_specs[profile]
    criteria = [
        {
            "key": key,
            "label": criterion_label,
            "score": _score_band(score),
            "max_score": 5,
        }
        for key, criterion_label, score in raw_criteria
    ]
    overall = round(sum(item["score"] for item in criteria) / max(1, len(criteria)), 2)
    return {
        "profile": profile,
        "label": label,
        "recommended": recommended,
        "overall_score": overall,
        "criteria": criteria,
    }


def build_peer_review_payload(
    run_id: str,
    project: dict[str, Any],
    papers: list[dict[str, Any]],
    prior_outputs: list[dict[str, Any]],
) -> dict[str, Any]:
    stage_dir = _reset_stage_dir(project["id"], run_id, "peer_review")
    stage_map = _stage_lookup(prior_outputs)
    export_artifacts = _stage_artifacts(stage_map, "paper_export")
    revision_artifacts = _stage_artifacts(stage_map, "paper_revision")
    sandbox_artifacts = _stage_artifacts(stage_map, "experiment_sandbox")

    citation_report = _dictify(export_artifacts.get("citation_verification"))
    citation_summary = _dictify(citation_report.get("summary"))
    claim_report = _dictify(export_artifacts.get("claim_evidence_report"))
    claim_summary = _dictify(claim_report.get("summary"))
    bibliography = _dictify(export_artifacts.get("bibliography"))
    markdown_package = _dictify(export_artifacts.get("markdown_package"))
    latex_package = _dictify(export_artifacts.get("latex_package"))
    pdf_package = _dictify(export_artifacts.get("pdf_package"))
    open_issues = _listify(revision_artifacts.get("open_issues"))
    sandbox_status = _stringify(_dictify(sandbox_artifacts.get("sandbox_result")).get("status")) or "not_run"

    package_complete = all(item.get("status") == "generated" for item in (markdown_package, latex_package, pdf_package))
    recommended_profile = _recommended_profile(project)
    rubrics = [
        _rubric_profile(
            profile,
            recommended=profile == recommended_profile,
            section_count=int(markdown_package.get("section_count") or 0),
            citation_summary={key: int(value or 0) for key, value in citation_summary.items()},
            claim_summary={key: int(value or 0) for key, value in claim_summary.items()},
            package_complete=package_complete,
            sandbox_status=sandbox_status,
            bibliography_count=int(bibliography.get("entry_count") or len(papers)),
        )
        for profile in ("ml_conference", "systems_conference", "journal_or_survey")
    ]

    findings: list[dict[str, Any]] = []
    fixes: list[dict[str, Any]] = []
    if _listify(citation_report.get("missing_keys")):
        findings.append(
            {
                "severity": "high",
                "area": "citation_hygiene",
                "finding": "Inline citation keys exist in the manuscript but do not resolve against the exported bibliography.",
            }
        )
        fixes.append(
            {
                "priority": "high",
                "action": "Resolve or remove missing citation keys before external review.",
            }
        )
    if int(claim_summary.get("unsupported", 0) or 0) > 0:
        findings.append(
            {
                "severity": "high",
                "area": "evidence_rigor",
                "finding": "At least one manuscript claim has no resolved evidence anchor across papers or experiment stages.",
            }
        )
        fixes.append(
            {
                "priority": "high",
                "action": "Either add evidence for unsupported claims or soften the wording in the manuscript export.",
            }
        )
    if sandbox_status not in {"completed", "succeeded", "success"}:
        findings.append(
            {
                "severity": "medium",
                "area": "experimental_readiness",
                "finding": f"Sandbox execution status is {sandbox_status}, so empirical claims should stay explicitly provisional.",
            }
        )
        fixes.append(
            {
                "priority": "medium",
                "action": "Rerun or repair the sandbox stage before positioning the manuscript as empirically closed.",
            }
        )
    if open_issues:
        findings.append(
            {
                "severity": "medium",
                "area": "revision_debt",
                "finding": f"{len(open_issues)} open issue(s) remain after revision and should be visible in the venue response plan.",
            }
        )
        fixes.append(
            {
                "priority": "medium",
                "action": "Address the remaining revision issues or cite them explicitly in the limitations section.",
            }
        )
    if not findings:
        findings.append(
            {
                "severity": "low",
                "area": "readiness",
                "finding": "No blocking review issue was detected by the automated rubric pass, but venue-specific tightening is still recommended.",
            }
        )
        fixes.append(
            {
                "priority": "low",
                "action": "Do a final manual pass on title, abstract, and positioning before submission.",
            }
        )

    report = {
        "recommended_profile": recommended_profile,
        "rubrics": rubrics,
        "findings": findings,
        "fixes": fixes,
    }
    _json_write(stage_dir / "peer_review.json", report)

    markdown_lines = [
        "# Peer Review",
        "",
        f"- Recommended venue profile: {recommended_profile}",
        "",
        "## Rubrics",
    ]
    for rubric in rubrics:
        badge = " (recommended)" if rubric["recommended"] else ""
        markdown_lines.append(f"### {rubric['label']}{badge}")
        markdown_lines.append(f"- Overall score: {rubric['overall_score']} / 5")
        markdown_lines.extend(
            f"- {item['label']}: {item['score']} / {item['max_score']}" for item in rubric["criteria"]
        )
        markdown_lines.append("")
    markdown_lines.append("## Findings")
    markdown_lines.extend(
        f"- [{item['severity']}] {item['finding']}" for item in findings
    )
    markdown_lines.extend(["", "## Fix Suggestions"])
    markdown_lines.extend(f"- [{item['priority']}] {item['action']}" for item in fixes)
    _write_text(stage_dir / "peer_review.md", "\n".join(markdown_lines).strip() + "\n")

    return {
        "content_md": "\n".join(markdown_lines).strip() + "\n",
        "artifacts": {
            "findings": findings,
            "fixes": fixes,
            "rubrics": rubrics,
        },
        "notes": "Generated venue-specific peer-review rubrics for ML conference, systems conference, and journal/survey profiles.",
    }


def _collect_stage_files(stage_dir: Path, source_stage: str) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    if not stage_dir.exists():
        return files
    for path in sorted(item for item in stage_dir.rglob("*") if item.is_file()):
        kind = path.suffix.lstrip(".") or "file"
        label = path.name.replace("_", " ").replace("-", " ").title()
        files.append(_file_entry(path, label, kind, source_stage))
    return files


def build_delivery_package_payload(
    run_id: str,
    project: dict[str, Any],
    plan_markdown: str,
    papers: list[dict[str, Any]],
    prior_outputs: list[dict[str, Any]],
) -> dict[str, Any]:
    stage_dir = _reset_stage_dir(project["id"], run_id, "delivery_package")
    export_root = EXPORT_DIR / project["id"] / run_id

    plan_path = _write_text(stage_dir / "approved_plan.md", plan_markdown.strip() + "\n")
    source_inventory_path = _json_write(
        stage_dir / "source_inventory.json",
        [
            {
                "title": _stringify(paper.get("title")),
                "citation_key": _paper_citation_key(paper),
                "year": paper.get("year") or 0,
                "venue": _stringify(paper.get("venue")),
                "doi": _stringify(paper.get("doi")),
                "url": _stringify(paper.get("url")),
            }
            for paper in papers
        ],
    )

    bundle_manifest = (
        [_file_entry(plan_path, "Approved Plan", "markdown", "delivery_package")]
        + [_file_entry(source_inventory_path, "Source Inventory", "json", "delivery_package")]
        + _collect_stage_files(export_root / "paper_export", "paper_export")
        + _collect_stage_files(export_root / "peer_review", "peer_review")
    )

    stage_map = _stage_lookup(prior_outputs)
    export_artifacts = _stage_artifacts(stage_map, "paper_export")
    review_artifacts = _stage_artifacts(stage_map, "peer_review")
    citation_report = _dictify(export_artifacts.get("citation_verification"))
    claim_report = _dictify(export_artifacts.get("claim_evidence_report"))
    review_findings = _listify(review_artifacts.get("findings"))

    next_steps: list[str] = []
    if _listify(citation_report.get("missing_keys")):
        next_steps.append("Resolve missing inline citation keys before external sharing.")
    if int(_dictify(claim_report.get("summary")).get("unsupported", 0) or 0) > 0:
        next_steps.append("Backfill or soften unsupported manuscript claims.")
    if review_findings:
        next_steps.append("Address the highest-severity peer-review findings and rerun the export.")
    if not next_steps:
        next_steps.append("Do a final human review of title, abstract, and venue positioning before submission.")

    delivery_summary = (
        f"Delivery bundle for {project['title']} with {len(bundle_manifest)} files, "
        f"{len(papers)} attached sources, and exported manuscript assets in Markdown, LaTeX, BibTeX, and PDF."
    )
    summary_md_path = _write_text(
        stage_dir / "delivery_summary.md",
        "\n".join(
            [
                "# Delivery Package",
                "",
                delivery_summary,
                "",
                "## Next Steps",
                *[f"- {item}" for item in next_steps],
            ]
        ).strip()
        + "\n",
    )
    manifest_path = _json_write(stage_dir / "bundle_manifest.json", bundle_manifest)
    bundle_manifest.extend(
        [
            _file_entry(summary_md_path, "Delivery Summary", "markdown", "delivery_package"),
            _file_entry(manifest_path, "Bundle Manifest", "json", "delivery_package"),
        ]
    )

    archive_path = stage_dir / f"{_slug(project['title'], 'research-package')}-delivery-bundle.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in bundle_manifest:
            file_path = Path(item["path"])
            if file_path.exists():
                archive.write(file_path, arcname=file_path.name)
    bundle_archive = _file_entry(archive_path, "Delivery Bundle Archive", "zip", "delivery_package")

    content_lines = [
        "# Delivery Package",
        "",
        f"- Summary: {delivery_summary}",
        f"- Bundle archive: {bundle_archive['url']}",
        "",
        "## Bundle Contents",
    ]
    content_lines.extend(f"- {item['label']} ({item['kind']}) -> {item['url']}" for item in bundle_manifest)
    content_lines.extend(["", "## Recommended Next Steps"])
    content_lines.extend(f"- {item}" for item in next_steps)

    return {
        "content_md": "\n".join(content_lines).strip() + "\n",
        "artifacts": {
            "delivery_summary": delivery_summary,
            "bundle_manifest": bundle_manifest,
            "next_steps": next_steps,
            "bundle_archive": bundle_archive,
        },
        "notes": f"Bundled delivery assets into {archive_path.name}.",
    }

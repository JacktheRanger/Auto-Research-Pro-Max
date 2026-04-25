from __future__ import annotations

from typing import Any

PROJECT_TEMPLATES: list[dict[str, Any]] = [
    {
        "key": "survey",
        "label": "Survey / Literature Review",
        "summary": (
            "Plan-gated research workflow tuned for structured literature surveys: heavy retrieval, "
            "thematic clustering, and a manuscript focused on synthesis instead of new experiments."
        ),
        "tags": ["literature", "synthesis", "survey"],
        "defaults": {
            "title": "Survey: ",
            "idea": (
                "Synthesize the recent literature on [TOPIC] to surface methodological clusters, "
                "open questions, and credible baselines."
            ),
            "background": (
                "The survey targets researchers entering [TOPIC]. Coverage should highlight cross-cutting "
                "ideas, methodological splits, and measurement debates rather than re-running experiments."
            ),
            "direction": (
                "Prioritize coverage breadth, identify weakly supported claims, and recommend "
                "follow-up reads with explicit provenance."
            ),
            "goals": (
                "Deliver a survey-style manuscript with topic clusters, contrasting methods, and "
                "an evidence-anchored summary of open problems."
            ),
            "constraints_text": (
                "Do not run new experiments. Do not invent results. Treat coverage gaps as explicit "
                "todos rather than glossing over them."
            ),
            "compute_budget": "CPU only / no GPU required",
            "api_budget": "Moderate (text generation + retrieval calls)",
            "sandbox_setup_command": "",
            "sandbox_run_command": "",
            "expected_artifacts": [],
        },
    },
    {
        "key": "benchmark",
        "label": "Benchmark Study",
        "summary": (
            "Workflow tuned for reproducible benchmark studies: emphasize evaluation matrix, "
            "baseline reproduction, and reporting tables that survive peer scrutiny."
        ),
        "tags": ["benchmark", "evaluation", "experiments"],
        "defaults": {
            "title": "Benchmark: ",
            "idea": (
                "Benchmark [METHOD] against established baselines on [TASK] using a shared, "
                "reproducible evaluation harness."
            ),
            "background": (
                "Existing reports on [TASK] use inconsistent splits and metrics. A grounded "
                "benchmark with deterministic seeds and accessible artifacts would unblock honest comparisons."
            ),
            "direction": (
                "Reproduce strongest baselines, isolate evaluation choices, and surface confidence "
                "intervals so the comparison is not driven by unreported configuration drift."
            ),
            "goals": (
                "Publish a transparent benchmark table with seeds, hardware notes, and per-metric "
                "uncertainty alongside an artifact bundle that reviewers can re-run."
            ),
            "constraints_text": (
                "Stay within the declared compute budget. Do not promote unverified leaderboard "
                "numbers without a sandbox-rerun anchor."
            ),
            "compute_budget": "1x4090 / single workstation acceptable",
            "api_budget": "Tight (planning + reviewer-facing prose only)",
            "sandbox_setup_command": "python -m venv .venv && .venv/bin/pip install -r requirements.txt",
            "sandbox_run_command": "make benchmark",
            "expected_artifacts": ["results/**/*.json", "logs/*.log"],
        },
    },
    {
        "key": "implementation",
        "label": "Implementation Project",
        "summary": (
            "Workflow tuned for engineering-heavy work: focus on prototyping, sandbox-backed "
            "validation, and pragmatic write-ups rather than literature breadth."
        ),
        "tags": ["implementation", "engineering", "prototype"],
        "defaults": {
            "title": "Implementation: ",
            "idea": (
                "Build a working prototype of [SYSTEM] with the smallest credible scope that "
                "exercises the load-bearing technical risk."
            ),
            "background": (
                "We need to know whether [SYSTEM] is feasible inside our compute envelope. The "
                "team prefers a runnable prototype with measured behavior over a paper-only proposal."
            ),
            "direction": (
                "Start from the riskiest module, sandbox the run loop, and iterate using validation "
                "and retry policies until the artifact bundle is stable."
            ),
            "goals": (
                "Ship a runnable prototype, captured sandbox metrics, and an implementation memo "
                "that other engineers can review and extend."
            ),
            "constraints_text": (
                "Keep dependencies minimal. Do not introduce undocumented services, secrets, or "
                "private datasets."
            ),
            "compute_budget": "Local workstation / single GPU",
            "api_budget": "Tight (planning + targeted code generation)",
            "sandbox_setup_command": "python -m venv .venv && .venv/bin/pip install -e .",
            "sandbox_run_command": "pytest -q",
            "expected_artifacts": ["dist/**/*", "logs/*.log"],
        },
    },
    {
        "key": "ablation_paper",
        "label": "Ablation-heavy Paper",
        "summary": (
            "Workflow tuned for papers where the contribution is a controlled set of ablations "
            "and the manuscript spends most of its bandwidth on isolating which knob mattered."
        ),
        "tags": ["ablation", "experiments", "paper"],
        "defaults": {
            "title": "Ablation Study: ",
            "idea": (
                "Quantify the contribution of [COMPONENT] in [METHOD] by sweeping ablation axes "
                "and reporting per-axis effect sizes."
            ),
            "background": (
                "Prior reports lump several improvements together. A disciplined ablation will let "
                "us attribute gains and surface regressions hidden inside the headline number."
            ),
            "direction": (
                "Design a minimal ablation matrix that isolates a small number of axes, run each "
                "configuration through the sandbox, and report effect sizes with confidence intervals."
            ),
            "goals": (
                "Produce a paper-ready ablation matrix, per-axis claims tied to sandbox artifacts, "
                "and a discussion of negative or null results."
            ),
            "constraints_text": (
                "Keep the matrix small enough to fit the compute budget. Do not collapse axes "
                "without explicit justification in the manuscript."
            ),
            "compute_budget": "Up to A100 x2 (matrix execution)",
            "api_budget": "Moderate (planning + manuscript)",
            "sandbox_setup_command": "python -m venv .venv && .venv/bin/pip install -r requirements.txt",
            "sandbox_run_command": "python ablations.py --all",
            "expected_artifacts": ["ablations/**/*.json", "tables/*.csv"],
        },
    },
]


def list_project_templates() -> list[dict[str, Any]]:
    return [
        {
            "key": item["key"],
            "label": item["label"],
            "summary": item["summary"],
            "tags": item.get("tags", []),
            "defaults": item.get("defaults", {}),
        }
        for item in PROJECT_TEMPLATES
    ]


def get_project_template(key: str) -> dict[str, Any] | None:
    for item in PROJECT_TEMPLATES:
        if item["key"] == key:
            return list_project_templates()[PROJECT_TEMPLATES.index(item)]
    return None

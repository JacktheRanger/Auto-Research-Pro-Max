export type Settings = {
  api_key: string;
  base_url: string;
  research_model: string;
  code_model: string;
  embedding_model: string;
  notes: string;
};

export type Project = {
  id: string;
  title: string;
  idea: string;
  background: string;
  direction: string;
  goals: string;
  constraints_text: string;
  compute_budget: string;
  api_budget: string;
  repo_path: string;
  repo_url: string;
  repo_ref: string;
  sandbox_workdir: string;
  sandbox_setup_command: string;
  sandbox_run_command: string;
  expected_artifacts: string[];
  status: string;
  created_at: string;
  updated_at: string;
  archived_at?: string;
  duplicated_from?: string;
  sandbox_base_image?: string;
  sandbox_extra_packages?: string[];
  sandbox_apt_packages?: string[];
  sandbox_pip_index_url?: string;
  sandbox_timeout_seconds?: number;
  sandbox_max_attempts?: number;
};

export type ProjectCreatePayload = {
  title: string;
  idea: string;
  background: string;
  direction: string;
  goals: string;
  constraints_text: string;
  compute_budget: string;
  api_budget: string;
  repo_path?: string;
  repo_url?: string;
  repo_ref?: string;
  sandbox_workdir?: string;
  sandbox_setup_command?: string;
  sandbox_run_command?: string;
  expected_artifacts?: string[];
};

export type ProjectExecutionPayload = {
  repo_path: string;
  repo_url: string;
  repo_ref: string;
  sandbox_workdir: string;
  sandbox_setup_command: string;
  sandbox_run_command: string;
  expected_artifacts: string[];
  sandbox_base_image?: string;
  sandbox_extra_packages?: string[];
  sandbox_apt_packages?: string[];
  sandbox_pip_index_url?: string;
  sandbox_timeout_seconds?: number;
  sandbox_max_attempts?: number;
};

export type Paper = {
  id: string;
  project_id: string;
  source_type: string;
  title: string;
  url: string;
  file_name: string;
  stored_path: string;
  notes: string;
  abstract: string;
  doi: string;
  venue: string;
  year: number;
  authors_json: string[];
  source_provider: string;
  external_id: string;
  canonical_key: string;
  citation_key: string;
  content_hash: string;
  extracted_text: string;
  preview_image_path: string;
  preview_thumbnail_path: string;
  stored_file_url: string;
  preview_image_url: string;
  preview_thumbnail_url: string;
  chunk_count: number;
  retrieval_ready: boolean;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type Plan = {
  project_id: string;
  status: string;
  plan_markdown: string;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type Run = {
  id: string;
  project_id: string;
  status: string;
  current_stage_index: number;
  total_stages: number;
  pending_gate_index: number;
  pending_gate_key: string;
  pending_gate_state: string;
  started_at: string;
  updated_at: string;
  finished_at: string;
  error: string;
  metadata_json: Record<string, unknown>;
};

export type StageContract = {
  inputs: string[];
  must_produce: string[];
  quality_bar: string[];
  disallowed: string[];
};

export type ArtifactSchemaItem = {
  key: string;
  label: string;
  type: string;
  description: string;
  required: boolean;
};

export type ApprovalGate = {
  label: string;
  summary: string;
  rollback_to_stage_key: string;
};

export type StageRetryPolicy = {
  max_attempts: number;
  base_delay_seconds: number;
  backoff_factor: number;
  retry_on_validation: boolean;
  retry_on_exception: boolean;
};

export type StageCatalogItem = {
  index: number;
  key: string;
  label: string;
  summary: string;
  owner: string;
  prompt_focus: string;
  contract: StageContract;
  artifact_schema: ArtifactSchemaItem[];
  approval_gate: ApprovalGate | null;
  retry_policy?: StageRetryPolicy;
};

export type RunStage = {
  run_id: string;
  stage_index: number;
  stage_key: string;
  stage_label: string;
  status: string;
  notes: string;
  content_md: string;
  started_at: string;
  completed_at: string;
  contract_json: StageContract;
  artifact_schema_json: ArtifactSchemaItem[];
  artifact_json: Record<string, unknown>;
  gate_status: string;
  approval_required: number;
  approval_label: string;
  rollback_target_index: number;
  error: string;
  metadata_json: Record<string, unknown>;
  gate_decided_by?: string;
  gate_comment?: string;
  gate_decided_at?: string;
};

export type RunAuditEvent = {
  id: string;
  run_id: string;
  stage_index: number;
  stage_key: string;
  gate_key: string;
  action: string;
  decided_by: string;
  comment: string;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export type RunControlPayload = {
  comment?: string;
  decided_by?: string;
};

export type PaperMetadataPayload = {
  title?: string;
  url?: string;
  notes?: string;
  abstract?: string;
  doi?: string;
  venue?: string;
  year?: number;
  authors_json?: string[] | string;
  citation_key?: string;
  source_provider?: string;
  external_id?: string;
  actor?: string;
};

export type RuntimeInfo = {
  host: string;
  port: number;
  mode: string;
  local_url: string;
  lan_urls: string[];
};

export type ProjectTemplate = {
  key: string;
  label: string;
  summary: string;
  tags: string[];
  defaults: {
    title?: string;
    idea?: string;
    background?: string;
    direction?: string;
    goals?: string;
    constraints_text?: string;
    compute_budget?: string;
    api_budget?: string;
    sandbox_setup_command?: string;
    sandbox_run_command?: string;
    expected_artifacts?: string[];
  };
};

export type LiteratureResult = {
  provider: string;
  title: string;
  abstract: string;
  year: number;
  venue: string;
  authors: string[];
  doi: string;
  url: string;
  pdf_url: string;
  external_id: string;
  citation_count: number;
  metadata: Record<string, unknown>;
  canonical_key: string;
};

export type LiteratureSearchResponse = {
  query: string;
  provider_results: Record<string, LiteratureResult[]>;
  results: LiteratureResult[];
  errors: Record<string, string>;
};

export type GroundedPaperResult = {
  paper_id: string;
  paper_title: string;
  citation_key: string;
  source_type: string;
  source_provider: string;
  doi: string;
  venue: string;
  year: number;
  url: string;
  preview_thumbnail_url: string;
  chunk_id: string;
  chunk_index: number;
  text: string;
  score: number;
  match_terms: string[];
  strategy: string;
};

export type GroundedSearchResponse = {
  query: string;
  strategy: string;
  results: GroundedPaperResult[];
};

export type CitationNode = {
  id: string;
  kind: "paper" | "doi" | "arxiv" | string;
  label: string;
  doi?: string;
  year?: number;
  venue?: string;
  citation_key?: string;
  preview_thumbnail_url?: string;
  external_id?: string;
};

export type CitationEdge = {
  source: string;
  target: string;
  kind: string;
};

export type CitationGraph = {
  nodes: CitationNode[];
  edges: CitationEdge[];
  summary: {
    papers: number;
    external_references: number;
    internal_links: number;
    unresolved_links: number;
  };
  unresolved_references: Array<{ source_paper_id: string; kind: string; id: string }>;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(errorBody || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string; stage_count: number }>("/api/health"),
  getRuntime: () => request<RuntimeInfo>("/api/runtime"),
  getStages: () => request<{ planning_gate: boolean; stages: StageCatalogItem[] }>("/api/stages"),
  getProjectTemplates: () =>
    request<{ templates: ProjectTemplate[] }>("/api/project-templates"),
  getSettings: () => request<Settings>("/api/settings"),
  saveSettings: (payload: Settings) =>
    request<Settings>("/api/settings", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  testSettings: (payload: Settings) =>
    request<{ ok: boolean; message: string }>("/api/settings/test", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listProjects: (params: { search?: string; include_archived?: boolean } = {}) => {
    const query = new URLSearchParams();
    if (params.search) {
      query.set("search", params.search);
    }
    if (params.include_archived === false) {
      query.set("include_archived", "false");
    }
    const suffix = query.toString();
    return request<{ projects: Project[]; total: number; search: string }>(
      suffix ? `/api/projects?${suffix}` : "/api/projects",
    );
  },
  createProject: (payload: ProjectCreatePayload) =>
    request<{ project: Project }>("/api/projects", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  duplicateProject: (projectId: string, title = "") =>
    request<{ project: Project; projects: Project[] }>(
      `/api/projects/${projectId}/duplicate`,
      {
        method: "POST",
        body: JSON.stringify({ title }),
      },
    ),
  archiveProject: (projectId: string) =>
    request<{ project: Project; projects: Project[] }>(
      `/api/projects/${projectId}/archive`,
      { method: "POST" },
    ),
  unarchiveProject: (projectId: string) =>
    request<{ project: Project; projects: Project[] }>(
      `/api/projects/${projectId}/unarchive`,
      { method: "POST" },
    ),
  deleteProject: (projectId: string) =>
    request<{ deleted: boolean; projects: Project[] }>(
      `/api/projects/${projectId}`,
      { method: "DELETE" },
    ),
  getProject: (projectId: string) =>
    request<{
      project: Project;
      papers: Paper[];
      plan: Plan | null;
      latest_run: Run | null;
    }>(`/api/projects/${projectId}`),
  updateProjectExecutionConfig: (projectId: string, payload: ProjectExecutionPayload) =>
    request<{ project: Project }>(`/api/projects/${projectId}/execution-config`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  uploadPaper: async (projectId: string, file: File, notes: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("notes", notes);
    const response = await fetch(`/api/projects/${projectId}/papers/upload`, {
      method: "POST",
      body: form,
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return response.json() as Promise<{ paper: Paper; papers: Paper[] }>;
  },
  addPaperUrl: (projectId: string, payload: { url: string; title: string; notes: string }) =>
    request<{ paper: Paper; papers: Paper[] }>(`/api/projects/${projectId}/papers/url`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  searchPaperGrounding: (projectId: string, payload: { query: string; limit?: number }) =>
    request<GroundedSearchResponse>(`/api/projects/${projectId}/papers/retrieve`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getCitationGraph: (projectId: string) =>
    request<CitationGraph>(`/api/projects/${projectId}/citation-graph`),
  searchLiterature: (projectId: string, payload: { query: string; limit_per_provider?: number }) =>
    request<LiteratureSearchResponse>(`/api/projects/${projectId}/literature/search`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  importLiteratureResult: (
    projectId: string,
    payload: LiteratureResult & { notes?: string },
  ) =>
    request<{ paper: Paper; papers: Paper[] }>(`/api/projects/${projectId}/papers/import`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updatePaperMetadata: (projectId: string, paperId: string, payload: PaperMetadataPayload) =>
    request<{ paper: Paper; papers: Paper[] }>(
      `/api/projects/${projectId}/papers/${paperId}`,
      {
        method: "PUT",
        body: JSON.stringify(payload),
      },
    ),
  refreshPaperMetadata: (projectId: string, paperId: string) =>
    request<{ paper: Paper; papers: Paper[] }>(
      `/api/projects/${projectId}/papers/${paperId}/refresh`,
      {
        method: "POST",
      },
    ),
  runPaperOcr: (projectId: string, paperId: string) =>
    request<{ paper: Paper; papers: Paper[] }>(
      `/api/projects/${projectId}/papers/${paperId}/ocr`,
      {
        method: "POST",
      },
    ),
  deletePaper: (projectId: string, paperId: string) =>
    request<{ deleted: boolean; papers: Paper[] }>(
      `/api/projects/${projectId}/papers/${paperId}`,
      {
        method: "DELETE",
      },
    ),
  generatePlan: (projectId: string) =>
    request<{ plan: Plan }>(`/api/projects/${projectId}/plan/generate`, {
      method: "POST",
    }),
  approvePlan: (projectId: string) =>
    request<{ plan: Plan }>(`/api/projects/${projectId}/plan/approve`, {
      method: "POST",
    }),
  startRun: (projectId: string) =>
    request<{ run: Run; stages: RunStage[] }>(`/api/projects/${projectId}/runs/start`, {
      method: "POST",
    }),
  getRun: (runId: string) =>
    request<{ run: Run; stages: RunStage[]; audit_events: RunAuditEvent[] }>(
      `/api/runs/${runId}`,
    ),
  getRunAudit: (runId: string) =>
    request<{ run_id: string; audit_events: RunAuditEvent[] }>(`/api/runs/${runId}/audit`),
  pauseRun: (runId: string, payload: RunControlPayload = {}) =>
    request<{ run: Run; stages: RunStage[]; audit_events: RunAuditEvent[] }>(
      `/api/runs/${runId}/control/pause`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    ),
  resumeRun: (runId: string, payload: RunControlPayload = {}) =>
    request<{ run: Run; stages: RunStage[]; audit_events: RunAuditEvent[] }>(
      `/api/runs/${runId}/control/resume`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    ),
  rejectRun: (runId: string, payload: RunControlPayload = {}) =>
    request<{ run: Run; stages: RunStage[]; audit_events: RunAuditEvent[] }>(
      `/api/runs/${runId}/control/reject`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    ),
  rollbackRun: (runId: string, payload: RunControlPayload = {}) =>
    request<{ run: Run; stages: RunStage[]; audit_events: RunAuditEvent[] }>(
      `/api/runs/${runId}/control/rollback`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    ),
  retryStage: (runId: string, stageIndex: number) =>
    request<{ run: Run; stages: RunStage[]; audit_events: RunAuditEvent[] }>(
      `/api/runs/${runId}/stages/${stageIndex}/retry`,
      {
        method: "POST",
      },
    ),
};

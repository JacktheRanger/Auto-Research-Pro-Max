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
  status: string;
  created_at: string;
  updated_at: string;
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
  extracted_text: string;
  metadata_json: Record<string, unknown>;
  created_at: string;
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
};

export type RuntimeInfo = {
  host: string;
  port: number;
  mode: string;
  local_url: string;
  lan_urls: string[];
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
  listProjects: () => request<{ projects: Project[] }>("/api/projects"),
  createProject: (payload: Omit<Project, "id" | "status" | "created_at" | "updated_at">) =>
    request<{ project: Project }>("/api/projects", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getProject: (projectId: string) =>
    request<{
      project: Project;
      papers: Paper[];
      plan: Plan | null;
      latest_run: Run | null;
    }>(`/api/projects/${projectId}`),
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
  getRun: (runId: string) => request<{ run: Run; stages: RunStage[] }>(`/api/runs/${runId}`),
  pauseRun: (runId: string) =>
    request<{ run: Run; stages: RunStage[] }>(`/api/runs/${runId}/control/pause`, {
      method: "POST",
    }),
  resumeRun: (runId: string) =>
    request<{ run: Run; stages: RunStage[] }>(`/api/runs/${runId}/control/resume`, {
      method: "POST",
    }),
  rejectRun: (runId: string) =>
    request<{ run: Run; stages: RunStage[] }>(`/api/runs/${runId}/control/reject`, {
      method: "POST",
    }),
  rollbackRun: (runId: string) =>
    request<{ run: Run; stages: RunStage[] }>(`/api/runs/${runId}/control/rollback`, {
      method: "POST",
    }),
};

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
  extracted_text: string;
  created_at: string;
};

export type Plan = {
  project_id: string;
  status: string;
  plan_markdown: string;
  created_at: string;
  updated_at: string;
};

export type Run = {
  id: string;
  project_id: string;
  status: string;
  current_stage_index: number;
  total_stages: number;
  started_at: string;
  updated_at: string;
  finished_at: string;
  error: string;
};

export type StageCatalogItem = {
  index: number;
  key: string;
  label: string;
  summary: string;
  owner: string;
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
};

export type RuntimeInfo = {
  host: string;
  port: number;
  mode: string;
  local_url: string;
  lan_urls: string[];
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
};

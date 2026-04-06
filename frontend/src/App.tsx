import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import { StageTimeline } from "./components/StageTimeline";
import {
  api,
  type Paper,
  type Plan,
  type Project,
  type RuntimeInfo,
  type Run,
  type RunStage,
  type Settings,
  type StageCatalogItem,
} from "./lib/api";

type ThemeMode = "light" | "dark";
type LocaleMode = "en" | "cn";

const stageLocaleCopy: Record<
  LocaleMode,
  Record<string, { label: string; summary: string; owner: string }>
> = {
  en: {},
  cn: {
    scope_alignment: {
      label: "范围对齐",
      summary: "把原始 idea、背景和约束收敛成一个边界明确的研究目标。",
      owner: "研究策略 Agent",
    },
    source_grounding: {
      label: "来源 Grounding",
      summary: "整理用户指定论文和来源，把它们转成后续可用的上下文材料。",
      owner: "论文输入 Agent",
    },
    literature_map: {
      label: "文献地图",
      summary: "产出主题、基线方法和开放问题的结构化视图。",
      owner: "文献分析 Agent",
    },
    synthesis: {
      label: "综合归纳",
      summary: "提炼可验证的假设、关键假设前提和值得下注的研究方向。",
      owner: "综合分析 Agent",
    },
    experiment_design: {
      label: "实验设计",
      summary: "定义数据集、评估指标、消融实验和成功标准。",
      owner: "实验设计 Agent",
    },
    code_prototype: {
      label: "代码原型",
      summary: "生成第一版实现草案和运行检查清单。",
      owner: "Codex 构建 Agent",
    },
    execution_review: {
      label: "执行评审",
      summary: "评估可行性、预估运行成本，并提前整理失败与修复路径。",
      owner: "执行评审 Agent",
    },
    paper_draft: {
      label: "论文草稿",
      summary: "组织摘要、提纲、贡献点和第一版论文稿。",
      owner: "论文写作 Agent",
    },
    peer_review: {
      label: "同行评审",
      summary: "压力测试核心论点，找出缺口并提出修改任务。",
      owner: "评审小组",
    },
    delivery_package: {
      label: "交付包",
      summary: "把批准后的计划、阶段输出和下一步建议整理成最终交付材料。",
      owner: "交付管理 Agent",
    },
  },
};

const uiCopy = {
  en: {
    ready: "Ready.",
    brandTitle: "Plan-gated research GUI for idea-to-delivery workflows.",
    brandBody:
      "Start from an idea, ground it with papers, approve the plan, and track execution in one place.",
    backendReady: "Backend ready",
    backendOffline: "Backend offline",
    liveStages: (count: number) => `${count} live stages`,
    setup: "Codex / OpenAI Setup",
    save: "Save",
    apiKey: "API Key",
    researchModel: "Research Model",
    codeModel: "Code Model",
    embeddingModel: "Embedding Model",
    notes: "Notes",
    optional: "optional",
    notesPlaceholder: "Optional provider notes, routing notes, or usage policy.",
    testConnection: "Test Connection",
    noConnectionTest: "No connection test yet.",
    projects: "Projects",
    heroEyebrow: "Mandatory Intake Before Execution",
    heroTitle: "Require idea, background, direction, and must-read papers before planning.",
    createProject: "Create Project",
    ideaTitle: "Idea / Title",
    ideaTitlePlaceholder: "A concise project title",
    researchIdea: "Research Idea",
    researchIdeaPlaceholder: "What do you want the system to investigate?",
    background: "Background / Domain Context",
    backgroundPlaceholder: "Context that should shape retrieval, design, and writing.",
    direction: "Direction / Focus",
    directionPlaceholder: "Preferred angle, method family, venue, or scope.",
    goals: "Deliverable Goals",
    goalsPlaceholder: "What should success look like in v1?",
    constraints: "Constraints",
    constraintsPlaceholder:
      "Known boundaries, forbidden approaches, deadlines, datasets, etc.",
    computeBudget: "Compute Budget",
    computeBudgetPlaceholder: "CPU only / 1x4090 / A100 x2",
    apiBudget: "API Budget",
    apiBudgetPlaceholder: "$20 / no hard cap / internal",
    paperIntake: "Paper Intake",
    paperIntakeBody:
      "Add must-read papers before generating the plan. Local PDFs are parsed; URLs are stored and remote PDFs are downloaded when possible.",
    localPdf: "Local PDF",
    uploadPdf: "Upload PDF",
    remoteUrl: "Remote URL",
    title: "Title",
    titlePlaceholder: "Optional title override",
    whyPaper: "Why this paper matters",
    whySource: "Why this source should shape the plan",
    remoteUrlPlaceholder: "arXiv / DOI / PDF / paper page",
    addUrlSource: "Add URL Source",
    planningGate: "Planning Gate",
    generatePlan: "Generate Plan",
    approvePlan: "Approve Plan",
    startRun: "Start Run",
    noPlanYet:
      "No plan yet. Create a project, attach papers, then generate the plan.",
    runSummary: "Run Summary",
    noRun: "No run started yet.",
    runStatus: "Run Status",
    currentStage: "Current Stage",
    started: "Started",
    planningGateLabel: "Planning gate",
    reducedPipelineNote:
      "The current product is temporarily set to 10 stages. More stages will be added in later iterations, and the follow-up work is tracked in TODO.md.",
    pipelineStages: "Current Stage Plan",
    selectedStageOutput: "Selected Stage Output",
    selectedStagePlaceholder:
      "Run the pipeline to populate stage output. Click any stage card to inspect its content.",
    sourceGroundingSnapshot: "Source Grounding Snapshot",
    noExtractedText: "No extracted text yet.",
    white: "White",
    black: "Black",
    en: "EN",
    cn: "CN",
    settingsSaved: "Settings saved.",
    projectCreated: "Project created.",
    localPaperAdded: "Local paper added.",
    remotePaperAdded: "Remote paper added.",
    planGenerated: "Plan generated. Review before starting.",
    planApproved: "Plan approved.",
    runStarted: "Run started.",
    wsConnected: "Live stage updates connected.",
    wsDisconnected: "Live updates disconnected.",
    copyLanUrl: "Copy LAN URL",
    lanUrlCopied: "LAN URL copied.",
    lanUrlCopyFailed: "LAN URL copy failed.",
  },
  cn: {
    ready: "已就绪。",
    brandTitle: "带计划审批门的研究工作流 GUI。",
    brandBody: "从 idea 出发，用论文做 grounding，先审批计划，再在一个界面里追踪整个执行流程。",
    backendReady: "后端已就绪",
    backendOffline: "后端离线",
    liveStages: (count: number) => `${count} 个阶段`,
    setup: "Codex / OpenAI 设置",
    save: "保存",
    apiKey: "API Key",
    researchModel: "研究模型",
    codeModel: "代码模型",
    embeddingModel: "Embedding 模型",
    notes: "备注",
    optional: "可选",
    notesPlaceholder: "可填写提供方说明、路由策略或使用规范。",
    testConnection: "测试连接",
    noConnectionTest: "还没有连接测试结果。",
    projects: "项目",
    heroEyebrow: "执行前必须先完成 Intake",
    heroTitle: "先提供 idea、背景、方向和必读论文，再进入计划阶段。",
    createProject: "创建项目",
    ideaTitle: "Idea / 标题",
    ideaTitlePlaceholder: "输入一个简洁的项目标题",
    researchIdea: "研究想法",
    researchIdeaPlaceholder: "你希望系统研究什么？",
    background: "背景 / 领域上下文",
    backgroundPlaceholder: "这些上下文会影响检索、设计和写作。",
    direction: "方向 / 聚焦点",
    directionPlaceholder: "偏好的方法路线、方向、目标会议或范围。",
    goals: "交付目标",
    goalsPlaceholder: "对 v1 来说，什么算成功？",
    constraints: "约束条件",
    constraintsPlaceholder: "已知边界、禁止方案、截止时间、数据集等。",
    computeBudget: "算力预算",
    computeBudgetPlaceholder: "仅 CPU / 1x4090 / A100 x2",
    apiBudget: "API 预算",
    apiBudgetPlaceholder: "$20 / 无硬上限 / 内部额度",
    paperIntake: "论文输入",
    paperIntakeBody:
      "在生成计划前先添加必读论文。本地 PDF 会解析；URL 会被记录，远程 PDF 会尽量下载和提取。",
    localPdf: "本地 PDF",
    uploadPdf: "上传 PDF",
    remoteUrl: "远程 URL",
    title: "标题",
    titlePlaceholder: "可选标题覆盖",
    whyPaper: "这篇论文为何重要",
    whySource: "这个来源为什么会影响计划",
    remoteUrlPlaceholder: "arXiv / DOI / PDF / 论文页面",
    addUrlSource: "添加 URL 来源",
    planningGate: "计划门控",
    generatePlan: "生成计划",
    approvePlan: "批准计划",
    startRun: "启动运行",
    noPlanYet: "还没有计划。先创建项目、添加论文，然后生成计划。",
    runSummary: "运行概览",
    noRun: "还没有启动运行。",
    runStatus: "运行状态",
    currentStage: "当前阶段",
    started: "开始时间",
    planningGateLabel: "计划门控",
    reducedPipelineNote:
      "当前产品暂定 10 个 stages，后续会继续扩展更多 stages，相关事项已记录在 TODO.md。",
    pipelineStages: "当前阶段规划",
    selectedStageOutput: "当前阶段输出",
    selectedStagePlaceholder: "运行后这里会出现阶段输出。点击任意阶段卡片即可查看内容。",
    sourceGroundingSnapshot: "来源论文快照",
    noExtractedText: "还没有提取文本。",
    white: "白色",
    black: "黑色",
    en: "EN",
    cn: "CN",
    settingsSaved: "设置已保存。",
    projectCreated: "项目已创建。",
    localPaperAdded: "本地论文已添加。",
    remotePaperAdded: "远程论文已添加。",
    planGenerated: "计划已生成。请先审阅再启动。",
    planApproved: "计划已批准。",
    runStarted: "运行已启动。",
    wsConnected: "实时阶段更新已连接。",
    wsDisconnected: "实时更新已断开。",
    copyLanUrl: "复制 LAN URL",
    lanUrlCopied: "LAN URL 已复制。",
    lanUrlCopyFailed: "复制 LAN URL 失败。",
  },
} satisfies Record<LocaleMode, Record<string, string | ((count: number) => string)>>;

const emptySettings: Settings = {
  api_key: "",
  base_url: "https://api.openai.com/v1",
  research_model: "gpt-5.4",
  code_model: "gpt-5.4",
  embedding_model: "",
  notes: "",
};

const emptyProjectForm = {
  title: "",
  idea: "",
  background: "",
  direction: "",
  goals: "",
  constraints_text: "",
  compute_budget: "",
  api_budget: "",
};

type ProjectDetail = {
  project: Project;
  papers: Paper[];
  plan: Plan | null;
  latest_run: Run | null;
};

export default function App() {
  const [locale, setLocale] = useState<LocaleMode>(() => {
    if (typeof window === "undefined") {
      return "en";
    }
    const saved = window.localStorage.getItem("arpm-locale");
    return saved === "cn" ? "cn" : "en";
  });
  const [theme, setTheme] = useState<ThemeMode>(() => {
    if (typeof window === "undefined") {
      return "light";
    }
    const saved = window.localStorage.getItem("arpm-theme");
    return saved === "dark" ? "dark" : "light";
  });
  const [settings, setSettings] = useState<Settings>(emptySettings);
  const [projects, setProjects] = useState<Project[]>([]);
  const [stageCatalog, setStageCatalog] = useState<StageCatalogItem[]>([]);
  const [projectForm, setProjectForm] = useState(emptyProjectForm);
  const [urlPaper, setUrlPaper] = useState({ url: "", title: "", notes: "" });
  const [uploadNotes, setUploadNotes] = useState("");
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [projectDetail, setProjectDetail] = useState<ProjectDetail | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [runStages, setRunStages] = useState<RunStage[]>([]);
  const [selectedStageIndex, setSelectedStageIndex] = useState(1);
  const [statusMessage, setStatusMessage] = useState(uiCopy.en.ready);
  const [connectionMessage, setConnectionMessage] = useState("");
  const [health, setHealth] = useState<{ status: string; stage_count: number } | null>(null);
  const [runtimeInfo, setRuntimeInfo] = useState<RuntimeInfo | null>(null);

  useEffect(() => {
    void bootstrap();
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("arpm-theme", theme);
  }, [theme]);

  useEffect(() => {
    document.documentElement.lang = locale === "cn" ? "zh-CN" : "en";
    window.localStorage.setItem("arpm-locale", locale);
  }, [locale]);

  const text = uiCopy[locale];

  async function bootstrap() {
    const [healthResponse, runtimeResponse, stagesResponse, settingsResponse, projectResponse] =
      await Promise.all([
        api.health(),
        api.getRuntime(),
        api.getStages(),
        api.getSettings(),
        api.listProjects(),
      ]);
    setHealth(healthResponse);
    setRuntimeInfo(runtimeResponse);
    setStageCatalog(stagesResponse.stages);
    setSettings(settingsResponse);
    setProjects(projectResponse.projects);
    if (projectResponse.projects[0]) {
      void loadProject(projectResponse.projects[0].id);
    }
  }

  async function loadProject(projectId: string) {
    const detail = await api.getProject(projectId);
    setSelectedProjectId(projectId);
    setProjectDetail(detail);
    setRun(detail.latest_run);
    setSelectedStageIndex(detail.latest_run?.current_stage_index || 1);
    if (detail.latest_run) {
      const runDetail = await api.getRun(detail.latest_run.id);
      setRunStages(runDetail.stages);
    } else {
      setRunStages([]);
    }
  }

  useEffect(() => {
    if (!run || run.status !== "running") {
      return;
    }
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${window.location.host}/ws/runs/${run.id}`);
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data) as { run: Run; stages: RunStage[] };
      setRun(payload.run);
      setRunStages(payload.stages);
      setSelectedStageIndex(payload.run.current_stage_index || 1);
    };
    socket.onopen = () => setConnectionMessage(text.wsConnected);
    socket.onclose = () => setConnectionMessage(text.wsDisconnected);
    const heartbeat = window.setInterval(() => {
      socket.send("ping");
    }, 15000);
    return () => {
      clearInterval(heartbeat);
      socket.close();
    };
  }, [run?.id, run?.status]);

  const selectedStage = useMemo(
    () => runStages.find((item) => item.stage_index === selectedStageIndex),
    [runStages, selectedStageIndex],
  );

  const localizedStageCatalog = useMemo(
    () =>
      stageCatalog.map((stage) => {
        const localized = stageLocaleCopy[locale][stage.key];
        if (!localized) {
          return stage;
        }
        return {
          ...stage,
          ...localized,
        };
      }),
    [locale, stageCatalog],
  );

  async function handleSaveSettings() {
    const saved = await api.saveSettings(settings);
    setSettings(saved);
    setStatusMessage(text.settingsSaved);
  }

  async function handleTestSettings() {
    const result = await api.testSettings(settings);
    setConnectionMessage(result.message);
  }

  async function handleCreateProject(event: React.FormEvent) {
    event.preventDefault();
    const created = await api.createProject(projectForm);
    const projectList = await api.listProjects();
    setProjects(projectList.projects);
    setProjectForm(emptyProjectForm);
    setStatusMessage(text.projectCreated);
    await loadProject(created.project.id);
  }

  async function handleUploadPaper(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const file = form.get("paper") as File | null;
    if (!selectedProjectId || !file) {
      return;
    }
    const response = await api.uploadPaper(selectedProjectId, file, uploadNotes);
    setProjectDetail((current) =>
      current
        ? {
            ...current,
            papers: response.papers,
          }
        : current,
    );
    setUploadNotes("");
    event.currentTarget.reset();
    setStatusMessage(text.localPaperAdded);
  }

  async function handleAddPaperUrl(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedProjectId) {
      return;
    }
    const response = await api.addPaperUrl(selectedProjectId, urlPaper);
    setProjectDetail((current) =>
      current
        ? {
            ...current,
            papers: response.papers,
          }
        : current,
    );
    setUrlPaper({ url: "", title: "", notes: "" });
    setStatusMessage(text.remotePaperAdded);
  }

  async function handleGeneratePlan() {
    if (!selectedProjectId) {
      return;
    }
    const result = await api.generatePlan(selectedProjectId);
    setProjectDetail((current) => (current ? { ...current, plan: result.plan } : current));
    setStatusMessage(text.planGenerated);
  }

  async function handleApprovePlan() {
    if (!selectedProjectId) {
      return;
    }
    const result = await api.approvePlan(selectedProjectId);
    setProjectDetail((current) => (current ? { ...current, plan: result.plan } : current));
    setStatusMessage(text.planApproved);
  }

  async function handleStartRun() {
    if (!selectedProjectId) {
      return;
    }
    const result = await api.startRun(selectedProjectId);
    setRun(result.run);
    setRunStages(result.stages);
    setSelectedStageIndex(1);
    setStatusMessage(text.runStarted);
  }

  function preferredLanUrl(info: RuntimeInfo | null): string | null {
    if (!info || info.mode !== "lan") {
      return null;
    }
    const currentHost = window.location.hostname;
    const currentOrigin = window.location.origin;
    if (!["127.0.0.1", "localhost"].includes(currentHost)) {
      return currentOrigin;
    }
    const preferred =
      info.lan_urls.find((url) => /^http:\/\/192\.168\./.test(url)) ??
      info.lan_urls.find((url) => /^http:\/\/10\./.test(url)) ??
      info.lan_urls.find((url) => /^http:\/\/172\.(1[6-9]|2\d|3[0-1])\./.test(url)) ??
      info.lan_urls[0];
    return preferred ?? null;
  }

  async function copyText(value: string) {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return;
    }
    const textarea = document.createElement("textarea");
    textarea.value = value;
    textarea.setAttribute("readonly", "true");
    textarea.style.position = "absolute";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    document.body.removeChild(textarea);
  }

  async function handleCopyLanUrl() {
    const target = preferredLanUrl(runtimeInfo);
    if (!target) {
      setConnectionMessage(text.lanUrlCopyFailed);
      return;
    }
    try {
      await copyText(target);
      setConnectionMessage(text.lanUrlCopied);
    } catch {
      setConnectionMessage(text.lanUrlCopyFailed);
    }
  }

  const approvalReady = projectDetail?.plan?.status === "ready";
  const runReady = projectDetail?.plan?.status === "approved";
  const lanCopyTarget = preferredLanUrl(runtimeInfo);

  return (
    <div className="page-shell">
      <section className="hero">
        <div className="hero-copy">
          <h1 className="hero-brand">Auto Research Pro Max</h1>
          <span className="eyebrow">{text.heroEyebrow}</span>
          <h2>{text.heroTitle}</h2>
        </div>
        <div className="status-stack">
          {runtimeInfo?.mode === "lan" && lanCopyTarget ? (
            <button className="secondary utility-button" onClick={handleCopyLanUrl} type="button">
              {text.copyLanUrl}
            </button>
          ) : null}
          <div aria-label="Language toggle" className="theme-toggle" role="group">
            <button
              className={`theme-option ${locale === "en" ? "active" : ""}`}
              onClick={() => setLocale("en")}
              type="button"
            >
              {text.en}
            </button>
            <button
              className={`theme-option ${locale === "cn" ? "active" : ""}`}
              onClick={() => setLocale("cn")}
              type="button"
            >
              {text.cn}
            </button>
          </div>
          <div aria-label="Theme toggle" className="theme-toggle" role="group">
            <button
              className={`theme-option ${theme === "light" ? "active" : ""}`}
              onClick={() => setTheme("light")}
              type="button"
            >
              {text.white}
            </button>
            <button
              className={`theme-option ${theme === "dark" ? "active" : ""}`}
              onClick={() => setTheme("dark")}
              type="button"
            >
              {text.black}
            </button>
          </div>
          <span>{statusMessage}</span>
          <span>{connectionMessage}</span>
        </div>
      </section>

      <div className="app-shell">
        <aside className="left-rail">
        <section className="brand-card">
          <span className="eyebrow">Auto Research Pro Max</span>
          <h1>{text.brandTitle}</h1>
          <p>{text.brandBody}</p>
          <div className="meta-row">
            <span>{health?.status === "ok" ? text.backendReady : text.backendOffline}</span>
            <span>{text.liveStages(health?.stage_count ?? 0)}</span>
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>{text.setup}</h2>
            <button onClick={handleSaveSettings} type="button">
              {text.save}
            </button>
          </div>
          <label>
            {text.apiKey}
            <input
              type="password"
              value={settings.api_key}
              onChange={(event) => setSettings({ ...settings, api_key: event.target.value })}
              placeholder="sk-..."
            />
          </label>
          <label>
            Base URL
            <input
              value={settings.base_url}
              onChange={(event) => setSettings({ ...settings, base_url: event.target.value })}
            />
          </label>
          <label>
            {text.researchModel}
            <input
              value={settings.research_model}
              onChange={(event) => setSettings({ ...settings, research_model: event.target.value })}
              placeholder="gpt-5.4"
            />
          </label>
          <label>
            {text.codeModel}
            <input
              value={settings.code_model}
              onChange={(event) => setSettings({ ...settings, code_model: event.target.value })}
              placeholder="gpt-5.4"
            />
          </label>
          <label>
            {text.embeddingModel}
            <input
              value={settings.embedding_model}
              onChange={(event) =>
                setSettings({ ...settings, embedding_model: event.target.value })
              }
              placeholder={text.optional}
            />
          </label>
          <label>
            {text.notes}
            <textarea
              value={settings.notes}
              onChange={(event) => setSettings({ ...settings, notes: event.target.value })}
              placeholder={text.notesPlaceholder}
            />
          </label>
          <button className="secondary" onClick={handleTestSettings} type="button">
            {text.testConnection}
          </button>
          <p className="muted">{connectionMessage || text.noConnectionTest}</p>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>{text.projects}</h2>
          </div>
          <div className="project-list">
            {projects.map((project) => (
              <button
                key={project.id}
                className={`project-chip ${selectedProjectId === project.id ? "selected" : ""}`}
                onClick={() => void loadProject(project.id)}
                type="button"
              >
                <strong>{project.title}</strong>
                <span>{project.status}</span>
              </button>
            ))}
          </div>
        </section>
        </aside>

        <main className="main-column">
        <section className="grid two-up">
          <form className="panel" onSubmit={handleCreateProject}>
            <div className="panel-header">
              <h2>{text.createProject}</h2>
            </div>
            <label>
              <span className="field-label">
                <span>{text.ideaTitle}</span>
                <span className="required-mark">*</span>
              </span>
              <input
                required
                value={projectForm.title}
                onChange={(event) =>
                  setProjectForm({ ...projectForm, title: event.target.value })
                }
                placeholder={text.ideaTitlePlaceholder}
              />
            </label>
            <label>
              <span className="field-label">
                <span>{text.researchIdea}</span>
                <span className="required-mark">*</span>
              </span>
              <textarea
                required
                value={projectForm.idea}
                onChange={(event) => setProjectForm({ ...projectForm, idea: event.target.value })}
                placeholder={text.researchIdeaPlaceholder}
              />
            </label>
            <label>
              <span className="field-label">
                <span>{text.background}</span>
                <span className="required-mark">*</span>
              </span>
              <textarea
                required
                value={projectForm.background}
                onChange={(event) =>
                  setProjectForm({ ...projectForm, background: event.target.value })
                }
                placeholder={text.backgroundPlaceholder}
              />
            </label>
            <label>
              <span className="field-label">
                <span>{text.direction}</span>
                <span className="required-mark">*</span>
              </span>
              <textarea
                required
                value={projectForm.direction}
                onChange={(event) =>
                  setProjectForm({ ...projectForm, direction: event.target.value })
                }
                placeholder={text.directionPlaceholder}
              />
            </label>
            <label>
              <span className="field-label">
                <span>{text.goals}</span>
                <span className="required-mark">*</span>
              </span>
              <textarea
                required
                value={projectForm.goals}
                onChange={(event) =>
                  setProjectForm({ ...projectForm, goals: event.target.value })
                }
                placeholder={text.goalsPlaceholder}
              />
            </label>
            <label>
              {text.constraints}
              <textarea
                value={projectForm.constraints_text}
                onChange={(event) =>
                  setProjectForm({ ...projectForm, constraints_text: event.target.value })
                }
                placeholder={text.constraintsPlaceholder}
              />
            </label>
            <div className="split-fields">
              <label>
                {text.computeBudget}
                <input
                  value={projectForm.compute_budget}
                  onChange={(event) =>
                    setProjectForm({ ...projectForm, compute_budget: event.target.value })
                  }
                  placeholder={text.computeBudgetPlaceholder}
                />
              </label>
              <label>
                {text.apiBudget}
                <input
                  value={projectForm.api_budget}
                  onChange={(event) =>
                    setProjectForm({ ...projectForm, api_budget: event.target.value })
                  }
                  placeholder={text.apiBudgetPlaceholder}
                />
              </label>
            </div>
            <button type="submit">{text.createProject}</button>
          </form>

          <section className="panel">
            <div className="panel-header">
              <h2>{text.paperIntake}</h2>
            </div>
            <p className="muted">{text.paperIntakeBody}</p>
            <form className="stacked-form" onSubmit={handleUploadPaper}>
              <label>
                {text.localPdf}
                <input name="paper" type="file" accept=".pdf" />
              </label>
              <label>
                {text.notes}
                <input
                  value={uploadNotes}
                  onChange={(event) => setUploadNotes(event.target.value)}
                  placeholder={text.whyPaper}
                />
              </label>
              <button disabled={!selectedProjectId} type="submit">
                {text.uploadPdf}
              </button>
            </form>
            <form className="stacked-form" onSubmit={handleAddPaperUrl}>
              <label>
                {text.remoteUrl}
                <input
                  value={urlPaper.url}
                  onChange={(event) => setUrlPaper({ ...urlPaper, url: event.target.value })}
                  placeholder={text.remoteUrlPlaceholder}
                />
              </label>
              <label>
                {text.title}
                <input
                  value={urlPaper.title}
                  onChange={(event) => setUrlPaper({ ...urlPaper, title: event.target.value })}
                  placeholder={text.titlePlaceholder}
                />
              </label>
              <label>
                {text.notes}
                <input
                  value={urlPaper.notes}
                  onChange={(event) => setUrlPaper({ ...urlPaper, notes: event.target.value })}
                  placeholder={text.whySource}
                />
              </label>
              <button disabled={!selectedProjectId} type="submit">
                {text.addUrlSource}
              </button>
            </form>
            <div className="paper-list">
              {(projectDetail?.papers ?? []).map((paper) => (
                <article key={paper.id} className="paper-card">
                  <strong>{paper.title}</strong>
                  <span>{paper.source_type}</span>
                  {paper.url ? <a href={paper.url}>{paper.url}</a> : null}
                  {paper.notes ? <p>{paper.notes}</p> : null}
                </article>
              ))}
            </div>
          </section>
        </section>

        <section className="grid two-up">
          <section className="panel">
            <div className="panel-header">
              <h2>{text.planningGate}</h2>
              <div className="inline-actions">
                <button disabled={!selectedProjectId} onClick={handleGeneratePlan} type="button">
                  {text.generatePlan}
                </button>
                <button disabled={!approvalReady} onClick={handleApprovePlan} type="button">
                  {text.approvePlan}
                </button>
                <button disabled={!runReady} onClick={handleStartRun} type="button">
                  {text.startRun}
                </button>
              </div>
            </div>
            <div className="markdown-surface">
              <ReactMarkdown>
                {projectDetail?.plan?.plan_markdown ??
                  text.noPlanYet}
              </ReactMarkdown>
            </div>
          </section>

          <section className="panel">
            <div className="panel-header">
              <h2>{text.runSummary}</h2>
            </div>
            {run ? (
              <div className="run-meta">
                <div>
                  <span className="metric-label">{text.runStatus}</span>
                  <strong>{run.status}</strong>
                </div>
                <div>
                  <span className="metric-label">{text.currentStage}</span>
                  <strong>
                    {run.current_stage_index}/{run.total_stages}
                  </strong>
                </div>
                <div>
                  <span className="metric-label">{text.started}</span>
                  <strong>{new Date(run.started_at).toLocaleString()}</strong>
                </div>
              </div>
            ) : (
              <p className="muted">{text.noRun}</p>
            )}
            <div className="preflight-banner">
              <span>{text.planningGateLabel}</span>
              <strong>{projectDetail?.plan?.status ?? "missing"}</strong>
            </div>
            <p className="muted">{text.reducedPipelineNote}</p>
          </section>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>{text.pipelineStages}</h2>
          </div>
          <StageTimeline
            catalog={localizedStageCatalog}
            locale={locale}
            runStages={runStages}
            currentStage={run?.current_stage_index ?? 0}
            onSelect={setSelectedStageIndex}
            selectedIndex={selectedStageIndex}
          />
        </section>

        <section className="grid detail-grid">
          <section className="panel">
            <div className="panel-header">
              <h2>{text.selectedStageOutput}</h2>
            </div>
            <div className="markdown-surface">
              <ReactMarkdown>
                {selectedStage?.content_md ??
                  text.selectedStagePlaceholder}
              </ReactMarkdown>
            </div>
          </section>

          <section className="panel">
            <div className="panel-header">
              <h2>{text.sourceGroundingSnapshot}</h2>
            </div>
            <div className="snapshot-list">
              {(projectDetail?.papers ?? []).map((paper) => (
                <div key={paper.id} className="snapshot-item">
                  <strong>{paper.title}</strong>
                  <span>{paper.source_type}</span>
                  <p>{paper.extracted_text?.slice(0, 240) || text.noExtractedText}</p>
                </div>
              ))}
            </div>
          </section>
        </section>
        </main>
      </div>
    </div>
  );
}

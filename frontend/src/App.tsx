import { type ReactNode, useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import { StageTimeline } from "./components/StageTimeline";
import {
  api,
  type GroundedPaperResult,
  type LiteratureResult,
  type CitationGraph,
  type Paper,
  type PaperMetadataPayload,
  type Plan,
  type Project,
  type ProjectExecutionPayload,
  type ProjectTemplate,
  type Run,
  type RunAuditEvent,
  type RunStage,
  type RuntimeInfo,
  type Settings,
  type StageCatalogItem,
} from "./lib/api";

type ThemeMode = "light" | "dark";
type LocaleMode = "en" | "cn";

type NotificationEntry = {
  id: string;
  title: string;
  body: string;
  createdAt: number;
  kind: "plan_ready" | "approval_needed" | "run_complete" | "run_failed";
};

const activeRunStatuses = new Set(["queued", "running", "paused", "awaiting_approval"]);

const stageLocaleCopy: Record<
  LocaleMode,
  Record<string, { label: string; summary: string; owner: string }>
> = {
  en: {},
  cn: {
    scope_alignment: {
      label: "范围对齐",
      summary: "先把研究边界、非目标和验收标准收紧，再做后续扩展。",
      owner: "研究策略 Agent",
    },
    source_grounding: {
      label: "来源 Grounding",
      summary: "规范化用户提供的论文来源，并补齐可用的证据上下文。",
      owner: "论文输入 Agent",
    },
    literature_retrieval: {
      label: "文献检索",
      summary: "通过 OpenAlex、Semantic Scholar、Crossref、arXiv 扩展论文覆盖面。",
      owner: "检索 Mesh",
    },
    literature_map: {
      label: "文献地图",
      summary: "整理主题簇、基线方法和未解决问题。",
      owner: "文献分析 Agent",
    },
    synthesis: {
      label: "综合归纳",
      summary: "把证据整理成可验证的假设、前提和下注方向。",
      owner: "综合分析 Agent",
    },
    experiment_design: {
      label: "实验设计",
      summary: "定义实验矩阵、指标、消融和成功标准，并在门控处等待批准。",
      owner: "实验设计 Agent",
    },
    code_prototype: {
      label: "代码原型",
      summary: "把实验设计转成可执行的模块计划、依赖和清单。",
      owner: "Codex 构建 Agent",
    },
    experiment_sandbox: {
      label: "实验沙箱",
      summary: "在 Docker 中执行仓库感知的准备命令与 benchmark 命令，启用超时、依赖白名单和产物采集。",
      owner: "Sandbox Runner",
    },
    execution_review: {
      label: "执行评审",
      summary: "基于真实沙箱结果评估可行性、故障和修复路径。",
      owner: "执行评审 Agent",
    },
    paper_outline: {
      label: "论文提纲",
      summary: "先生成结构化提纲、贡献映射和图表计划。",
      owner: "论文架构 Agent",
    },
    paper_drafting: {
      label: "论文起草",
      summary: "根据提纲和证据撰写初稿章节。",
      owner: "论文写作 Agent",
    },
    paper_revision: {
      label: "论文修订",
      summary: "收紧措辞、解决薄弱论断，并在门控处等待批准。",
      owner: "修订编辑 Agent",
    },
    paper_export: {
      label: "论文导出",
      summary: "生成真实的 Markdown / LaTeX / BibTeX / PDF 导出文件，并附带校验报告。",
      owner: "导出管理 Agent",
    },
    peer_review: {
      label: "同行评审",
      summary: "按不同 venue rubric 评审稿件，并输出高优先级修改建议。",
      owner: "评审小组",
    },
    delivery_package: {
      label: "交付包",
      summary: "打包最终稿件、校验报告、评审结果和可下载交付归档。",
      owner: "交付管理 Agent",
    },
  },
};

const uiCopy = {
  en: {
    ready: "Ready.",
    brandTitle: "Plan-gated research GUI with retrieval, sandboxing, and approval loops.",
    brandBody:
      "Start from an idea, ground it with papers, approve the plan, and control staged execution in one place.",
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
    heroTitle: "Require idea, direction, must-read papers, and explicit approvals before the run moves forward.",
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
    executionConfig: "Execution Sandbox",
    executionConfigBody:
      "Point the sandbox at a local repo path or a git URL, then provide the setup and run commands. Local path takes priority when both are set.",
    repoPath: "Local Repo Path",
    repoPathPlaceholder: "~/code/my-benchmark or ../repo",
    repoUrl: "Git Repo URL",
    repoUrlPlaceholder: "https://github.com/org/repo.git",
    repoRef: "Git Ref",
    repoRefPlaceholder: "main / tag / commit",
    sandboxWorkdir: "Sandbox Workdir",
    sandboxWorkdirPlaceholder: "relative/path inside the repo",
    setupCommand: "Setup Command",
    setupCommandPlaceholder:
      "python -m venv .venv && .venv/bin/pip install -r requirements.txt",
    runCommand: "Run Command",
    runCommandPlaceholder: "pytest -q / python train.py / make benchmark",
    expectedArtifacts: "Expected Artifacts",
    expectedArtifactsPlaceholder: "One glob per line, for example:\nresults/**/*.json\noutputs/*.csv",
    saveExecutionConfig: "Save Execution Config",
    paperIntake: "Paper Intake",
    paperIntakeBody:
      "Add local PDFs, remote URLs, or import results from live literature search before generating the plan.",
    localPdf: "Local PDF",
    uploadPdf: "Upload PDF",
    remoteUrl: "Remote URL",
    title: "Title",
    titlePlaceholder: "Optional title override",
    whyPaper: "Why this paper matters",
    whySource: "Why this source should shape the plan",
    remoteUrlPlaceholder: "arXiv / DOI / PDF / paper page",
    addUrlSource: "Add URL Source",
    literatureSearch: "Literature Discovery",
    literatureSearchPlaceholder: "Search topic / method / task keywords",
    search: "Search",
    importResult: "Import",
    noLiteratureResults: "No literature results yet.",
    providerErrors: "Provider Errors",
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
      "The workflow now includes live retrieval adapters, a Docker sandbox, manuscript sub-pipelines, and stage approval gates.",
    pipelineStages: "Current Stage Plan",
    selectedStageOutput: "Selected Stage Output",
    selectedStagePlaceholder:
      "Run the pipeline to populate stage output. Click any stage card to inspect its content.",
    sourceGroundingSnapshot: "Source Snapshot",
    noExtractedText: "No extracted text yet.",
    white: "White",
    black: "Black",
    en: "EN",
    cn: "CN",
    settingsSaved: "Settings saved.",
    projectCreated: "Project created.",
    executionConfigSaved: "Execution config saved.",
    localPaperAdded: "Local paper added.",
    remotePaperAdded: "Remote paper added.",
    literatureImported: "Literature result imported.",
    planGenerated: "Plan generated. Review before starting.",
    planApproved: "Plan approved.",
    runStarted: "Run started.",
    runPaused: "Run paused.",
    runResumed: "Run resumed.",
    gateRejected: "Approval gate rejected.",
    rollbackComplete: "Run rolled back to the selected gate target.",
    wsConnected: "Live stage updates connected.",
    wsDisconnected: "Live updates disconnected.",
    copyLanUrl: "Copy LAN URL",
    lanUrlCopied: "LAN URL copied.",
    lanUrlCopyFailed: "LAN URL copy failed.",
    pauseRun: "Pause",
    resumeRun: "Resume / Approve Gate",
    rejectGate: "Reject Gate",
    rollbackGate: "Rollback",
    activeGate: "Active Gate",
    noActiveGate: "No active approval gate.",
    stageContract: "Stage Contract",
    stageFocus: "Stage Focus",
    inputs: "Inputs",
    mustProduce: "Must Produce",
    qualityBar: "Quality Bar",
    disallowed: "Disallowed",
    artifactSchema: "Artifact Schema",
    artifactSnapshot: "Artifact Snapshot",
    gateState: "Gate State",
    stageNotes: "Stage Notes",
    retrievedVia: "Retrieved via",
    citationKey: "Citation key",
    doiLabel: "DOI",
    groundedRetrieval: "Paper-grounded Retrieval",
    groundedRetrievalPlaceholder: "Search within attached papers and imported chunks",
    groundedSearch: "Search Papers",
    groundedStrategy: "Retrieval strategy",
    noGroundedResults: "No grounded snippets yet.",
    chunkCount: "Chunks",
    openPdf: "Open PDF",
    preview: "Preview",
    approvalAudit: "Approval Audit Trail",
    approvalAuditEmpty: "No pause, reject, or rollback decisions recorded yet.",
    auditAction: "Action",
    auditStage: "Stage",
    auditDecidedBy: "Decided by",
    auditComment: "Comment",
    auditTime: "Time",
    auditDecidedByMissing: "(unspecified)",
    auditCommentMissing: "(no comment)",
    commentPrompt: (action: string) =>
      `Optional comment for "${action}" (leave blank to record without notes):`,
    decidedByPrompt: "Optional decider name or handle (leave blank to skip):",
    gateDecisionLabel: "Gate decision",
    validationReport: "Validation Report",
    validationStatusOk: "Passed",
    validationStatusFailed: "Failed",
    validationErrors: "Errors",
    validationWarnings: "Warnings",
    validationMarkdown: "Markdown structure",
    validationSchema: "Artifact schema",
    validationSemantic: "Semantic checks",
    validationMissingHeadings: "Missing headings",
    validationOrderedHeadings: "Required headings present",
    validationRequiredKeys: "Required artifact keys",
    validationUnexpectedKeys: "Unexpected artifact keys",
    validationMustProduceCoverage: "Must-produce coverage",
    validationDisallowedFindings: "Disallowed clause matches",
    validationListSize: "List size",
    validationCovered: "covered",
    validationUncovered: "uncovered",
    validationTriggered: "triggered",
    validationOk: "ok",
    validationNoData: "No validation report yet — run this stage first.",
    validationToggleShow: "Show validation",
    validationToggleHide: "Hide validation",
    paperEdit: "Edit metadata",
    paperEditCancel: "Cancel",
    paperEditSave: "Save",
    paperRefresh: "Refresh from providers",
    paperDelete: "Remove",
    paperDeleteConfirm: "Remove this paper from the project? This also drops its chunks.",
    paperEditTitle: "Title",
    paperEditAuthors: "Authors",
    paperEditAuthorsHint: "One per line, or separated by ;",
    paperEditYear: "Year",
    paperEditVenue: "Venue",
    paperEditDoi: "DOI",
    paperEditUrl: "URL",
    paperEditAbstract: "Abstract",
    paperEditNotes: "Notes",
    paperEditCitationKey: "Citation key",
    paperUpdateSaved: "Paper metadata updated.",
    paperRefreshSaved: "Paper metadata refreshed.",
    paperDeletedMessage: "Paper removed.",
    paperEditError: "Could not save metadata.",
    paperRefreshNoData: "No additional metadata returned by providers.",
    paperLastEdited: "Last edits",
    paperLastRefresh: "Last refresh",
    paperRunOcr: "Run OCR",
    paperOcrSuccess: "OCR recovered text from the PDF.",
    paperOcrSkipped: "OCR could not recover text — see metadata for missing dependencies.",
    paperOcrUnavailable: "OCR is unavailable: install the optional pytesseract + tesseract dependencies.",
    paperOcrSummary: "OCR",
    retryStage: "Retry stage",
    retryStageDisabled: "Stage cannot be retried while the run is busy.",
    retryQueued: "Stage retry queued.",
    retryAttempts: "Attempts",
    costSummary: "Cost & Usage",
    costTotalSpend: "Estimated spend",
    costTotalTokens: "Total tokens",
    costPerModel: "Per model",
    costPerStage: "Per stage",
    costNoUsage: "No model usage recorded yet.",
    costUsageDisclaimer: "Estimate uses approximate per-million rates; verify with your provider.",
    projectTemplates: "Project Templates",
    projectTemplatesHint: "Pick a research mode to pre-fill the form. You can still tweak any field before creating the project.",
    templateNone: "Custom (no template)",
    templateAppliedPrefix: "Template applied:",
    projectSearchPlaceholder: "Search projects by title, idea, direction…",
    projectIncludeArchived: "Show archived",
    projectsEmpty: "No projects match the current filters.",
    projectArchivedLabel: "archived",
    projectDuplicatedLabel: "copy",
    projectDuplicate: "Duplicate project",
    projectArchive: "Archive project",
    projectUnarchive: "Restore project",
    projectDelete: "Delete project (irreversible)",
    projectDuplicatedMessage: "Project duplicated.",
    projectArchivedMessage: "Project archived.",
    projectUnarchivedMessage: "Project restored.",
    projectDeletedMessage: "Project deleted.",
    projectDeleteConfirm: "Delete project \"{title}\" and all its papers / runs? This cannot be undone.",
    notifications: "Notifications",
    notificationsEnable: "Enable desktop notifications",
    notificationsEnabled: "Desktop notifications enabled",
    notificationsBlocked: "Browser blocked desktop notifications",
    notificationsUnsupported: "Browser does not support notifications",
    notificationsClear: "Clear",
    notificationsEmpty: "No new notifications.",
    notificationPlanReadyTitle: "Plan ready for review",
    notificationApprovalNeededTitle: "Approval needed",
    notificationRunCompleteTitle: "Run complete",
    notificationRunFailedTitle: "Run failed",
    sandboxAdvanced: "Advanced sandbox options",
    sandboxAdvancedHint:
      "Override the runtime image, extra Python or apt packages, and a custom pip index. Set max attempts to 2-3 to retry transient sandbox failures.",
    sandboxBaseImage: "Base image",
    sandboxBaseImagePlaceholder: "python:3.11-slim (default)",
    sandboxExtraPackages: "Extra Python packages",
    sandboxExtraPackagesPlaceholder:
      "One package per line, e.g.\ntorch\ntransformers",
    sandboxAptPackages: "Extra apt packages",
    sandboxAptPackagesPlaceholder:
      "One package per line, e.g.\nbuild-essential\nffmpeg",
    sandboxPipIndex: "Custom pip index URL",
    sandboxPipIndexPlaceholder: "https://pypi.org/simple",
    sandboxTimeoutSeconds: "Timeout (seconds)",
    sandboxTimeoutPlaceholder: "300",
    sandboxMaxAttempts: "Max sandbox attempts",
    sandboxMaxAttemptsPlaceholder: "1",
    citationGraph: "Citation Graph",
    citationGraphRefresh: "Refresh",
    citationGraphPapers: "Papers",
    citationGraphInternal: "Internal links",
    citationGraphExternal: "External references",
    citationGraphUnresolved: "Unresolved",
    citationGraphEmpty: "No citation links extracted yet — add or refresh papers with extracted text or DOIs.",
    citationGraphReferences: "References",
    citationGraphCitedBy: "Cited by",
    citationGraphError: "Failed to load citation graph:",
    reindexIncremental: "Re-index (changed only)",
    reindexFull: "Force full re-index",
    reindexResult:
      "Indexed {indexed} papers, skipped {skipped} unchanged, {embedded} embedded out of {total}.",
    reindexError: "Re-index failed:",
  },
  cn: {
    ready: "已就绪。",
    brandTitle: "带前置计划审批、真实检索、沙箱执行和审批回路的研究工作流 GUI。",
    brandBody: "从 idea 出发，用论文做 grounding，先审批计划，再在同一个界面里控制整条分阶段执行链路。",
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
    heroTitle: "先提供 idea、方向和必读论文，再经过计划审批与前置计划审批，运行才会继续推进。",
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
    executionConfig: "执行沙箱配置",
    executionConfigBody:
      "给沙箱配置本地仓库路径或 git URL，再填写准备命令和运行命令。如果两者都填写，优先使用本地路径。",
    repoPath: "本地仓库路径",
    repoPathPlaceholder: "~/code/my-benchmark 或 ../repo",
    repoUrl: "Git 仓库 URL",
    repoUrlPlaceholder: "https://github.com/org/repo.git",
    repoRef: "Git 引用",
    repoRefPlaceholder: "main / tag / commit",
    sandboxWorkdir: "沙箱工作目录",
    sandboxWorkdirPlaceholder: "仓库内相对路径",
    setupCommand: "准备命令",
    setupCommandPlaceholder:
      "python -m venv .venv && .venv/bin/pip install -r requirements.txt",
    runCommand: "运行命令",
    runCommandPlaceholder: "pytest -q / python train.py / make benchmark",
    expectedArtifacts: "期望产物",
    expectedArtifactsPlaceholder: "每行一个 glob，例如：\nresults/**/*.json\noutputs/*.csv",
    saveExecutionConfig: "保存执行配置",
    paperIntake: "论文输入",
    paperIntakeBody:
      "在生成计划前，可以添加本地 PDF、远程 URL，或从实时文献检索结果中直接导入。",
    localPdf: "本地 PDF",
    uploadPdf: "上传 PDF",
    remoteUrl: "远程 URL",
    title: "标题",
    titlePlaceholder: "可选标题覆盖",
    whyPaper: "这篇论文为何重要",
    whySource: "这个来源为什么会影响计划",
    remoteUrlPlaceholder: "arXiv / DOI / PDF / 论文页面",
    addUrlSource: "添加 URL 来源",
    literatureSearch: "文献发现",
    literatureSearchPlaceholder: "输入任务 / 方法 / 主题关键词",
    search: "检索",
    importResult: "导入",
    noLiteratureResults: "还没有检索结果。",
    providerErrors: "Provider 错误",
    planningGate: "前置计划审批",
    generatePlan: "生成计划",
    approvePlan: "批准计划",
    startRun: "启动运行",
    noPlanYet: "还没有计划。先创建项目、添加论文，然后生成计划。",
    runSummary: "运行概览",
    noRun: "还没有启动运行。",
    runStatus: "运行状态",
    currentStage: "当前阶段",
    started: "开始时间",
    planningGateLabel: "前置计划审批",
    reducedPipelineNote:
      "当前流水线已经包含真实文献检索适配器、Docker 实验沙箱、论文子流水线，以及可暂停/恢复/拒绝/回滚的审批门。",
    pipelineStages: "当前阶段规划",
    selectedStageOutput: "当前阶段输出",
    selectedStagePlaceholder: "运行后这里会出现阶段输出。点击任意阶段卡片即可查看内容。",
    sourceGroundingSnapshot: "来源快照",
    noExtractedText: "还没有提取文本。",
    white: "白色",
    black: "黑色",
    en: "EN",
    cn: "CN",
    settingsSaved: "设置已保存。",
    projectCreated: "项目已创建。",
    executionConfigSaved: "执行配置已保存。",
    localPaperAdded: "本地论文已添加。",
    remotePaperAdded: "远程论文已添加。",
    literatureImported: "检索结果已导入。",
    planGenerated: "计划已生成。请先审阅再启动。",
    planApproved: "计划已批准。",
    runStarted: "运行已启动。",
    runPaused: "运行已暂停。",
    runResumed: "运行已恢复。",
    gateRejected: "审批门已拒绝。",
    rollbackComplete: "已回滚到门控指定阶段。",
    wsConnected: "实时阶段更新已连接。",
    wsDisconnected: "实时更新已断开。",
    copyLanUrl: "复制 LAN URL",
    lanUrlCopied: "LAN URL 已复制。",
    lanUrlCopyFailed: "复制 LAN URL 失败。",
    pauseRun: "暂停",
    resumeRun: "恢复 / 通过门控",
    rejectGate: "拒绝门控",
    rollbackGate: "回滚",
    activeGate: "当前审批门",
    noActiveGate: "当前没有活动审批门。",
    stageContract: "阶段合同",
    stageFocus: "阶段焦点",
    inputs: "输入要求",
    mustProduce: "必须产出",
    qualityBar: "质量标准",
    disallowed: "禁止事项",
    artifactSchema: "产物 Schema",
    artifactSnapshot: "产物快照",
    gateState: "门控状态",
    stageNotes: "阶段备注",
    retrievedVia: "检索来源",
    citationKey: "引用键",
    doiLabel: "DOI",
    groundedRetrieval: "论文 Grounded 检索",
    groundedRetrievalPlaceholder: "在已附加论文和已切块内容中检索",
    groundedSearch: "检索论文",
    groundedStrategy: "检索策略",
    noGroundedResults: "还没有 grounded snippet。",
    chunkCount: "分块数",
    openPdf: "打开 PDF",
    preview: "预览",
    approvalAudit: "审批审计记录",
    approvalAuditEmpty: "尚未记录任何暂停、拒绝或回滚决策。",
    auditAction: "动作",
    auditStage: "阶段",
    auditDecidedBy: "决策人",
    auditComment: "备注",
    auditTime: "时间",
    auditDecidedByMissing: "（未填写）",
    auditCommentMissing: "（无备注）",
    commentPrompt: (action: string) =>
      `请输入“${action}”的可选备注（留空表示无备注）:`,
    decidedByPrompt: "可选填写决策人名称（留空跳过）:",
    gateDecisionLabel: "门控决策",
    validationReport: "校验报告",
    validationStatusOk: "通过",
    validationStatusFailed: "未通过",
    validationErrors: "错误",
    validationWarnings: "警告",
    validationMarkdown: "Markdown 结构",
    validationSchema: "产物 Schema",
    validationSemantic: "语义检查",
    validationMissingHeadings: "缺失的标题",
    validationOrderedHeadings: "已包含的必需标题",
    validationRequiredKeys: "必需产物键",
    validationUnexpectedKeys: "未声明的产物键",
    validationMustProduceCoverage: "must-produce 覆盖度",
    validationDisallowedFindings: "禁止条款命中",
    validationListSize: "列表条目数",
    validationCovered: "已覆盖",
    validationUncovered: "未覆盖",
    validationTriggered: "触发",
    validationOk: "正常",
    validationNoData: "还没有校验报告 — 运行该阶段后会出现。",
    validationToggleShow: "展开校验",
    validationToggleHide: "收起校验",
    paperEdit: "编辑元数据",
    paperEditCancel: "取消",
    paperEditSave: "保存",
    paperRefresh: "从 Provider 刷新",
    paperDelete: "删除",
    paperDeleteConfirm: "确认从项目中移除这篇论文？相关分块也会被清理。",
    paperEditTitle: "标题",
    paperEditAuthors: "作者",
    paperEditAuthorsHint: "每行一位，或用 ; 分隔",
    paperEditYear: "年份",
    paperEditVenue: "Venue",
    paperEditDoi: "DOI",
    paperEditUrl: "URL",
    paperEditAbstract: "摘要",
    paperEditNotes: "备注",
    paperEditCitationKey: "Citation key",
    paperUpdateSaved: "论文元数据已更新。",
    paperRefreshSaved: "已从 Provider 刷新元数据。",
    paperDeletedMessage: "论文已移除。",
    paperEditError: "保存元数据失败。",
    paperRefreshNoData: "Provider 没有返回新的元数据。",
    paperLastEdited: "最近一次编辑",
    paperLastRefresh: "最近一次刷新",
    paperRunOcr: "执行 OCR",
    paperOcrSuccess: "OCR 已从 PDF 中恢复文本。",
    paperOcrSkipped: "OCR 未能恢复文本 — 详情见 metadata 中的依赖。",
    paperOcrUnavailable: "OCR 不可用：请安装可选的 pytesseract 与 tesseract 依赖。",
    paperOcrSummary: "OCR 状态",
    retryStage: "重新执行该阶段",
    retryStageDisabled: "运行繁忙时无法重试。",
    retryQueued: "阶段重试已排队。",
    retryAttempts: "尝试次数",
    costSummary: "成本与用量",
    costTotalSpend: "估算花费",
    costTotalTokens: "Token 总量",
    costPerModel: "按模型",
    costPerStage: "按阶段",
    costNoUsage: "暂无模型用量记录。",
    costUsageDisclaimer: "估算基于大致的每百万 Token 价格，请与服务商账单核对。",
    projectTemplates: "项目模板",
    projectTemplatesHint: "选择一种研究模式以预填表单。仍然可以在创建前编辑任何字段。",
    templateNone: "自定义（不使用模板）",
    templateAppliedPrefix: "已应用模板：",
    projectSearchPlaceholder: "按标题、想法、方向等搜索项目…",
    projectIncludeArchived: "显示已归档项目",
    projectsEmpty: "没有匹配当前筛选的项目。",
    projectArchivedLabel: "已归档",
    projectDuplicatedLabel: "副本",
    projectDuplicate: "复制项目",
    projectArchive: "归档项目",
    projectUnarchive: "恢复项目",
    projectDelete: "删除项目（不可恢复）",
    projectDuplicatedMessage: "项目已复制。",
    projectArchivedMessage: "项目已归档。",
    projectUnarchivedMessage: "项目已恢复。",
    projectDeletedMessage: "项目已删除。",
    projectDeleteConfirm: "确认删除项目 “{title}” 及其所有论文/运行？此操作不可恢复。",
    notifications: "通知",
    notificationsEnable: "启用桌面通知",
    notificationsEnabled: "桌面通知已启用",
    notificationsBlocked: "浏览器已禁止桌面通知",
    notificationsUnsupported: "浏览器不支持通知",
    notificationsClear: "清空",
    notificationsEmpty: "暂无新通知。",
    notificationPlanReadyTitle: "计划已可审阅",
    notificationApprovalNeededTitle: "需要审批",
    notificationRunCompleteTitle: "运行已完成",
    notificationRunFailedTitle: "运行失败",
    sandboxAdvanced: "高级沙箱选项",
    sandboxAdvancedHint:
      "可自定义运行时镜像、额外 Python / apt 包，以及私有 pip index。最大尝试次数 2-3 用于重试临时性沙箱失败。",
    sandboxBaseImage: "基础镜像",
    sandboxBaseImagePlaceholder: "python:3.11-slim（默认）",
    sandboxExtraPackages: "额外 Python 包",
    sandboxExtraPackagesPlaceholder: "每行一个包，如：\ntorch\ntransformers",
    sandboxAptPackages: "额外 apt 包",
    sandboxAptPackagesPlaceholder: "每行一个包，如：\nbuild-essential\nffmpeg",
    sandboxPipIndex: "自定义 pip index URL",
    sandboxPipIndexPlaceholder: "https://pypi.org/simple",
    sandboxTimeoutSeconds: "超时秒数",
    sandboxTimeoutPlaceholder: "300",
    sandboxMaxAttempts: "沙箱最大尝试次数",
    sandboxMaxAttemptsPlaceholder: "1",
    citationGraph: "引用图",
    citationGraphRefresh: "刷新",
    citationGraphPapers: "论文",
    citationGraphInternal: "内部链接",
    citationGraphExternal: "外部引用",
    citationGraphUnresolved: "未解析",
    citationGraphEmpty: "暂未提取出引用关系 — 可补充 DOI 或重新解析论文文本。",
    citationGraphReferences: "引用",
    citationGraphCitedBy: "被引用",
    citationGraphError: "无法加载引用图：",
    reindexIncremental: "增量重建索引",
    reindexFull: "强制完整重建",
    reindexResult: "已重建 {indexed} 篇，跳过未变化 {skipped} 篇，共 {embedded}/{total} 篇有 embedding。",
    reindexError: "重建索引失败：",
  },
} satisfies Record<
  LocaleMode,
  Record<string, string | ((count: number) => string) | ((action: string) => string)>
>;

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

const emptyExecutionForm = {
  repo_path: "",
  repo_url: "",
  repo_ref: "",
  sandbox_workdir: "",
  sandbox_setup_command: "",
  sandbox_run_command: "",
  expected_artifacts_text: "",
  sandbox_base_image: "",
  sandbox_extra_packages_text: "",
  sandbox_apt_packages_text: "",
  sandbox_pip_index_url: "",
  sandbox_timeout_seconds: "",
  sandbox_max_attempts: "",
};

type ProjectDetail = {
  project: Project;
  papers: Paper[];
  plan: Plan | null;
  latest_run: Run | null;
};

function parseExpectedArtifacts(value: string): string[] {
  return value
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function projectToExecutionForm(project: Project | null) {
  if (!project) {
    return emptyExecutionForm;
  }
  return {
    repo_path: project.repo_path || "",
    repo_url: project.repo_url || "",
    repo_ref: project.repo_ref || "",
    sandbox_workdir: project.sandbox_workdir || "",
    sandbox_setup_command: project.sandbox_setup_command || "",
    sandbox_run_command: project.sandbox_run_command || "",
    expected_artifacts_text: (project.expected_artifacts || []).join("\n"),
    sandbox_base_image: project.sandbox_base_image || "",
    sandbox_extra_packages_text: (project.sandbox_extra_packages || []).join("\n"),
    sandbox_apt_packages_text: (project.sandbox_apt_packages || []).join("\n"),
    sandbox_pip_index_url: project.sandbox_pip_index_url || "",
    sandbox_timeout_seconds:
      project.sandbox_timeout_seconds && project.sandbox_timeout_seconds > 0
        ? String(project.sandbox_timeout_seconds)
        : "",
    sandbox_max_attempts:
      project.sandbox_max_attempts && project.sandbox_max_attempts > 0
        ? String(project.sandbox_max_attempts)
        : "",
  };
}

function executionPayloadFromForm(form: typeof emptyExecutionForm): ProjectExecutionPayload {
  return {
    repo_path: form.repo_path.trim(),
    repo_url: form.repo_url.trim(),
    repo_ref: form.repo_ref.trim(),
    sandbox_workdir: form.sandbox_workdir.trim(),
    sandbox_setup_command: form.sandbox_setup_command.trim(),
    sandbox_run_command: form.sandbox_run_command.trim(),
    expected_artifacts: parseExpectedArtifacts(form.expected_artifacts_text),
    sandbox_base_image: form.sandbox_base_image.trim(),
    sandbox_extra_packages: parseExpectedArtifacts(form.sandbox_extra_packages_text),
    sandbox_apt_packages: parseExpectedArtifacts(form.sandbox_apt_packages_text),
    sandbox_pip_index_url: form.sandbox_pip_index_url.trim(),
    sandbox_timeout_seconds: form.sandbox_timeout_seconds
      ? Math.max(0, Number(form.sandbox_timeout_seconds) || 0)
      : 0,
    sandbox_max_attempts: form.sandbox_max_attempts
      ? Math.max(0, Number(form.sandbox_max_attempts) || 0)
      : 0,
  };
}

function prettyJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
}

type ValidationReport = {
  ok: boolean;
  errors: string[];
  warnings: string[];
  contract: {
    inputs_count: number;
    must_produce_count: number;
    quality_bar_count: number;
    disallowed_count: number;
    required_headings: string[];
  };
  markdown: {
    required: string[];
    present: string[];
    title_heading_present: boolean;
  };
  artifact_schema: {
    required_keys: string[];
    validated_keys: string[];
    unexpected_keys: string[];
  };
  semantic?: {
    must_produce_coverage: Array<{
      expectation: string;
      matched_tokens: string[];
      required_match_count?: number;
      covered: boolean;
    }>;
    disallowed_findings: Array<{
      clause: string;
      matched_tokens: string[];
      trigger_threshold: number;
      triggered: boolean;
    }>;
    list_size_findings: Array<{ key: string; count: number; minimum: number }>;
    uncovered_count: number;
    disallowed_triggered_count: number;
  };
};

type ValidationCopy = {
  validationReport: string;
  validationStatusOk: string;
  validationStatusFailed: string;
  validationErrors: string;
  validationWarnings: string;
  validationMarkdown: string;
  validationSchema: string;
  validationSemantic: string;
  validationMissingHeadings: string;
  validationOrderedHeadings: string;
  validationRequiredKeys: string;
  validationUnexpectedKeys: string;
  validationMustProduceCoverage: string;
  validationDisallowedFindings: string;
  validationListSize: string;
  validationCovered: string;
  validationUncovered: string;
  validationTriggered: string;
  validationOk: string;
  validationNoData: string;
  validationToggleShow: string;
  validationToggleHide: string;
};

type PaperCardCopy = {
  preview: string;
  doiLabel: string;
  chunkCount: string;
  openPdf: string;
  paperEdit: string;
  paperEditCancel: string;
  paperEditSave: string;
  paperRefresh: string;
  paperDelete: string;
  paperDeleteConfirm: string;
  paperEditTitle: string;
  paperEditAuthors: string;
  paperEditAuthorsHint: string;
  paperEditYear: string;
  paperEditVenue: string;
  paperEditDoi: string;
  paperEditUrl: string;
  paperEditAbstract: string;
  paperEditNotes: string;
  paperEditCitationKey: string;
  paperLastEdited: string;
  paperLastRefresh: string;
  paperRunOcr: string;
  paperOcrSummary: string;
};

type StageAttemptCopy = {
  retryAttempts: string;
};

type TemplatePickerCopy = {
  projectTemplates: string;
  projectTemplatesHint: string;
  templateNone: string;
};

type NotificationsCopy = {
  notifications: string;
  notificationsEnable: string;
  notificationsEnabled: string;
  notificationsBlocked: string;
  notificationsUnsupported: string;
  notificationsClear: string;
  notificationsEmpty: string;
};

type CitationGraphCopy = {
  citationGraph: string;
  citationGraphRefresh: string;
  citationGraphPapers: string;
  citationGraphInternal: string;
  citationGraphExternal: string;
  citationGraphUnresolved: string;
  citationGraphEmpty: string;
  citationGraphReferences: string;
  citationGraphCitedBy: string;
};

function CitationGraphPanel({
  graph,
  text,
  onRefresh,
}: {
  graph: CitationGraph | null;
  text: CitationGraphCopy;
  onRefresh: () => void;
}) {
  const summary = graph?.summary;
  const papers = graph?.nodes.filter((node) => node.kind === "paper") ?? [];
  const edgesByPaper = (() => {
    const map = new Map<string, { outgoing: typeof graph.edges; incoming: typeof graph.edges }>();
    for (const node of papers) {
      map.set(node.id, { outgoing: [], incoming: [] });
    }
    if (!graph) {
      return map;
    }
    for (const edge of graph.edges) {
      const out = map.get(edge.source);
      if (out) {
        out.outgoing.push(edge);
      }
      const inc = map.get(edge.target);
      if (inc) {
        inc.incoming.push(edge);
      }
    }
    return map;
  })();
  return (
    <div className="citation-panel">
      <div className="citation-panel-head">
        <h3>{text.citationGraph}</h3>
        <button type="button" className="secondary" onClick={onRefresh}>
          {text.citationGraphRefresh}
        </button>
      </div>
      {!graph || papers.length === 0 ? (
        <p className="muted">{text.citationGraphEmpty}</p>
      ) : (
        <>
          <div className="citation-summary">
            <span>
              {text.citationGraphPapers}: {summary?.papers ?? 0}
            </span>
            <span>
              {text.citationGraphInternal}: {summary?.internal_links ?? 0}
            </span>
            <span>
              {text.citationGraphExternal}: {summary?.external_references ?? 0}
            </span>
            <span>
              {text.citationGraphUnresolved}: {summary?.unresolved_links ?? 0}
            </span>
          </div>
          <ul className="citation-list">
            {papers.map((paper) => {
              const buckets = edgesByPaper.get(paper.id);
              return (
                <li key={paper.id}>
                  <strong>{paper.label}</strong>
                  <span className="muted">{paper.citation_key || paper.doi || ""}</span>
                  <div className="citation-edges">
                    <span>
                      {text.citationGraphReferences}:{" "}
                      {(buckets?.outgoing ?? []).length === 0
                        ? "—"
                        : (buckets?.outgoing ?? [])
                            .map((edge) => edge.target.replace("paper:", "").replace("external:", ""))
                            .join(", ")}
                    </span>
                    <span>
                      {text.citationGraphCitedBy}:{" "}
                      {(buckets?.incoming ?? []).length === 0
                        ? "—"
                        : (buckets?.incoming ?? [])
                            .map((edge) => edge.source.replace("paper:", ""))
                            .join(", ")}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}

function NotificationsTray({
  notifications,
  permission,
  text,
  onEnable,
  onClear,
}: {
  notifications: NotificationEntry[];
  permission: NotificationPermission | "unsupported";
  text: NotificationsCopy;
  onEnable: () => void;
  onClear: () => void;
}) {
  const [open, setOpen] = useState(false);
  const unread = notifications.length;
  return (
    <div className={`notifications-tray ${open ? "is-open" : ""}`}>
      <button
        type="button"
        className={`notifications-toggle ${unread > 0 ? "has-new" : ""}`}
        onClick={() => setOpen((current) => !current)}
        aria-label={text.notifications}
      >
        🔔 {unread > 0 ? unread : ""}
      </button>
      {open ? (
        <div className="notifications-popover">
          <div className="notifications-head">
            <strong>{text.notifications}</strong>
            <div className="notifications-actions">
              {permission === "granted" ? (
                <span className="muted">{text.notificationsEnabled}</span>
              ) : permission === "denied" ? (
                <span className="muted">{text.notificationsBlocked}</span>
              ) : permission === "unsupported" ? (
                <span className="muted">{text.notificationsUnsupported}</span>
              ) : (
                <button type="button" onClick={onEnable}>
                  {text.notificationsEnable}
                </button>
              )}
              <button type="button" onClick={onClear} disabled={unread === 0}>
                {text.notificationsClear}
              </button>
            </div>
          </div>
          {unread === 0 ? (
            <p className="muted">{text.notificationsEmpty}</p>
          ) : (
            <ul className="notifications-list">
              {notifications.map((entry) => (
                <li key={entry.id} className={`notification-${entry.kind}`}>
                  <strong>{entry.title}</strong>
                  <span>{entry.body}</span>
                  <time>{new Date(entry.createdAt).toLocaleTimeString()}</time>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}

function ProjectTemplatePicker({
  templates,
  selectedKey,
  text,
  onSelect,
}: {
  templates: ProjectTemplate[];
  selectedKey: string;
  text: TemplatePickerCopy;
  onSelect: (key: string) => void;
}) {
  if (!templates.length) {
    return null;
  }
  return (
    <div className="template-picker">
      <strong>{text.projectTemplates}</strong>
      <p className="muted template-hint">{text.projectTemplatesHint}</p>
      <div className="template-options">
        <button
          type="button"
          className={`template-option ${selectedKey ? "" : "is-active"}`}
          onClick={() => onSelect("")}
        >
          {text.templateNone}
        </button>
        {templates.map((template) => (
          <button
            key={template.key}
            type="button"
            className={`template-option ${selectedKey === template.key ? "is-active" : ""}`}
            onClick={() => onSelect(template.key)}
          >
            <strong>{template.label}</strong>
            <span className="muted">{template.summary}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

type CostSummaryCopy = {
  costSummary: string;
  costTotalSpend: string;
  costTotalTokens: string;
  costPerModel: string;
  costPerStage: string;
  costNoUsage: string;
  costUsageDisclaimer: string;
};

function formatTokens(value: number): string {
  if (!Number.isFinite(value) || value === 0) {
    return "0";
  }
  if (value < 1000) {
    return value.toString();
  }
  if (value < 1_000_000) {
    return `${(value / 1000).toFixed(1)}k`;
  }
  return `${(value / 1_000_000).toFixed(2)}M`;
}

function formatCost(value: number): string {
  if (!Number.isFinite(value) || value === 0) {
    return "$0.00";
  }
  if (value < 0.01) {
    return `$${value.toFixed(4)}`;
  }
  return `$${value.toFixed(2)}`;
}

function CostSummaryPanel({ run, text }: { run: Run | null; text: CostSummaryCopy }) {
  const summary = (run?.metadata_json as
    | {
        cost_summary?: {
          totals?: {
            input_tokens?: number;
            output_tokens?: number;
            total_tokens?: number;
            cost_usd?: number;
          };
          per_model?: Record<
            string,
            { input_tokens?: number; output_tokens?: number; cost_usd?: number; calls?: number }
          >;
          per_stage?: Array<{
            stage_index: number;
            stage_key: string;
            model: string;
            total_tokens?: number;
            cost_usd?: number;
          }>;
        };
      }
    | undefined)?.cost_summary;
  const totals = summary?.totals;
  const perModel = summary?.per_model ?? {};
  const perStage = summary?.per_stage ?? [];
  const hasUsage = Boolean(totals && (totals.total_tokens ?? 0) > 0);
  return (
    <div className="cost-panel">
      <h3>{text.costSummary}</h3>
      {!hasUsage ? (
        <p className="muted">{text.costNoUsage}</p>
      ) : (
        <>
          <div className="cost-grid">
            <div>
              <span className="metric-label">{text.costTotalSpend}</span>
              <strong>{formatCost(totals?.cost_usd ?? 0)}</strong>
            </div>
            <div>
              <span className="metric-label">{text.costTotalTokens}</span>
              <strong>{formatTokens(totals?.total_tokens ?? 0)}</strong>
            </div>
          </div>
          {Object.keys(perModel).length ? (
            <details className="cost-details">
              <summary>{text.costPerModel}</summary>
              <ul>
                {Object.entries(perModel).map(([model, info]) => (
                  <li key={`model-${model}`}>
                    <strong>{model}</strong> · {formatCost(info.cost_usd ?? 0)} ·
                    {" "}
                    {formatTokens((info.input_tokens ?? 0) + (info.output_tokens ?? 0))} tokens · {info.calls ?? 0} calls
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
          {perStage.length ? (
            <details className="cost-details">
              <summary>{text.costPerStage}</summary>
              <ul>
                {perStage.map((entry, index) => (
                  <li key={`stage-${entry.stage_index}-${index}`}>
                    #{entry.stage_index} {entry.stage_key} · {entry.model || "n/a"} ·
                    {" "}
                    {formatTokens(entry.total_tokens ?? 0)} tokens · {formatCost(entry.cost_usd ?? 0)}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </>
      )}
      <p className="muted cost-disclaimer">{text.costUsageDisclaimer}</p>
    </div>
  );
}

function StageAttemptList({
  stage,
  text,
}: {
  stage: RunStage | undefined;
  text: StageAttemptCopy;
}) {
  if (!stage) {
    return null;
  }
  const meta = stage.metadata_json as
    | {
        attempts?: Array<{
          attempt: number;
          status?: string;
          error?: string;
          completed_at?: string;
          started_at?: string;
        }>;
        retry_policy?: { max_attempts?: number };
      }
    | undefined;
  const attempts = meta?.attempts ?? [];
  if (!attempts.length) {
    return null;
  }
  const max = meta?.retry_policy?.max_attempts ?? attempts.length;
  return (
    <div className="stage-attempts">
      <strong>
        {text.retryAttempts}: {attempts.length}/{max}
      </strong>
      <ul>
        {attempts.map((attempt, index) => (
          <li key={`${stage.run_id}-${stage.stage_index}-${attempt.attempt}-${index}`}>
            <span className={`stage-attempt-pill stage-attempt-${attempt.status ?? "pending"}`}>
              #{attempt.attempt} · {attempt.status ?? "pending"}
            </span>
            {attempt.error ? <span className="muted"> · {attempt.error}</span> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function PaperCard({
  paper,
  text,
  onUpdate,
  onRefresh,
  onDelete,
  onRunOcr,
}: {
  paper: Paper;
  text: PaperCardCopy;
  onUpdate: (payload: PaperMetadataPayload) => Promise<void>;
  onRefresh: () => Promise<void>;
  onDelete: () => Promise<void>;
  onRunOcr: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<PaperMetadataPayload>({});

  function startEdit() {
    setDraft({
      title: paper.title,
      authors_json: paper.authors_json.join("\n"),
      year: paper.year || undefined,
      venue: paper.venue,
      doi: paper.doi,
      url: paper.url,
      abstract: paper.abstract,
      notes: paper.notes,
      citation_key: paper.citation_key,
    });
    setEditing(true);
  }

  async function submitEdit() {
    setBusy(true);
    try {
      await onUpdate(draft);
      setEditing(false);
    } finally {
      setBusy(false);
    }
  }

  async function triggerRefresh() {
    setBusy(true);
    try {
      await onRefresh();
    } finally {
      setBusy(false);
    }
  }

  async function triggerDelete() {
    if (typeof window !== "undefined" && !window.confirm(text.paperDeleteConfirm)) {
      return;
    }
    setBusy(true);
    try {
      await onDelete();
    } finally {
      setBusy(false);
    }
  }

  async function triggerOcr() {
    setBusy(true);
    try {
      await onRunOcr();
    } finally {
      setBusy(false);
    }
  }

  const metadataInfo = paper.metadata_json as
    | {
        manual_edits?: Array<{ fields?: string[]; actor?: string }>;
        provider_refreshes?: Array<{ providers?: string[]; errors?: Record<string, string> }>;
        ocr?: {
          status?: string;
          engine?: string;
          pages_processed?: number;
          languages?: string;
          missing_dependencies?: string[];
          recovered_chars?: number;
          triggered_reason?: string;
        };
      }
    | undefined;
  const lastEdit = metadataInfo?.manual_edits?.[metadataInfo.manual_edits.length - 1];
  const lastRefresh = metadataInfo?.provider_refreshes?.[metadataInfo.provider_refreshes.length - 1];
  const ocrInfo = metadataInfo?.ocr;

  return (
    <article className="paper-card">
      {paper.preview_thumbnail_url ? (
        <a href={paper.preview_image_url || paper.preview_thumbnail_url} rel="noreferrer" target="_blank">
          <img
            alt={`${paper.title} ${text.preview}`}
            className="paper-thumb"
            loading="lazy"
            src={paper.preview_thumbnail_url}
          />
        </a>
      ) : null}
      {!editing ? (
        <>
          <strong>{paper.title}</strong>
          <span>{paperSummaryLine(paper)}</span>
          {paper.authors_json.length ? <p>{summarizeAuthors(paper.authors_json)}</p> : null}
          {paper.doi ? (
            <p>
              {text.doiLabel}: {paper.doi}
            </p>
          ) : null}
          <p>
            {text.chunkCount}: {paper.chunk_count} · {paper.retrieval_ready ? "ready" : "pending"}
          </p>
          {paper.url ? (
            <a href={paper.url} rel="noreferrer" target="_blank">
              {paper.url}
            </a>
          ) : null}
          {paper.stored_file_url ? (
            <a href={paper.stored_file_url} rel="noreferrer" target="_blank">
              {text.openPdf}
            </a>
          ) : null}
          {paper.notes ? <p>{paper.notes}</p> : null}
          {lastEdit?.fields?.length ? (
            <p className="muted paper-card-meta-line">
              {text.paperLastEdited}: {lastEdit.fields.join(", ")}
              {lastEdit.actor ? ` · ${lastEdit.actor}` : ""}
            </p>
          ) : null}
          {lastRefresh?.providers?.length ? (
            <p className="muted paper-card-meta-line">
              {text.paperLastRefresh}: {lastRefresh.providers.join(", ")}
            </p>
          ) : null}
          {ocrInfo?.status ? (
            <p className="muted paper-card-meta-line">
              {text.paperOcrSummary}: {ocrInfo.status}
              {ocrInfo.recovered_chars ? ` · ${ocrInfo.recovered_chars} chars` : ""}
              {ocrInfo.missing_dependencies?.length
                ? ` · missing: ${ocrInfo.missing_dependencies.join(", ")}`
                : ""}
            </p>
          ) : null}
          <div className="paper-card-actions">
            <button type="button" className="secondary" onClick={startEdit} disabled={busy}>
              {text.paperEdit}
            </button>
            <button type="button" className="secondary" onClick={triggerRefresh} disabled={busy}>
              {text.paperRefresh}
            </button>
            {paper.stored_file_url ? (
              <button type="button" className="secondary" onClick={triggerOcr} disabled={busy}>
                {text.paperRunOcr}
              </button>
            ) : null}
            <button type="button" className="secondary danger" onClick={triggerDelete} disabled={busy}>
              {text.paperDelete}
            </button>
          </div>
        </>
      ) : (
        <form
          className="paper-edit-form"
          onSubmit={(event) => {
            event.preventDefault();
            void submitEdit();
          }}
        >
          <label>
            {text.paperEditTitle}
            <input
              value={draft.title ?? ""}
              onChange={(event) => setDraft({ ...draft, title: event.target.value })}
            />
          </label>
          <label>
            {text.paperEditAuthors}
            <textarea
              rows={3}
              value={typeof draft.authors_json === "string" ? draft.authors_json : (draft.authors_json ?? []).join("\n")}
              onChange={(event) => setDraft({ ...draft, authors_json: event.target.value })}
              placeholder={text.paperEditAuthorsHint}
            />
          </label>
          <div className="split-fields">
            <label>
              {text.paperEditYear}
              <input
                type="number"
                value={draft.year ?? ""}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    year: event.target.value ? Number(event.target.value) : undefined,
                  })
                }
              />
            </label>
            <label>
              {text.paperEditVenue}
              <input
                value={draft.venue ?? ""}
                onChange={(event) => setDraft({ ...draft, venue: event.target.value })}
              />
            </label>
          </div>
          <div className="split-fields">
            <label>
              {text.paperEditDoi}
              <input
                value={draft.doi ?? ""}
                onChange={(event) => setDraft({ ...draft, doi: event.target.value })}
              />
            </label>
            <label>
              {text.paperEditCitationKey}
              <input
                value={draft.citation_key ?? ""}
                onChange={(event) => setDraft({ ...draft, citation_key: event.target.value })}
              />
            </label>
          </div>
          <label>
            {text.paperEditUrl}
            <input
              value={draft.url ?? ""}
              onChange={(event) => setDraft({ ...draft, url: event.target.value })}
            />
          </label>
          <label>
            {text.paperEditAbstract}
            <textarea
              rows={4}
              value={draft.abstract ?? ""}
              onChange={(event) => setDraft({ ...draft, abstract: event.target.value })}
            />
          </label>
          <label>
            {text.paperEditNotes}
            <textarea
              rows={2}
              value={draft.notes ?? ""}
              onChange={(event) => setDraft({ ...draft, notes: event.target.value })}
            />
          </label>
          <div className="paper-card-actions">
            <button type="submit" disabled={busy}>
              {text.paperEditSave}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => setEditing(false)}
              disabled={busy}
            >
              {text.paperEditCancel}
            </button>
          </div>
        </form>
      )}
    </article>
  );
}

function ValidationReportPanel({
  report,
  text,
}: {
  report: ValidationReport | undefined;
  text: ValidationCopy;
}) {
  const [expanded, setExpanded] = useState(true);
  if (!report) {
    return (
      <div className="detail-block validation-block">
        <h3>{text.validationReport}</h3>
        <p className="muted">{text.validationNoData}</p>
      </div>
    );
  }
  const missingHeadings = report.markdown.required.filter(
    (heading) => !report.markdown.present.includes(heading),
  );
  const semantic = report.semantic;
  return (
    <div className={`detail-block validation-block validation-${report.ok ? "ok" : "failed"}`}>
      <div className="validation-head">
        <h3>{text.validationReport}</h3>
        <span className={`validation-pill validation-pill-${report.ok ? "ok" : "failed"}`}>
          {report.ok ? text.validationStatusOk : text.validationStatusFailed}
        </span>
        <button
          className="validation-toggle"
          type="button"
          onClick={() => setExpanded((current) => !current)}
        >
          {expanded ? text.validationToggleHide : text.validationToggleShow}
        </button>
      </div>
      {expanded ? (
        <div className="validation-body">
          {report.errors.length ? (
            <div className="validation-section validation-section-errors">
              <strong>{text.validationErrors}</strong>
              <ul>
                {report.errors.map((message) => (
                  <li key={`err-${message}`}>{message}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {report.warnings.length ? (
            <div className="validation-section validation-section-warnings">
              <strong>{text.validationWarnings}</strong>
              <ul>
                {report.warnings.map((message) => (
                  <li key={`warn-${message}`}>{message}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className="validation-grid">
            <div>
              <strong>{text.validationMarkdown}</strong>
              <p>
                {text.validationOrderedHeadings}: {report.markdown.present.length}/
                {report.markdown.required.length}
              </p>
              {missingHeadings.length ? (
                <p className="muted">
                  {text.validationMissingHeadings}: {missingHeadings.join(", ")}
                </p>
              ) : null}
            </div>
            <div>
              <strong>{text.validationSchema}</strong>
              <p>
                {text.validationRequiredKeys}: {report.artifact_schema.validated_keys.length}/
                {report.artifact_schema.required_keys.length}
              </p>
              {report.artifact_schema.unexpected_keys.length ? (
                <p className="muted">
                  {text.validationUnexpectedKeys}:{" "}
                  {report.artifact_schema.unexpected_keys.join(", ")}
                </p>
              ) : null}
            </div>
            {semantic ? (
              <div>
                <strong>{text.validationSemantic}</strong>
                <p>
                  {text.validationMustProduceCoverage}:{" "}
                  {semantic.must_produce_coverage.length - semantic.uncovered_count}/
                  {semantic.must_produce_coverage.length} {text.validationCovered}
                </p>
                <p>
                  {text.validationDisallowedFindings}: {semantic.disallowed_triggered_count}{" "}
                  {text.validationTriggered}
                </p>
              </div>
            ) : null}
          </div>
          {semantic && semantic.must_produce_coverage.length ? (
            <details className="validation-details">
              <summary>{text.validationMustProduceCoverage}</summary>
              <ul>
                {semantic.must_produce_coverage.map((entry) => (
                  <li key={`prod-${entry.expectation}`}>
                    <span
                      className={`validation-pill validation-pill-${entry.covered ? "ok" : "failed"}`}
                    >
                      {entry.covered ? text.validationCovered : text.validationUncovered}
                    </span>{" "}
                    {entry.expectation}
                    {entry.matched_tokens.length ? (
                      <span className="muted"> · {entry.matched_tokens.join(", ")}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
          {semantic && semantic.disallowed_findings.length ? (
            <details className="validation-details">
              <summary>{text.validationDisallowedFindings}</summary>
              <ul>
                {semantic.disallowed_findings.map((entry) => (
                  <li key={`disallow-${entry.clause}`}>
                    <span
                      className={`validation-pill validation-pill-${entry.triggered ? "failed" : "ok"}`}
                    >
                      {entry.triggered ? text.validationTriggered : text.validationOk}
                    </span>{" "}
                    {entry.clause}
                    {entry.matched_tokens.length ? (
                      <span className="muted"> · {entry.matched_tokens.join(", ")}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
          {semantic && semantic.list_size_findings.length ? (
            <details className="validation-details">
              <summary>{text.validationListSize}</summary>
              <ul>
                {semantic.list_size_findings.map((entry) => (
                  <li key={`list-${entry.key}`}>
                    {entry.key}: {entry.count}/{entry.minimum}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function summarizeAuthors(authors: string[]) {
  if (!authors.length) {
    return "";
  }
  if (authors.length <= 4) {
    return authors.join(", ");
  }
  return `${authors.slice(0, 4).join(", ")} +${authors.length - 4}`;
}

function paperSummaryLine(paper: Paper) {
  const segments = [paper.source_type];
  if (paper.year) {
    segments.push(String(paper.year));
  }
  if (paper.venue) {
    segments.push(paper.venue);
  }
  if (paper.citation_key) {
    segments.push(paper.citation_key);
  }
  return segments.join(" · ");
}

function formatBytes(value: number) {
  if (!Number.isFinite(value) || value <= 0) {
    return "0 B";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isFileArtifact(value: unknown): value is Record<string, unknown> {
  if (!isRecord(value)) {
    return false;
  }
  return typeof value.path === "string" && typeof value.url === "string";
}

function renderArtifactValue(value: unknown, keyPath = "root"): ReactNode {
  if (isFileArtifact(value)) {
    const label = typeof value.label === "string" ? value.label : "File";
    const kind = typeof value.kind === "string" ? value.kind : "file";
    const sizeBytes = typeof value.size_bytes === "number" ? value.size_bytes : 0;
    const url = typeof value.url === "string" ? value.url : "";
    const path = typeof value.path === "string" ? value.path : "";
    return (
      <div className="artifact-file">
        <strong>{label}</strong>
        <span>
          {kind}
          {sizeBytes ? ` · ${formatBytes(sizeBytes)}` : ""}
        </span>
        {url ? (
          <a href={url} rel="noreferrer" target="_blank">
            {url}
          </a>
        ) : null}
        {path ? <code>{path}</code> : null}
      </div>
    );
  }
  if (Array.isArray(value)) {
    if (!value.length) {
      return <span className="artifact-empty">[]</span>;
    }
    return (
      <div className="artifact-list">
        {value.map((item, index) => (
          <div key={`${keyPath}-${index}`} className="artifact-list-item">
            {renderArtifactValue(item, `${keyPath}-${index}`)}
          </div>
        ))}
      </div>
    );
  }
  if (isRecord(value)) {
    const entries = Object.entries(value);
    if (!entries.length) {
      return <span className="artifact-empty">{`{}`}</span>;
    }
    return (
      <div className="artifact-tree">
        {entries.map(([key, nested]) => (
          <div key={`${keyPath}-${key}`} className="artifact-row">
            <span className="artifact-key">{key}</span>
            <div className="artifact-value">{renderArtifactValue(nested, `${keyPath}-${key}`)}</div>
          </div>
        ))}
      </div>
    );
  }
  if (typeof value === "string") {
    if (value.startsWith("/media/") || value.startsWith("http://") || value.startsWith("https://")) {
      return (
        <a href={value} rel="noreferrer" target="_blank">
          {value}
        </a>
      );
    }
    return <span className="artifact-text">{value || "-"}</span>;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return <span className="artifact-text">{String(value)}</span>;
  }
  return <span className="artifact-empty">null</span>;
}

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
  const [projectTemplates, setProjectTemplates] = useState<ProjectTemplate[]>([]);
  const [selectedTemplateKey, setSelectedTemplateKey] = useState<string>("");
  const [projectForm, setProjectForm] = useState(emptyProjectForm);
  const [executionForm, setExecutionForm] = useState(emptyExecutionForm);
  const [urlPaper, setUrlPaper] = useState({ url: "", title: "", notes: "" });
  const [uploadNotes, setUploadNotes] = useState("");
  const [literatureQuery, setLiteratureQuery] = useState("");
  const [literatureResults, setLiteratureResults] = useState<LiteratureResult[]>([]);
  const [literatureErrors, setLiteratureErrors] = useState<Record<string, string>>({});
  const [groundedQuery, setGroundedQuery] = useState("");
  const [groundedResults, setGroundedResults] = useState<GroundedPaperResult[]>([]);
  const [groundedStrategy, setGroundedStrategy] = useState("");
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [projectDetail, setProjectDetail] = useState<ProjectDetail | null>(null);
  const [projectSearch, setProjectSearch] = useState("");
  const [projectIncludeArchived, setProjectIncludeArchived] = useState(true);
  const [citationGraph, setCitationGraph] = useState<CitationGraph | null>(null);
  const [notifications, setNotifications] = useState<NotificationEntry[]>([]);
  const [notificationPermission, setNotificationPermission] = useState<NotificationPermission | "unsupported">(
    typeof Notification === "undefined" ? "unsupported" : Notification.permission,
  );
  const [run, setRun] = useState<Run | null>(null);
  const [runStages, setRunStages] = useState<RunStage[]>([]);
  const [auditEvents, setAuditEvents] = useState<RunAuditEvent[]>([]);
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
    const [healthResponse, runtimeResponse, stagesResponse, settingsResponse, projectResponse, templatesResponse] =
      await Promise.all([
        api.health(),
        api.getRuntime(),
        api.getStages(),
        api.getSettings(),
        api.listProjects(),
        api.getProjectTemplates(),
      ]);
    setHealth(healthResponse);
    setRuntimeInfo(runtimeResponse);
    setStageCatalog(stagesResponse.stages);
    setSettings(settingsResponse);
    setProjects(projectResponse.projects);
    setProjectTemplates(templatesResponse.templates);
    if (projectResponse.projects[0]) {
      await loadProject(projectResponse.projects[0].id);
    }
  }

  function applyProjectTemplate(key: string) {
    if (!key) {
      setSelectedTemplateKey("");
      return;
    }
    const template = projectTemplates.find((entry) => entry.key === key);
    if (!template) {
      return;
    }
    const defaults = template.defaults;
    setSelectedTemplateKey(key);
    setProjectForm((current) => ({
      ...current,
      title: defaults.title ?? current.title,
      idea: defaults.idea ?? current.idea,
      background: defaults.background ?? current.background,
      direction: defaults.direction ?? current.direction,
      goals: defaults.goals ?? current.goals,
      constraints_text: defaults.constraints_text ?? current.constraints_text,
      compute_budget: defaults.compute_budget ?? current.compute_budget,
      api_budget: defaults.api_budget ?? current.api_budget,
    }));
    setExecutionForm((current) => ({
      ...current,
      sandbox_setup_command: defaults.sandbox_setup_command ?? current.sandbox_setup_command,
      sandbox_run_command: defaults.sandbox_run_command ?? current.sandbox_run_command,
      expected_artifacts_text:
        defaults.expected_artifacts && defaults.expected_artifacts.length
          ? defaults.expected_artifacts.join("\n")
          : current.expected_artifacts_text,
    }));
    setStatusMessage(`${text.templateAppliedPrefix} ${template.label}`);
  }

  async function refreshProjects() {
    const response = await api.listProjects();
    setProjects(response.projects);
  }

  async function handleReindexProject(force: boolean) {
    if (!selectedProjectId) {
      return;
    }
    try {
      const response = await api.reindexProject(selectedProjectId, force);
      const message =
        text.reindexResult.replace("{indexed}", String(response.papers_indexed))
          .replace("{skipped}", String(response.papers_skipped))
          .replace("{embedded}", String(response.embedding_ready))
          .replace("{total}", String(response.papers_total));
      setStatusMessage(message);
      await refreshCitationGraph(selectedProjectId);
    } catch (error) {
      setStatusMessage(`${text.reindexError} ${(error as Error).message ?? ""}`);
    }
  }

  async function refreshCitationGraph(projectId: string | null) {
    if (!projectId) {
      setCitationGraph(null);
      return;
    }
    try {
      const response = await api.getCitationGraph(projectId);
      setCitationGraph(response);
    } catch (error) {
      setStatusMessage(`${text.citationGraphError} ${(error as Error).message ?? ""}`);
    }
  }

  const filteredProjects = useMemo(() => {
    const term = projectSearch.trim().toLowerCase();
    return projects
      .filter((project) => projectIncludeArchived || !project.archived_at)
      .filter((project) => {
        if (!term) {
          return true;
        }
        return [
          project.title,
          project.idea,
          project.direction,
          project.goals,
          project.constraints_text,
        ]
          .join(" ")
          .toLowerCase()
          .includes(term);
      });
  }, [projects, projectSearch, projectIncludeArchived]);

  async function handleDuplicateProject(projectId: string) {
    const response = await api.duplicateProject(projectId);
    setProjects(response.projects);
    setStatusMessage(text.projectDuplicatedMessage);
    await loadProject(response.project.id);
  }

  async function handleToggleArchive(project: Project) {
    const response = project.archived_at
      ? await api.unarchiveProject(project.id)
      : await api.archiveProject(project.id);
    setProjects(response.projects);
    setStatusMessage(project.archived_at ? text.projectUnarchivedMessage : text.projectArchivedMessage);
  }

  async function handleDeleteProject(project: Project) {
    if (typeof window !== "undefined" && !window.confirm(text.projectDeleteConfirm.replace("{title}", project.title))) {
      return;
    }
    const response = await api.deleteProject(project.id);
    setProjects(response.projects);
    if (selectedProjectId === project.id) {
      setProjectDetail(null);
      setSelectedProjectId(response.projects[0]?.id ?? "");
      if (response.projects[0]) {
        await loadProject(response.projects[0].id);
      }
    }
    setStatusMessage(text.projectDeletedMessage);
  }

  async function loadProject(projectId: string) {
    const detail = await api.getProject(projectId);
    setSelectedProjectId(projectId);
    setProjectDetail(detail);
    setGroundedResults([]);
    setGroundedStrategy("");
    setRun(detail.latest_run);
    void refreshCitationGraph(projectId);
    setSelectedStageIndex(detail.latest_run?.current_stage_index || 1);
    if (detail.latest_run) {
      const runDetail = await api.getRun(detail.latest_run.id);
      setRun(runDetail.run);
      setRunStages(runDetail.stages);
      setAuditEvents(runDetail.audit_events ?? []);
      setSelectedStageIndex(runDetail.run.current_stage_index || 1);
    } else {
      setRunStages([]);
      setAuditEvents([]);
      setSelectedStageIndex(1);
    }
    await refreshProjects();
  }

  useEffect(() => {
    if (!run || !activeRunStatuses.has(run.status)) {
      return;
    }
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${window.location.host}/ws/runs/${run.id}`);
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data) as {
        run: Run;
        stages: RunStage[];
        audit_events?: RunAuditEvent[];
      };
      setRun(payload.run);
      setRunStages(payload.stages);
      if (payload.audit_events) {
        setAuditEvents(payload.audit_events);
      }
      setSelectedStageIndex(payload.run.pending_gate_index || payload.run.current_stage_index || 1);
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
  }, [run?.id, run?.status, text.wsConnected, text.wsDisconnected]);

  useEffect(() => {
    setExecutionForm(projectToExecutionForm(projectDetail?.project ?? null));
  }, [projectDetail?.project]);

  function pushNotification(entry: Omit<NotificationEntry, "id" | "createdAt">) {
    const next: NotificationEntry = {
      ...entry,
      id: `notif_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      createdAt: Date.now(),
    };
    setNotifications((current) => [next, ...current].slice(0, 12));
    if (typeof Notification !== "undefined" && Notification.permission === "granted") {
      try {
        new Notification(entry.title, { body: entry.body });
      } catch {
        // ignore — desktop notification failures should not impact UI
      }
    }
  }

  const planStatus = projectDetail?.plan?.status ?? "";
  useEffect(() => {
    if (!projectDetail?.plan) {
      return;
    }
    if (planStatus !== "ready") {
      return;
    }
    pushNotification({
      kind: "plan_ready",
      title: text.notificationPlanReadyTitle,
      body: projectDetail.project.title,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planStatus, projectDetail?.project.id]);

  const runStatus = run?.status ?? "";
  const pendingGate = run?.pending_gate_index ?? 0;
  useEffect(() => {
    if (!run) {
      return;
    }
    if (runStatus === "awaiting_approval" && pendingGate > 0) {
      pushNotification({
        kind: "approval_needed",
        title: text.notificationApprovalNeededTitle,
        body: `${projectDetail?.project.title ?? "Run"} · stage ${pendingGate}`,
      });
    } else if (runStatus === "completed") {
      pushNotification({
        kind: "run_complete",
        title: text.notificationRunCompleteTitle,
        body: projectDetail?.project.title ?? "Run completed",
      });
    } else if (runStatus === "failed") {
      pushNotification({
        kind: "run_failed",
        title: text.notificationRunFailedTitle,
        body: run.error || projectDetail?.project.title || "Run failed",
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runStatus, pendingGate]);

  async function enableNotifications() {
    if (typeof Notification === "undefined") {
      setStatusMessage(text.notificationsUnsupported);
      return;
    }
    if (Notification.permission === "granted") {
      setNotificationPermission("granted");
      setStatusMessage(text.notificationsEnabled);
      return;
    }
    const permission = await Notification.requestPermission();
    setNotificationPermission(permission);
    if (permission === "granted") {
      setStatusMessage(text.notificationsEnabled);
    } else {
      setStatusMessage(text.notificationsBlocked);
    }
  }

  function clearNotifications() {
    setNotifications([]);
  }

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

  const selectedStageDefinition = useMemo(
    () => localizedStageCatalog.find((stage) => stage.index === selectedStageIndex) ?? null,
    [localizedStageCatalog, selectedStageIndex],
  );

  const activeGateStage = useMemo(
    () =>
      localizedStageCatalog.find((stage) => stage.key === run?.pending_gate_key) ??
      localizedStageCatalog.find((stage) => stage.index === run?.pending_gate_index) ??
      null,
    [localizedStageCatalog, run?.pending_gate_index, run?.pending_gate_key],
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
    setProjectForm(emptyProjectForm);
    setStatusMessage(text.projectCreated);
    await loadProject(created.project.id);
  }

  async function handleSaveExecutionConfig(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedProjectId) {
      return;
    }
    const payload = executionPayloadFromForm(executionForm);
    const result = await api.updateProjectExecutionConfig(selectedProjectId, payload);
    setProjectDetail((current) => (current ? { ...current, project: result.project } : current));
    setExecutionForm(projectToExecutionForm(result.project));
    setStatusMessage(text.executionConfigSaved);
    await refreshProjects();
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
    await refreshProjects();
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
    await refreshProjects();
  }

  async function handleSearchLiterature(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedProjectId || !literatureQuery.trim()) {
      return;
    }
    const response = await api.searchLiterature(selectedProjectId, {
      query: literatureQuery,
      limit_per_provider: 3,
    });
    setLiteratureResults(response.results);
    setLiteratureErrors(response.errors);
  }

  async function handleSearchGroundedPapers(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedProjectId || !groundedQuery.trim()) {
      return;
    }
    const response = await api.searchPaperGrounding(selectedProjectId, {
      query: groundedQuery,
      limit: 6,
    });
    setGroundedResults(response.results);
    setGroundedStrategy(response.strategy);
  }

  async function handleUpdatePaperMetadata(paperId: string, payload: PaperMetadataPayload) {
    if (!selectedProjectId) {
      return;
    }
    try {
      const response = await api.updatePaperMetadata(selectedProjectId, paperId, payload);
      setProjectDetail((current) =>
        current ? { ...current, papers: response.papers } : current,
      );
      setStatusMessage(text.paperUpdateSaved);
    } catch (error) {
      setStatusMessage(`${text.paperEditError} ${(error as Error).message ?? ""}`);
    }
  }

  async function handleRefreshPaperMetadata(paperId: string) {
    if (!selectedProjectId) {
      return;
    }
    try {
      const response = await api.refreshPaperMetadata(selectedProjectId, paperId);
      setProjectDetail((current) =>
        current ? { ...current, papers: response.papers } : current,
      );
      const refreshed = response.paper.metadata_json as
        | { last_refresh_status?: string }
        | undefined;
      setStatusMessage(
        refreshed?.last_refresh_status === "no_provider_data"
          ? text.paperRefreshNoData
          : text.paperRefreshSaved,
      );
    } catch (error) {
      setStatusMessage(`${text.paperEditError} ${(error as Error).message ?? ""}`);
    }
  }

  async function handleDeletePaper(paperId: string) {
    if (!selectedProjectId) {
      return;
    }
    const response = await api.deletePaper(selectedProjectId, paperId);
    setProjectDetail((current) =>
      current ? { ...current, papers: response.papers } : current,
    );
    setStatusMessage(text.paperDeletedMessage);
  }

  async function handleRunPaperOcr(paperId: string) {
    if (!selectedProjectId) {
      return;
    }
    try {
      const response = await api.runPaperOcr(selectedProjectId, paperId);
      setProjectDetail((current) =>
        current ? { ...current, papers: response.papers } : current,
      );
      const ocr = (response.paper.metadata_json as { ocr?: { status?: string; recovered_chars?: number } })?.ocr;
      const status = ocr?.status ?? "";
      if (status === "ok" && (ocr?.recovered_chars ?? 0) > 0) {
        setStatusMessage(text.paperOcrSuccess);
      } else if (status.startsWith("no_")) {
        setStatusMessage(text.paperOcrUnavailable);
      } else {
        setStatusMessage(text.paperOcrSkipped);
      }
    } catch (error) {
      setStatusMessage(`${text.paperEditError} ${(error as Error).message ?? ""}`);
    }
  }

  async function handleImportLiterature(result: LiteratureResult) {
    if (!selectedProjectId) {
      return;
    }
    const response = await api.importLiteratureResult(selectedProjectId, {
      ...result,
      notes: `${text.retrievedVia}: ${result.provider}`,
    });
    setProjectDetail((current) =>
      current
        ? {
            ...current,
            papers: response.papers,
          }
        : current,
    );
    setStatusMessage(text.literatureImported);
    await refreshProjects();
  }

  async function handleGeneratePlan() {
    if (!selectedProjectId) {
      return;
    }
    const result = await api.generatePlan(selectedProjectId);
    setProjectDetail((current) => (current ? { ...current, plan: result.plan } : current));
    setStatusMessage(text.planGenerated);
    await refreshProjects();
  }

  async function handleApprovePlan() {
    if (!selectedProjectId) {
      return;
    }
    const result = await api.approvePlan(selectedProjectId);
    setProjectDetail((current) => (current ? { ...current, plan: result.plan } : current));
    setStatusMessage(text.planApproved);
    await refreshProjects();
  }

  async function handleStartRun() {
    if (!selectedProjectId) {
      return;
    }
    const result = await api.startRun(selectedProjectId);
    setRun(result.run);
    setRunStages(result.stages);
    setAuditEvents([]);
    setSelectedStageIndex(1);
    setStatusMessage(text.runStarted);
    await refreshProjects();
  }

  function promptControlPayload(actionLabel: string): { comment: string; decided_by: string } | null {
    if (typeof window === "undefined") {
      return { comment: "", decided_by: "" };
    }
    const comment = window.prompt(text.commentPrompt(actionLabel), "") ?? "";
    if (comment === null) {
      return null;
    }
    let decidedBy = "";
    if (comment.trim()) {
      decidedBy = window.prompt(text.decidedByPrompt, "") ?? "";
    }
    return { comment: comment.trim(), decided_by: decidedBy.trim() };
  }

  async function handlePauseRun() {
    if (!run) {
      return;
    }
    const payload = promptControlPayload(text.pauseRun);
    if (payload === null) {
      return;
    }
    const result = await api.pauseRun(run.id, payload);
    setRun(result.run);
    setRunStages(result.stages);
    setAuditEvents(result.audit_events ?? []);
    setStatusMessage(text.runPaused);
    await refreshProjects();
  }

  async function handleResumeRun() {
    if (!run) {
      return;
    }
    const payload = promptControlPayload(text.resumeRun);
    if (payload === null) {
      return;
    }
    const result = await api.resumeRun(run.id, payload);
    setRun(result.run);
    setRunStages(result.stages);
    setAuditEvents(result.audit_events ?? []);
    setStatusMessage(text.runResumed);
    await refreshProjects();
  }

  async function handleRejectGate() {
    if (!run) {
      return;
    }
    const payload = promptControlPayload(text.rejectGate);
    if (payload === null) {
      return;
    }
    const result = await api.rejectRun(run.id, payload);
    setRun(result.run);
    setRunStages(result.stages);
    setAuditEvents(result.audit_events ?? []);
    setStatusMessage(text.gateRejected);
    await refreshProjects();
  }

  async function handleRetryStage(stageIndex: number) {
    if (!run) {
      return;
    }
    try {
      const result = await api.retryStage(run.id, stageIndex);
      setRun(result.run);
      setRunStages(result.stages);
      setAuditEvents(result.audit_events ?? []);
      setStatusMessage(text.retryQueued);
      await refreshProjects();
    } catch (error) {
      setStatusMessage(`${text.retryStageDisabled} ${(error as Error).message ?? ""}`);
    }
  }

  async function handleRollbackRun() {
    if (!run) {
      return;
    }
    const payload = promptControlPayload(text.rollbackGate);
    if (payload === null) {
      return;
    }
    const result = await api.rollbackRun(run.id, payload);
    setRun(result.run);
    setRunStages(result.stages);
    setAuditEvents(result.audit_events ?? []);
    setSelectedStageIndex(result.run.current_stage_index || 1);
    setStatusMessage(text.rollbackComplete);
    await refreshProjects();
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
  const canPause = run?.status === "running";
  const canResume = run ? run.status === "paused" || run.status === "awaiting_approval" : false;
  const canReject = run?.status === "awaiting_approval";
  const canRollback = run?.status === "awaiting_approval";

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
          <NotificationsTray
            notifications={notifications}
            permission={notificationPermission}
            text={text}
            onEnable={enableNotifications}
            onClear={clearNotifications}
          />
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
                onChange={(event) => setSettings({ ...settings, embedding_model: event.target.value })}
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
            <div className="project-controls">
              <input
                value={projectSearch}
                onChange={(event) => setProjectSearch(event.target.value)}
                placeholder={text.projectSearchPlaceholder}
              />
              <label className="inline-toggle">
                <input
                  type="checkbox"
                  checked={projectIncludeArchived}
                  onChange={(event) => setProjectIncludeArchived(event.target.checked)}
                />
                {text.projectIncludeArchived}
              </label>
            </div>
            <div className="project-list">
              {filteredProjects.length === 0 ? (
                <p className="muted">{text.projectsEmpty}</p>
              ) : null}
              {filteredProjects.map((project) => {
                const archived = Boolean(project.archived_at);
                return (
                  <div
                    key={project.id}
                    className={`project-chip-row ${selectedProjectId === project.id ? "selected" : ""} ${archived ? "archived" : ""}`}
                  >
                    <button
                      className="project-chip"
                      onClick={() => void loadProject(project.id)}
                      type="button"
                    >
                      <strong>{project.title}</strong>
                      <span>
                        {project.status}
                        {archived ? ` · ${text.projectArchivedLabel}` : ""}
                        {project.duplicated_from ? ` · ${text.projectDuplicatedLabel}` : ""}
                      </span>
                    </button>
                    <div className="project-chip-actions">
                      <button
                        type="button"
                        title={text.projectDuplicate}
                        onClick={() => void handleDuplicateProject(project.id)}
                      >
                        ⧉
                      </button>
                      <button
                        type="button"
                        title={archived ? text.projectUnarchive : text.projectArchive}
                        onClick={() => void handleToggleArchive(project)}
                      >
                        {archived ? "⤴" : "📦"}
                      </button>
                      <button
                        type="button"
                        className="danger"
                        title={text.projectDelete}
                        onClick={() => void handleDeleteProject(project)}
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        </aside>

        <main className="main-column">
          <section className="grid two-up">
            <form className="panel" onSubmit={handleCreateProject}>
              <div className="panel-header">
                <h2>{text.createProject}</h2>
              </div>
              <ProjectTemplatePicker
                templates={projectTemplates}
                selectedKey={selectedTemplateKey}
                text={text}
                onSelect={(key) => applyProjectTemplate(key)}
              />
              <label>
                <span className="field-label">
                  <span>{text.ideaTitle}</span>
                  <span className="required-mark">*</span>
                </span>
                <input
                  required
                  value={projectForm.title}
                  onChange={(event) => setProjectForm({ ...projectForm, title: event.target.value })}
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
                  onChange={(event) => setProjectForm({ ...projectForm, background: event.target.value })}
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
                  onChange={(event) => setProjectForm({ ...projectForm, direction: event.target.value })}
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
                  onChange={(event) => setProjectForm({ ...projectForm, goals: event.target.value })}
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
              <form className="stacked-form" onSubmit={handleSearchLiterature}>
                <label>
                  {text.literatureSearch}
                  <input
                    value={literatureQuery}
                    onChange={(event) => setLiteratureQuery(event.target.value)}
                    placeholder={text.literatureSearchPlaceholder}
                  />
                </label>
                <button disabled={!selectedProjectId} type="submit">
                  {text.search}
                </button>
              </form>
              <div className="paper-list">
                {literatureResults.length === 0 ? (
                  <p className="muted">{text.noLiteratureResults}</p>
                ) : null}
                {Object.entries(literatureErrors).map(([provider, error]) => (
                  <article key={`error-${provider}`} className="paper-card">
                    <strong>{text.providerErrors}</strong>
                    <span>{provider}</span>
                    <p>{error}</p>
                  </article>
                ))}
                {literatureResults.map((result) => (
                  <article key={`${result.provider}-${result.canonical_key}`} className="paper-card">
                    <strong>{result.title}</strong>
                    <span>
                      {result.provider} · {result.year || "n/a"} · {result.venue || "n/a"}
                    </span>
                    {result.authors.length ? <p>{summarizeAuthors(result.authors)}</p> : null}
                    {result.doi ? <p>{text.doiLabel}: {result.doi}</p> : null}
                    {result.url ? (
                      <a href={result.url} rel="noreferrer" target="_blank">
                        {result.url}
                      </a>
                    ) : null}
                    {result.abstract ? <p>{result.abstract.slice(0, 220)}</p> : null}
                    <button
                      className="secondary"
                      onClick={() => void handleImportLiterature(result)}
                      type="button"
                    >
                      {text.importResult}
                    </button>
                  </article>
                ))}
              </div>
              <div className="paper-list">
                {(projectDetail?.papers ?? []).map((paper) => (
                  <PaperCard
                    key={paper.id}
                    paper={paper}
                    text={text}
                    onUpdate={(updates) => handleUpdatePaperMetadata(paper.id, updates)}
                    onRefresh={() => handleRefreshPaperMetadata(paper.id)}
                    onDelete={() => handleDeletePaper(paper.id)}
                    onRunOcr={() => handleRunPaperOcr(paper.id)}
                  />
                ))}
              </div>
            </section>
	          </section>

	          <section className="panel">
	            <div className="panel-header">
	              <h2>{text.executionConfig}</h2>
	              <button disabled={!selectedProjectId} form="execution-config-form" type="submit">
	                {text.saveExecutionConfig}
	              </button>
	            </div>
	            <p className="muted">{text.executionConfigBody}</p>
	            <form className="stacked-form" id="execution-config-form" onSubmit={handleSaveExecutionConfig}>
	              <div className="split-fields">
	                <label>
	                  {text.repoPath}
	                  <input
	                    value={executionForm.repo_path}
	                    onChange={(event) => setExecutionForm({ ...executionForm, repo_path: event.target.value })}
	                    placeholder={text.repoPathPlaceholder}
	                  />
	                </label>
	                <label>
	                  {text.repoUrl}
	                  <input
	                    value={executionForm.repo_url}
	                    onChange={(event) => setExecutionForm({ ...executionForm, repo_url: event.target.value })}
	                    placeholder={text.repoUrlPlaceholder}
	                  />
	                </label>
	              </div>
	              <div className="split-fields">
	                <label>
	                  {text.repoRef}
	                  <input
	                    value={executionForm.repo_ref}
	                    onChange={(event) => setExecutionForm({ ...executionForm, repo_ref: event.target.value })}
	                    placeholder={text.repoRefPlaceholder}
	                  />
	                </label>
	                <label>
	                  {text.sandboxWorkdir}
	                  <input
	                    value={executionForm.sandbox_workdir}
	                    onChange={(event) =>
	                      setExecutionForm({ ...executionForm, sandbox_workdir: event.target.value })
	                    }
	                    placeholder={text.sandboxWorkdirPlaceholder}
	                  />
	                </label>
	              </div>
	              <label>
	                {text.setupCommand}
	                <textarea
	                  value={executionForm.sandbox_setup_command}
	                  onChange={(event) =>
	                    setExecutionForm({ ...executionForm, sandbox_setup_command: event.target.value })
	                  }
	                  placeholder={text.setupCommandPlaceholder}
	                />
	              </label>
	              <label>
	                {text.runCommand}
	                <textarea
	                  value={executionForm.sandbox_run_command}
	                  onChange={(event) =>
	                    setExecutionForm({ ...executionForm, sandbox_run_command: event.target.value })
	                  }
	                  placeholder={text.runCommandPlaceholder}
	                />
	              </label>
	              <label>
	                {text.expectedArtifacts}
	                <textarea
	                  value={executionForm.expected_artifacts_text}
	                  onChange={(event) =>
	                    setExecutionForm({ ...executionForm, expected_artifacts_text: event.target.value })
	                  }
	                  placeholder={text.expectedArtifactsPlaceholder}
	                />
	              </label>
	              <details className="sandbox-advanced">
	                <summary>{text.sandboxAdvanced}</summary>
	                <p className="muted">{text.sandboxAdvancedHint}</p>
	                <label>
	                  {text.sandboxBaseImage}
	                  <input
	                    value={executionForm.sandbox_base_image}
	                    onChange={(event) =>
	                      setExecutionForm({ ...executionForm, sandbox_base_image: event.target.value })
	                    }
	                    placeholder={text.sandboxBaseImagePlaceholder}
	                  />
	                </label>
	                <label>
	                  {text.sandboxExtraPackages}
	                  <textarea
	                    value={executionForm.sandbox_extra_packages_text}
	                    onChange={(event) =>
	                      setExecutionForm({
	                        ...executionForm,
	                        sandbox_extra_packages_text: event.target.value,
	                      })
	                    }
	                    placeholder={text.sandboxExtraPackagesPlaceholder}
	                  />
	                </label>
	                <label>
	                  {text.sandboxAptPackages}
	                  <textarea
	                    value={executionForm.sandbox_apt_packages_text}
	                    onChange={(event) =>
	                      setExecutionForm({
	                        ...executionForm,
	                        sandbox_apt_packages_text: event.target.value,
	                      })
	                    }
	                    placeholder={text.sandboxAptPackagesPlaceholder}
	                  />
	                </label>
	                <label>
	                  {text.sandboxPipIndex}
	                  <input
	                    value={executionForm.sandbox_pip_index_url}
	                    onChange={(event) =>
	                      setExecutionForm({
	                        ...executionForm,
	                        sandbox_pip_index_url: event.target.value,
	                      })
	                    }
	                    placeholder={text.sandboxPipIndexPlaceholder}
	                  />
	                </label>
	                <div className="split-fields">
	                  <label>
	                    {text.sandboxTimeoutSeconds}
	                    <input
	                      type="number"
	                      min="0"
	                      value={executionForm.sandbox_timeout_seconds}
	                      onChange={(event) =>
	                        setExecutionForm({
	                          ...executionForm,
	                          sandbox_timeout_seconds: event.target.value,
	                        })
	                      }
	                      placeholder={text.sandboxTimeoutPlaceholder}
	                    />
	                  </label>
	                  <label>
	                    {text.sandboxMaxAttempts}
	                    <input
	                      type="number"
	                      min="1"
	                      max="3"
	                      value={executionForm.sandbox_max_attempts}
	                      onChange={(event) =>
	                        setExecutionForm({
	                          ...executionForm,
	                          sandbox_max_attempts: event.target.value,
	                        })
	                      }
	                      placeholder={text.sandboxMaxAttemptsPlaceholder}
	                    />
	                  </label>
	                </div>
	              </details>
	            </form>
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
                <ReactMarkdown>{projectDetail?.plan?.plan_markdown ?? text.noPlanYet}</ReactMarkdown>
              </div>
            </section>

            <section className="panel">
              <div className="panel-header">
                <h2>{text.runSummary}</h2>
                <div className="inline-actions">
                  <button disabled={!canPause} onClick={handlePauseRun} type="button">
                    {text.pauseRun}
                  </button>
                  <button disabled={!canResume} onClick={handleResumeRun} type="button">
                    {text.resumeRun}
                  </button>
                  <button disabled={!canReject} onClick={handleRejectGate} type="button">
                    {text.rejectGate}
                  </button>
                  <button disabled={!canRollback} onClick={handleRollbackRun} type="button">
                    {text.rollbackGate}
                  </button>
                </div>
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
              <div className="gate-panel">
                <span className="metric-label">{text.activeGate}</span>
                <strong>{activeGateStage?.approval_gate?.label ?? text.noActiveGate}</strong>
                {activeGateStage?.approval_gate?.summary ? (
                  <p className="muted">{activeGateStage.approval_gate.summary}</p>
                ) : null}
                {run?.pending_gate_state ? (
                  <p className="muted">
                    {text.gateState}: {run.pending_gate_state}
                  </p>
                ) : null}
              </div>
              <CostSummaryPanel
                run={run}
                text={text}
              />
              <div className="audit-panel">
                <h3>{text.approvalAudit}</h3>
                {auditEvents.length === 0 ? (
                  <p className="muted">{text.approvalAuditEmpty}</p>
                ) : (
                  <ul className="audit-list">
                    {auditEvents.map((event) => (
                      <li key={event.id} className={`audit-row audit-${event.action}`}>
                        <div className="audit-row-head">
                          <span className="audit-action-pill">{event.action}</span>
                          <span className="audit-stage">
                            {text.auditStage} {event.stage_index || "—"}
                            {event.stage_key ? ` (${event.stage_key})` : ""}
                          </span>
                          <time className="audit-time muted">
                            {new Date(event.created_at).toLocaleString()}
                          </time>
                        </div>
                        <div className="audit-row-body">
                          <div className="audit-decided-by">
                            <span className="metric-label">{text.auditDecidedBy}</span>
                            <strong>{event.decided_by || text.auditDecidedByMissing}</strong>
                          </div>
                          <p className="audit-comment">
                            {event.comment || text.auditCommentMissing}
                          </p>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
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
              currentStage={run?.pending_gate_index || run?.current_stage_index || 0}
              onSelect={setSelectedStageIndex}
              selectedIndex={selectedStageIndex}
            />
          </section>

          <section className="grid detail-grid">
            <section className="panel">
              <div className="panel-header">
                <h2>{text.selectedStageOutput}</h2>
                <div className="inline-actions">
                  {selectedStage && selectedStage.status === "failed" ? (
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => void handleRetryStage(selectedStage.stage_index)}
                    >
                      {text.retryStage}
                    </button>
                  ) : null}
                </div>
              </div>
              <div className="markdown-surface">
                <ReactMarkdown>{selectedStage?.content_md ?? text.selectedStagePlaceholder}</ReactMarkdown>
              </div>
              <div className="detail-stack">
                <div className="detail-block">
                  <h3>{text.stageNotes}</h3>
                  <p>{selectedStage?.notes || text.selectedStagePlaceholder}</p>
                  <StageAttemptList stage={selectedStage} text={text} />
                </div>
                <div className="detail-block">
                  <h3>{text.stageContract}</h3>
                  <p className="muted">{selectedStageDefinition?.prompt_focus ?? ""}</p>
                  <strong>{text.inputs}</strong>
                  <ul className="contract-list">
                    {(selectedStageDefinition?.contract.inputs ?? selectedStage?.contract_json.inputs ?? []).map((item) => (
                      <li key={`input-${item}`}>{item}</li>
                    ))}
                  </ul>
                  <strong>{text.mustProduce}</strong>
                  <ul className="contract-list">
                    {(selectedStageDefinition?.contract.must_produce ??
                      selectedStage?.contract_json.must_produce ??
                      []).map((item) => (
                      <li key={`produce-${item}`}>{item}</li>
                    ))}
                  </ul>
                  <strong>{text.qualityBar}</strong>
                  <ul className="contract-list">
                    {(selectedStageDefinition?.contract.quality_bar ??
                      selectedStage?.contract_json.quality_bar ??
                      []).map((item) => (
                      <li key={`quality-${item}`}>{item}</li>
                    ))}
                  </ul>
                  <strong>{text.disallowed}</strong>
                  <ul className="contract-list">
                    {(selectedStageDefinition?.contract.disallowed ??
                      selectedStage?.contract_json.disallowed ??
                      []).map((item) => (
                      <li key={`blocked-${item}`}>{item}</li>
                    ))}
                  </ul>
                </div>
                <div className="detail-block">
                  <h3>{text.artifactSchema}</h3>
                  {(selectedStageDefinition?.artifact_schema ?? selectedStage?.artifact_schema_json ?? []).map((item) => (
                    <div key={item.key} className="artifact-item">
                      <strong>{item.label}</strong>
                      <span>
                        {item.type} · {item.required ? "required" : "optional"}
                      </span>
                      <p>{item.description}</p>
                    </div>
                  ))}
                </div>
                <div className="detail-block">
                  <h3>{text.artifactSnapshot}</h3>
                  {selectedStage?.artifact_json && Object.keys(selectedStage.artifact_json).length ? (
                    <div className="artifact-surface">{renderArtifactValue(selectedStage.artifact_json)}</div>
                  ) : (
                    <pre className="json-surface">{prettyJson(selectedStage?.artifact_json)}</pre>
                  )}
                </div>
                <ValidationReportPanel
                  text={text}
                  report={
                    (selectedStage?.metadata_json as { validation?: ValidationReport } | undefined)
                      ?.validation
                  }
                />
              </div>
            </section>

            <section className="panel">
              <div className="panel-header">
                <h2>{text.sourceGroundingSnapshot}</h2>
                <div className="inline-actions">
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => void handleReindexProject(false)}
                    disabled={!selectedProjectId}
                  >
                    {text.reindexIncremental}
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => void handleReindexProject(true)}
                    disabled={!selectedProjectId}
                  >
                    {text.reindexFull}
                  </button>
                </div>
              </div>
              <form className="stacked-form" onSubmit={handleSearchGroundedPapers}>
                <label>
                  {text.groundedRetrieval}
                  <input
                    value={groundedQuery}
                    onChange={(event) => setGroundedQuery(event.target.value)}
                    placeholder={text.groundedRetrievalPlaceholder}
                  />
                </label>
                <button disabled={!selectedProjectId} type="submit">
                  {text.groundedSearch}
                </button>
                {groundedStrategy ? (
                  <p className="muted">
                    {text.groundedStrategy}: {groundedStrategy}
                  </p>
                ) : null}
              </form>
              <div className="snapshot-list">
                {groundedResults.length === 0 ? (
                  <p className="muted">{text.noGroundedResults}</p>
                ) : null}
                {groundedResults.map((item) => (
                  <div key={item.chunk_id} className="snapshot-item">
                    {item.preview_thumbnail_url ? (
                      <img
                        alt={`${item.paper_title} ${text.preview}`}
                        className="paper-thumb compact"
                        loading="lazy"
                        src={item.preview_thumbnail_url}
                      />
                    ) : null}
                    <strong>{item.paper_title}</strong>
                    <span>
                      {item.citation_key || "uncited"} · {item.source_provider || item.source_type} · score{" "}
                      {item.score.toFixed(3)}
                    </span>
                    <p>{item.text.slice(0, 260)}</p>
                  </div>
                ))}
              </div>
              <div className="snapshot-list">
                {(projectDetail?.papers ?? []).map((paper) => (
                  <div key={paper.id} className="snapshot-item">
                    {paper.preview_thumbnail_url ? (
                      <img
                        alt={`${paper.title} ${text.preview}`}
                        className="paper-thumb compact"
                        loading="lazy"
                        src={paper.preview_thumbnail_url}
                      />
                    ) : null}
                    <strong>{paper.title}</strong>
                    <span>{paperSummaryLine(paper)}</span>
                    {paper.authors_json?.length ? <p>{summarizeAuthors(paper.authors_json)}</p> : null}
                    {paper.doi ? <p>{text.doiLabel}: {paper.doi}</p> : null}
                    <p>{paper.extracted_text?.slice(0, 260) || paper.abstract?.slice(0, 260) || text.noExtractedText}</p>
                  </div>
                ))}
              </div>
              <CitationGraphPanel
                graph={citationGraph}
                onRefresh={() => void refreshCitationGraph(selectedProjectId || null)}
                text={text}
              />
            </section>
          </section>
        </main>
      </div>
    </div>
  );
}

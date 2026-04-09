import type { RunStage, StageCatalogItem } from "../lib/api";

type Props = {
  catalog: StageCatalogItem[];
  locale: "en" | "cn";
  runStages: RunStage[];
  currentStage: number;
  onSelect: (index: number) => void;
  selectedIndex: number;
};

const statusTone: Record<string, string> = {
  pending: "stage-pending",
  running: "stage-running",
  completed: "stage-completed",
  failed: "stage-failed",
};

const statusLabel: Record<"en" | "cn", Record<string, string>> = {
  en: {
    pending: "pending",
    running: "running",
    completed: "completed",
    failed: "failed",
  },
  cn: {
    pending: "待执行",
    running: "进行中",
    completed: "已完成",
    failed: "失败",
  },
};

const gateLabel: Record<"en" | "cn", Record<string, string>> = {
  en: {
    pending: "gate pending",
    approved: "gate approved",
    rejected: "gate rejected",
  },
  cn: {
    pending: "门控待审批",
    approved: "门控已通过",
    rejected: "门控已拒绝",
  },
};

export function StageTimeline({
  catalog,
  locale,
  runStages,
  currentStage,
  onSelect,
  selectedIndex,
}: Props) {
  return (
    <div className="stage-grid">
      {catalog.map((stage) => {
        const progress = runStages.find((item) => item.stage_index === stage.index);
        const status = progress?.status ?? "pending";
        const isActive = stage.index === currentStage;
        const isSelected = stage.index === selectedIndex;
        const gateState = progress?.gate_status ?? "";
        const approvalRequired = stage.approval_gate || progress?.approval_required;
        return (
          <button
            key={stage.key}
            className={`stage-card ${statusTone[status] ?? "stage-pending"} ${isActive ? "is-active" : ""} ${isSelected ? "is-selected" : ""}`}
            onClick={() => onSelect(stage.index)}
            type="button"
          >
            <div className="stage-card-top">
              <span className="stage-index">{stage.index}</span>
              <span className="stage-status">{statusLabel[locale][status] ?? status}</span>
            </div>
            <h3>{stage.label}</h3>
            <p>{stage.summary}</p>
            {approvalRequired ? (
              <span className={`stage-gate gate-${gateState || "idle"}`}>
                {gateState ? gateLabel[locale][gateState] ?? gateState : stage.approval_gate?.label ?? progress?.approval_label}
              </span>
            ) : null}
            <span className="stage-owner">{stage.owner}</span>
          </button>
        );
      })}
    </div>
  );
}

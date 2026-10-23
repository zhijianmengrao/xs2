import NovelAdvisorConversation from "../components/NovelAdvisorConversation";
import { adoptNovelAdvisor, advisorMarkdown } from "../lib/novel-advisor";
import NovelConfigurationSuggestions from "../components/NovelConfigurationSuggestions";
import { applyAssistantConfiguration, premiseWithWorldDirection, type ConfigurationReceipt } from "../lib/novel-assistant-configuration";
import NovelReferenceChoice from "../components/NovelReferenceChoice";
import { referenceTitle } from "../components/novel-reference";
import { getNovelProgress, type NovelProgress } from "../lib/api";
import NovelManuscriptDownload from "../components/NovelManuscriptDownload";
import NovelRepairPanel from "../components/NovelRepairPanel";
import { beginReaderRepair } from "../lib/novel-repair-flow";
import { advanceRepairPlan } from "../lib/novel-repair-runner";
import { getNovelReaderReport } from "../lib/api";
import { applyNovelRepairPlan } from "../lib/api";
import { getNovelAdoptedWriting, getNovelReferenceCandidates, type ReferenceChoice } from "../lib/api";
import { novelEntryStage, canOpenNovelStage } from "../lib/novel-flow-entry";
import { retainAdoptedWriting, toggleWriting, validateReferenceAdaptations } from "../lib/novel-writing-selection";
import { nextNovelStageAfterReferenceAdoption } from "../lib/novel-continuation";
import { nextSerialChapter, selectProductionChapter } from "../lib/novel-chapters";
import { getNovelChapterContext, previewNovelChapterRemoval, removeNovelChapter } from "../lib/api";
import { compareNovelOutlines, outlineChapterImpacts, outlineImpactInventory } from "../lib/novel-outline-impact";
import NovelReferenceContent from "../components/NovelReferenceContent";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft, ArrowRight, BookOpen, Check, ChevronDown, CircleAlert, Clock3,
  FileText, FolderOpen, Gauge, Headphones, ListChecks, Loader2, MessageCircle,
  Play, RefreshCw, Settings2, Sparkles, WandSparkles, Library, Upload, SlidersHorizontal, Trash2, Users,
} from "lucide-react";
import {
  askNovelAssistant, checkNovelContinuation, fetchNovelArchiveState, fetchNovelAssistantHistory, attachWritingLibrary, createTask, getTask, getWorkflow, listWorkspaceFiles, listWorkflows,
  publishWritingLibrary, saveNovelProject, listNovelProjects, deleteNovelProject, inspectNovelImportUrl, importNovelUrl, readWorkflowWorkspaceFile, readWorkspaceFile, runTask, writeNovelWorkspaceText, listWritingLibrary,
  type WritingLibraryItem,
} from "../lib/api";
import type { WorkflowDefinition, WorkflowVariable } from "../types";
import type { NovelAssistantEntry } from "../lib/api";
import NovelArchiveContent from "../components/NovelArchiveContent";
import NovelPlotProposals from "../components/NovelPlotProposals";
import NovelReaderReport from "../components/NovelReaderReport";
import WritingLibraryView from "../components/WritingLibraryView";
import NovelWorkflowArtifact from "../components/NovelWorkflowArtifact";
import NovelReadingDialog from "../components/NovelReadingDialog";
import NovelStepModels from "../components/NovelStepModels";
import { NovelDisplaySettings, NovelWorkbenchProvider, NovelWorkbenchSurface, NovelUnitMotif } from "../components/NovelWorkbenchPreferences";
import { repairNodeModels } from "../lib/novel-workbench-models";
import "./novel-workbench.css";
import { readerRepairDecision, shouldAdvanceSerialChapter } from "../lib/novel-auto-flow";
import { archiveLabel, archiveScalar } from "../lib/novel-archive";
import CharacterVoiceEditor from "../components/CharacterVoiceEditor";

const PREFIX = "xs2-novel-flywheel-";
const DEFAULT_WORKSPACE = "data/workspaces/books/welcome";

type StageMeta = {
  id: string; title: string; group: string; description: string; artifact: string;
  preferredFields?: string[]; optional?: boolean;
};

const STAGES: StageMeta[] = [
  { id: "reference-distillation", title: "资料蒸馏", group: "独立资料分析", description: "导入参考文件或网址，独立分析风格、写法和冲突，完成后进入共享写法库。", artifact: "learning/candidates.json", preferredFields: ["window_size"], optional: true },
  { id: "novel-advisor", title: "小说顾问", group: "方向准备", description: "根据资料和创意，判断题材定位、写法、钩子、伏笔和递进冲突。", artifact: "learning/advisor_report.json", preferredFields: ["premise", "genre", "narrative_pov", "language", "conflict_plan_mode", "conflict_point_count", "foreshadowing_count"], optional: true },
  { id: "style-compatibility-advisor", title: "写法兼容顾问", group: "本书参考写法", description: "比较当前作品与蒸馏候选，给出推荐、适配和冲突提示；没有候选时可直接创作。", artifact: "learning/compatibility_report.json", preferredFields: ["premise", "genre", "narrative_pov", "language"], optional: true },
  { id: "adopt-reference", title: "选择与确认", group: "本书参考写法", description: "分别确认风格、写法与冲突的本书适配；已有采用内容持续保留。", artifact: "learning/active_context.md", optional: true },
  { id: "build", title: "建立世界观", group: "创作规划", description: "根据已确认的方向建立世界运行规则。", artifact: "meta/world_foundation.md", preferredFields: ["premise", "genre", "language", "narrative_pov"] },
  { id: "character", title: "创建角色", group: "创作规划", description: "生成角色档案、关系和声音锚点。", artifact: "meta/character_profiles.md", preferredFields: ["narrative_pov", "language"] },
  { id: "story-plan", title: "规划故事", group: "创作规划", description: "把世界、角色、看点和写法汇总为故事引擎。", artifact: "meta/story_plan.md", preferredFields: ["narrative_pov", "language"] },
  { id: "outline", title: "生成卷纲", group: "创作规划", description: "按短篇或长篇模式规划篇幅、分卷、伏笔和递进冲突。", artifact: "outline/near_term_outline.md", preferredFields: ["volume_number", "estimated_length", "words_per_chapter", "latest_chapter", "narrative_pov", "conflict_plan_mode", "conflict_point_count", "foreshadowing_count"] },
  { id: "mvp", title: "生成正文", group: "正文生产", description: "按当前章意图、字数和作品设定生成正文。", artifact: "story/{chapter}/chapter.md", preferredFields: ["human_intent", "world_intent", "target_word_count", "writer_type", "chapter_number", "narrative_pov", "language"] },
  { id: "polish", title: "润色本章", group: "正文生产", description: "改善语言、节奏和阅读体验，不改变已确认事实。", artifact: "story/{chapter}/chapter.md", preferredFields: ["narrative_pov", "language"] },
  { id: "reader-sim", title: "模拟读者", group: "质量检查", description: "从读者视角判断看点、钩子、节奏和继续阅读意愿。", artifact: "story/{chapter}/reader_report.json", preferredFields: ["chapter_number", "narrative_pov", "language"], optional: true },
  { id: "post-hoc", title: "质量审核", group: "质量检查", description: "确认章节事实并回写世界、角色、伏笔和叙事债务。", artifact: "story/{chapter}/diff_story_confirmed.md", preferredFields: ["chapter_number", "narrative_pov", "language"] },
  { id: "export", title: "导出成品", group: "交付", description: "合并已完成章节，生成成品和导出清单。", artifact: "export/manuscript.md", preferredFields: ["output_path", "manifest_path"] },
];

// 引用型步骤（写法采用/顾问），模块级常量保持引用稳定，供 useCallback 依赖使用
const REFERENCE_STAGES = STAGES.filter(stage => ["style-compatibility-advisor", "adopt-reference"].includes(stage.id));

const FALLBACK_DEFAULTS: Record<string, string> = {
  reference_path: "references/source.txt", window_size: "4200", reference_mode: "auto", premise: "", genre: "都市情感", language: "中文",
  narrative_pov: "third_person", volume_number: "1", estimated_length: "中", words_per_chapter: "2000-2500",
  latest_chapter: "0000", chapter_number: "0001", prev_chapter: "0000", human_intent: "", world_intent: "",
  target_word_count: "3000-4000", writer_type: "single", output_path: "export/manuscript.md", manifest_path: "export/manifest.json",
  conflict_plan_mode: "short_full", conflict_point_count: "3", foreshadowing_count: "2", chapter_ending_mode: "continue",
};

const LABELS: Record<string, string> = {
  reference_path: "参考资料路径", window_size: "分析窗口长度", premise: "故事创意", genre: "题材类型", language: "输出语言",
  narrative_pov: "叙事视角", volume_number: "目标卷号", estimated_length: "预计篇幅", words_per_chapter: "每章字数",
  latest_chapter: "最新章节号", chapter_number: "章节号", prev_chapter: "上一章节号", human_intent: "本章想写什么",
  world_intent: "世界发生的变化", target_word_count: "目标字数", writer_type: "写手模式", output_path: "成品路径", manifest_path: "导出清单路径",
  conflict_plan_mode: "冲突规划范围", conflict_point_count: "冲突点数量", foreshadowing_count: "伏笔数量",
};

type TaskRef = { workflow_id: string; task_id: string };
type View = "home" | "flow" | "chapters" | "review" | "archive" | "library" | "settings" | "distill" | "reference" | "humanware";
type Mode = "short" | "serial";
type AutoScope = "manual" | "short_full" | "serial_batch";
type WritingMode = "original" | "reuse" | "distill";
type Project = {
  chapterDrafts?: Record<string, Record<string, string>>;
  advisorBrief?: string;
  configuredFields?: string[];
  assistantConfigurations?: Record<string, ConfigurationReceipt>;
  pendingAssistantConfiguration?: string;
  selectedStyles?: string[]; selectedConflicts?: string[]; referenceAdaptations?: Record<string, string>;
  repairReviewOnly?: boolean;
  assessmentOnly?: boolean;
  repairModel?: string;
  autoRepairPlanId?: string;
  pendingReferenceAdoption?: string;
  continuationIssue?: Awaited<ReturnType<typeof checkNovelContinuation>> | null;
  _revision?: number;
  readerRepairCount?: number; autoRepairLimit?: number; autoPauseReason?: string; autoLaunchStage?: string;
  title: string; mode: Mode; index: number; stageId?: string; values: Record<string, string>; refs: Record<string, TaskRef>;
  completed: string[]; selected: string[]; autoNext: boolean; autoScope: AutoScope; autoChapterLimit: number;
  autoChapterStarted: number | null; directionConfirmed: boolean; distillationSkipped: boolean;
  advisorAccepted: boolean; assistantPlan: string; writingMode: WritingMode; libraryRefs: string[]; persisted: boolean;
};
type CatalogItem = { workflow_id: string; name: string; node_count: number; version: number; status?: string; definition?: WorkflowDefinition };
type WorkspaceFile = { path: string; size_bytes: number; modified_at: number; character_count?: number | null };
type Candidate = { candidate_id: string; mechanism: string; transfer_guidance: string; constraints: string[]; layer?: string; support_count?: number; pov_compatibility?: string; adaptation_guidance?: string; risk_flags?: string[]; application_scope?: string[] };
type ConflictPattern = { scope?: string; goal: string; obstacle: string; attempt: string; cost: string; next_obstacle: string; foreshadowing?: string[] };
type CandidateSet = { candidates: Candidate[]; candidates_sha256: string; conflict_patterns?: ConflictPattern[]; style_choices?: ReferenceChoice[]; conflict_choices?: ReferenceChoice[]; reference_choices_sha256?: string };
const storageKey = (workspace: string) => `xs2-novel-control-v2:${workspace.toLowerCase()}`;
const workflowId = (stageId: string) => PREFIX + stageId;
const terminal = ["completed", "failed", "stopped", "cancelled", "interrupted"];
const cardClass = "rounded-2xl border border-border bg-card";
const inputClass = "w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 disabled:opacity-60";

async function backupCurrentOutline(workspace: string, fallbackContent = "") {
  let content = fallbackContent.trim();
  try {
    const outline = await readWorkspaceFile(workflowId("build"), workspace, "outline/near_term_outline.md");
    if (outline.content.trim()) content = outline.content;
  } catch {
    // The page's file list can lag behind a completed outline task; use its verified preview if needed.
  }
  if (!content) return "";
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const path = `planning/backups/outline-before-${stamp}/near_term_outline.md`;
  await writeNovelWorkspaceText(workflowId("build"), workspace, path, content);
  return content;
}

function restore(workspace: string): Project {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey(workspace)) || "null");
    if (saved) return {
      chapterDrafts: saved.chapterDrafts || {},
      configuredFields: saved.configuredFields || [], assistantConfigurations: saved.assistantConfigurations || {},
      pendingAssistantConfiguration: saved.pendingAssistantConfiguration || "",
      advisorBrief: saved.advisorBrief || "",
      selectedStyles: saved.selectedStyles || [], selectedConflicts: saved.selectedConflicts || [], referenceAdaptations: saved.referenceAdaptations || {},
      pendingReferenceAdoption: saved.pendingReferenceAdoption || "",
      continuationIssue: saved.continuationIssue || null,
      title: saved.title || "未命名作品", mode: saved.mode === "serial" ? "serial" : "short", index: Number.isInteger(saved.index) ? saved.index : 0,
      _revision: saved._revision, assessmentOnly: saved.assessmentOnly === true, repairReviewOnly: saved.repairReviewOnly === true, repairModel: saved.repairModel || "", autoRepairPlanId: saved.autoRepairPlanId || "", stageId: saved.stageId, values: { ...FALLBACK_DEFAULTS, ...(saved.values || {}) }, refs: saved.refs || {}, completed: saved.completed || [], selected: saved.selected || [],
      readerRepairCount: Number(saved.readerRepairCount) || 0, autoRepairLimit: Math.max(1, Math.min(5, Number(saved.autoRepairLimit) || 2)), autoPauseReason: saved.autoPauseReason || "", autoLaunchStage: saved.autoLaunchStage || "",
      autoNext: saved.autoNext === true, autoScope: saved.autoScope || "manual", autoChapterLimit: Number(saved.autoChapterLimit) || 1,
      autoChapterStarted: typeof saved.autoChapterStarted === "number" ? saved.autoChapterStarted : null, directionConfirmed: saved.directionConfirmed === true,
      distillationSkipped: saved.distillationSkipped === true, advisorAccepted: saved.advisorAccepted === true, assistantPlan: saved.assistantPlan || "", writingMode: saved.writingMode || "original", libraryRefs: saved.libraryRefs || [], persisted: saved.persisted !== false,
    };
  } catch { /* invalid local draft */ }
  return {
    title: "未命名作品", mode: "short", index: 0, stageId: "novel-advisor", values: { ...FALLBACK_DEFAULTS }, refs: {}, completed: [], selected: [],
    autoNext: false, autoScope: "manual", autoChapterLimit: 1, autoChapterStarted: null, directionConfirmed: false,
    distillationSkipped: false, advisorAccepted: false, assistantPlan: "", writingMode: "original", libraryRefs: [], persisted: false,
  };
}

function mergeProjectState(workspace: string, saved: Partial<Project>): Project {
  const defaults = restore(workspace);
  return { ...defaults, ...saved, values: { ...FALLBACK_DEFAULTS, ...saved.values }, persisted: true };
}

function sameWorkspace(first: string, second: string): boolean {
  const normalize = (value: string) => value.replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
  const a = normalize(first), b = normalize(second);
  return a === b || a.endsWith(`/${b}`) || b.endsWith(`/${a}`);
}

function statusLabel(status: string) {
  return ({ pending: "等待启动", running: "运行中", pre_running: "准备中", retry_waiting: "等待重试", resume_pending: "等待恢复", interrupted: "已中断", completed: "已完成", failed: "执行失败", stopped: "已停止", cancelled: "已取消" } as Record<string, string>)[status] || status;
}

function chapterListSummary(chapters: string[]) {
  return chapters.length ? `第 ${chapters.slice(0, 10).map(Number).join("、")} 章${chapters.length > 10 ? `等 ${chapters.length} 章` : ""}` : "暂无";
}

function outlineChangeSummary(changes: ReturnType<typeof compareNovelOutlines>["changes"]) {
  const groups = [
    { type: "updated", label: "内容调整" },
    { type: "added", label: "新增章节" },
    { type: "removed", label: "移除章节" },
  ] as const;
  const parts = groups.flatMap(({ type, label }) => {
    const chapters = changes.filter(change => change.type === type).map(change => change.chapter);
    return chapters.length ? [`${label}：${chapterListSummary(chapters)}`] : [];
  });
  return parts.length ? parts.join("；") : "未发现章节内容变化";
}

function chapterPlanRefreshPrompt(chapter: string, reason: string) {
  return `请基于当前大纲、世界设定、人物状态和我已采用的写法，重新规划第 ${Number(chapter)} 章。之前采用的章节方案因为依据已变化而过期，但请保留它作为对照，不要静默沿用或删除。请按我当前的创作意图重新给出本章目标、递进阻碍、人物选择、代价、伏笔触发与章末推进，并说明与旧方案的差异。触发原因：${reason}`;
}

function outlineArtifactImpact(impact: ReturnType<typeof outlineChapterImpacts>[number]) {
  if (impact.type === "downstream") {
    const status = [
      impact.hasPlan ? "已有章节方案，可能受前文变化连带影响，需复核因果、人物动机和伏笔" : "",
      impact.hasDraft ? "已有正文会保留，需人工检查衔接，必要时返修" : "",
      impact.hasConfirmedArchive ? "已确认档案会保留，正文返修后需重新审核" : "",
    ].filter(Boolean);
    return status.length ? status.join("；") : "大纲未直接改动此章，建议检查前后衔接";
  }
  const status = [
    impact.hasPlan ? "已有章节方案，需按新大纲重新核对" : "尚无章节方案",
    impact.hasDraft ? "已有正文需人工核对，必要时返修" : "尚无正文",
    impact.hasConfirmedArchive ? "已有确认档案会保留，正文若返修需重新审核" : "尚无确认档案",
  ];
  if (impact.type === "removed" && (impact.hasPlan || impact.hasDraft || impact.hasConfirmedArchive)) {
    status.push("大纲移除不会自动删除现存产物，需决定保留、改写或归档");
  }
  return status.join("；");
}

function outlineImpactLabel(type: ReturnType<typeof outlineChapterImpacts>[number]["type"]) {
  return ({
    updated: "内容调整",
    added: "新增章节",
    removed: "从新大纲移除",
    downstream: "后续章节待复核",
  } as const)[type];
}

function NovelWorkbenchContent() {
  const [workspace, setWorkspace] = useState(() => localStorage.getItem("xs2-novel-workspace") || DEFAULT_WORKSPACE);
  const activeWorkspace = useRef(workspace);
  activeWorkspace.current = workspace;
  const [referenceStage, setReferenceStage] = useState("adopt-reference");
  const [view, setView] = useState<View>(() => new URLSearchParams(window.location.search).get("view") === "flow" ? "flow" : "home");
  const [reviewChapter, setReviewChapter] = useState("");
  const [chapterOpening, setChapterOpening] = useState(false);
  const chapterOpeningGuard = useRef(false);
  const [project, setProject] = useState<Project>(() => restore(workspace));
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [workspaceDraft, setWorkspaceDraft] = useState(workspace);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [files, setFiles] = useState<WorkspaceFile[]>([]);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [catalogError, setCatalogError] = useState("");
  const [pageFeedback, setPageFeedback] = useState("");
  const [loadedWorkspace, setLoadedWorkspace] = useState("");
  const lastSavedProject = useRef("");
  const [projectList, setProjectList] = useState<Array<{workspace: string; state: Partial<Project>; progress?: NovelProgress}>>([]);
  const refreshProjects = useCallback(async () => {
    try { setProjectList((await listNovelProjects()).projects); } catch (failure) { setCatalogError(failure instanceof Error ? failure.message : "无法读取作品列表"); }
  }, []);
  useEffect(() => { void refreshProjects(); }, [refreshProjects, workspace]);
  useEffect(() => {
    if (loadedWorkspace === workspace) return;
    let active = true;
    void listNovelProjects().then(result => {
      if (!active) return;
      setProjectList(result.projects);
      const saved = result.projects.find(item => sameWorkspace(item.workspace, workspace));
      const restored = saved ? mergeProjectState(workspace, saved.state) : restore(workspace);
      lastSavedProject.current = JSON.stringify(restored);
      setProject(restored);
      setLoadedWorkspace(workspace);
    }).catch(failure => { if (active) setCatalogError(failure instanceof Error ? failure.message : "读取作品设置失败"); });
    return () => { active = false; };
  }, [workspace, loadedWorkspace]);
  useEffect(() => {
    if (!project.persisted || loadedWorkspace !== workspace) return;
    if (JSON.stringify(project) === lastSavedProject.current) return;
    const timer = window.setTimeout(async () => {
      try {
        const result = await saveNovelProject(workflowId("build"), workspace, project);
        if (activeWorkspace.current !== workspace) return;
        lastSavedProject.current = JSON.stringify({ ...project, _revision: result.revision });
        setProject(current => ({ ...current, _revision: result.revision }));
        const canonical = result.workspace;
        if (canonical && canonical !== workspace) {
          localStorage.setItem("xs2-novel-workspace", canonical);
          setWorkspace(canonical);
          setWorkspaceDraft(canonical);
        }
        await refreshProjects();
      } catch (failure) {
        if (activeWorkspace.current !== workspace) return;
        const message = failure instanceof Error ? failure.message : "保存作品失败";
        setCatalogError(message);
        if (message.includes("409")) {
          setPageFeedback("后台已更新这本作品，正在恢复最新进度；旧页面内容没有覆盖后台成果。");
          setLoadedWorkspace("");
        }
      }
    }, 600);
    return () => window.clearTimeout(timer);
  }, [workspace, project, refreshProjects, loadedWorkspace]);
  const refreshCatalog = useCallback(async () => {
    try {
      const items = await listWorkflows();
      const relevant = items.filter((item) => item.workflow_id.startsWith(PREFIX));
      const enriched = await Promise.all(relevant.map(async (item) => {
        try { return { ...item, definition: (await getWorkflow(item.workflow_id)).definition }; } catch { return item; }
      }));
      setCatalog(enriched); setCatalogError("");
    } catch (failure) { setCatalogError(failure instanceof Error ? failure.message : "无法读取工作流目录"); }
  }, []);
  const refreshFiles = useCallback(async () => {
    setLoadingFiles(true);
    try { const result = await listWorkspaceFiles(workflowId("build"), workspace); if (sameWorkspace(activeWorkspace.current, workspace)) setFiles(result.files); }
    catch (failure) { if (sameWorkspace(activeWorkspace.current, workspace)) setFiles([]); throw failure; }
    finally { if (sameWorkspace(activeWorkspace.current, workspace)) setLoadingFiles(false); }
  }, [workspace]);
  useEffect(() => { void refreshCatalog(); const timer = window.setInterval(() => void refreshCatalog(), 30000); return () => window.clearInterval(timer); }, [refreshCatalog]);
  useEffect(() => { void refreshFiles().catch(() => {}); }, [refreshFiles]);
  useEffect(() => { if (view !== "home" || loadedWorkspace !== workspace) return; const refresh = () => { void refreshProjects(); void refreshFiles().catch(() => {}); }; refresh(); const timer = window.setInterval(refresh, 5000); return () => window.clearInterval(timer); }, [view, loadedWorkspace, workspace, refreshProjects, refreshFiles]);
  useEffect(() => { if (project.persisted && loadedWorkspace === workspace) localStorage.setItem(storageKey(workspace), JSON.stringify(project)); }, [workspace, project, loadedWorkspace]);
  useEffect(() => {
    if (!project.pendingAssistantConfiguration || loadedWorkspace !== workspace) return;
    let active = true;
    let missingReads = 0;
    let timer: number | undefined;
    setPageFeedback("助手正在根据你的想法完善设置…可以继续查看其他页面。");
    const refresh = async () => {
      try {
        const result = await fetchNovelAssistantHistory(workflowId("build"), workspace);
        if (!active) return;
        const entry = result.entries.find(item => item.id === project.pendingAssistantConfiguration);
        if (!entry && ++missingReads >= 12) {
          setProject(current => ({...current, pendingAssistantConfiguration: ""}));
          setPageFeedback("尚未找到本次配置分析记录，请回到助手查看提交状态后重试；现有设置保持原值。");
          return;
        }
        if (entry && entry.status !== "running") {
          setProject(current => ({ ...applyAssistantConfiguration(current, entry, FALLBACK_DEFAULTS), pendingAssistantConfiguration: "" }));
          setPageFeedback(entry.status === "completed" ? "助手配置分析已完成，可在作品设置或助手建议中查看填写与保留结果。" : `助手配置分析失败：${entry.message || "请重新分析"}`);
          return;
        }
      } catch { /* A transient read failure must not discard a durable pending request. */ }
      if (active) timer = window.setTimeout(() => void refresh(), 2500);
    };
    void refresh();
    return () => { active = false; if (timer !== undefined) window.clearTimeout(timer); };
  }, [project.pendingAssistantConfiguration, loadedWorkspace, workspace]);
  const applyWorkspace = () => { const next = workspaceDraft.trim(); if (!next) { setPageFeedback("工作区不能为空，请先输入目录。 "); return; } if (next === workspace) { setPageFeedback("当前已经是这个工作区。 "); return; } localStorage.setItem("xs2-novel-workspace", next); setWorkspace(next); setFiles([]); setProject(restore(next)); setPageFeedback(`已切换到工作区：${next}`); setView("home"); };
    const stepItems = useMemo(() => {
    const known = STAGES.filter(stage => !["reference-distillation", "style-compatibility-advisor", "adopt-reference"].includes(stage.id)).map((stage, index) => {
      const item = catalog.find(item => item.workflow_id === workflowId(stage.id));
      const meta = item?.definition?.console;
      return { ...stage, title: meta?.title || item?.name || stage.title, description: meta?.description || stage.description, group: meta?.group || stage.group, artifact: meta?.artifact || stage.artifact, order: meta?.order ?? (index + 1) * 10 };
    });
    const extra = catalog.filter(item => item.definition?.console?.app === "novel-workbench" && !STAGES.some(stage => workflowId(stage.id) === item.workflow_id)).map(item => {
      const meta = item.definition!.console!;
      return { id: item.workflow_id.slice(PREFIX.length), title: meta.title || item.name, group: meta.group || "扩展流程", description: meta.description || "插件提供的创作步骤。", artifact: meta.artifact || "", optional: true, preferredFields: [], order: meta.order ?? 999 };
    });
    return [...known, ...extra].sort((a,b) => a.order-b.order);
  }, [catalog]);
  useEffect(() => {
    if (loadedWorkspace !== workspace) return;
    const id = novelEntryStage(project, stepItems);
    const index = stepItems.findIndex(stage => stage.id === id);
    if (index < 0 || (id === project.stageId && index === project.index)) return;
    setProject(current => { const stageId = novelEntryStage(current, stepItems); return {...current, stageId, index:Math.max(0, stepItems.findIndex(stage => stage.id === stageId))}; });
    // novelEntryStage 需要整个 project，但 effect 只关心步骤定位字段；补全 project 会在
    // 用户输入（values 等）时高频重跑。所需字段已显式列出，此处有意保持精确依赖。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stepItems, project.stageId, project.index, project.persisted, project.refs, project.completed, project.directionConfirmed, loadedWorkspace, workspace]);
  const referenceIndex = Math.max(0, REFERENCE_STAGES.findIndex(stage => stage.id === referenceStage));
  const setReferenceProject = useCallback<React.Dispatch<React.SetStateAction<Project>>>(update => {
    setProject(current => {
      const moduleProject = {...current, index: Math.max(0, REFERENCE_STAGES.findIndex(stage => stage.id === referenceStage)), stageId: referenceStage, autoNext: false, autoScope: "manual" as AutoScope};
      const next = typeof update === "function" ? update(moduleProject) : update;
      if (next.stageId && ["style-compatibility-advisor", "adopt-reference"].includes(next.stageId)) setReferenceStage(next.stageId);
      return {...next, index: current.index, stageId: current.stageId, autoNext: current.autoNext, autoScope: current.autoScope};
    });
  }, [referenceStage]);
  const openReference = (advisor = false) => {setReferenceStage(advisor ? "style-compatibility-advisor" : "adopt-reference"); setView("reference");};
  const continueAfterReferenceAdoption = useCallback(async () => {
    const setupStages = ["build", "character", "story-plan", "outline"];
    let check: Awaited<ReturnType<typeof checkNovelContinuation>> | null = null;
    let checkMessage = "";
    if (setupStages.every(stage => project.completed.includes(stage))) {
      try {
        check = await checkNovelContinuation(workflowId("build"), workspace, project.values.chapter_number || "0001");
      } catch (failure) {
        checkMessage = `写法已采用，但当前无法完成续写检查：${failure instanceof Error ? failure.message : String(failure)}。正文启动前会再次检查。`;
      }
    }
    const nextId = check
      ? nextNovelStageAfterReferenceAdoption(project.completed, project.stageId || "mvp", check)
      : setupStages.find(stage => !project.completed.includes(stage)) || project.stageId || "mvp";
    const nextIndex = Math.max(0, stepItems.findIndex(stage => stage.id === nextId));
    const needsPlanRefresh = !!check && !check.ready && check.action === "outline";
    const planRefreshPrompt = needsPlanRefresh && check
      ? chapterPlanRefreshPrompt(check.chapter, check.message)
      : "";
    setProject(current => ({
      ...current,
      pendingReferenceAdoption: "",
      continuationIssue: check && !check.ready ? check : null,
      index: nextIndex,
      stageId: nextId,
      refs: check && !check.ready && check.action !== "outline"
        ? Object.fromEntries(Object.entries(current.refs).filter(([stage]) => stage !== nextId))
        : current.refs,
      completed: check && !check.ready && check.action !== "outline"
        ? current.completed.filter(stage => stage !== nextId)
        : current.completed,
      values: check && !check.ready
        ? { ...current.values, chapter_number: check.chapter, prev_chapter: String(Math.max(0, Number(check.chapter) - 1)).padStart(4, "0") }
        : current.values,
      assistantPlan: planRefreshPrompt || current.assistantPlan,
      autoNext: false,
      autoScope: "manual",
      autoLaunchStage: "",
    }));
    setView("flow");
    if (needsPlanRefresh) setAssistantOpen(true);
    const nextTitle = stepItems.find(stage => stage.id === nextId)?.title || nextId;
    setPageFeedback(checkMessage || (check && !check.ready
      ? `写法已采用。检查发现第 ${Number(check.chapter)} 章还不能直接生成正文，已定位到「${nextTitle}」：${check.next_step || check.message}${needsPlanRefresh ? " 创作助手已打开并准备好重新规划本章；采用新方案后再返回正文。" : ""}`
      : `写法已采用。按当前进度，下一步是「${nextTitle}」${check?.next_step ? `：${check.next_step}` : "。"}`));
  }, [project.completed, project.stageId, project.values.chapter_number, setProject, stepItems, workspace]);
  const chapterFiles = files.filter((file) => /^story\/\d{4}\/chapter\.md$/i.test(file.path));
  const chapters = chapterFiles.map((file) => ({ number: file.path.match(/story\/(\d{4})/)?.[1] || "0000", file }));
  const removedChapters = files.flatMap(file => {
    const number = file.path.match(/^archive\/chapter_resets\/(\d{4})\.json$/)?.[1];
    return number && !chapters.some(chapter => chapter.number === number) ? [number] : [];
  }).sort();
  const nextChapterNumber = nextSerialChapter(chapters.map(chapter => chapter.number), project.values.chapter_number);
  const openChapterProduction = async (chapter: string, action = "write", automatic = false) => {
    if (chapterOpeningGuard.current) return;
    chapterOpeningGuard.current = true; setChapterOpening(true);
    setPageFeedback(`正在核对第 ${Number(chapter)} 章的正文、计划和任务状态…`);
    const requestedWorkspace = workspace;
    try {
      const context = await getNovelChapterContext(workflowId("build"), workspace, chapter, action);
      const check = action === "write" && !context.has_body
        ? await checkNovelContinuation(workflowId("build"), workspace, chapter) : null;
      if (!sameWorkspace(activeWorkspace.current, requestedWorkspace)) return;
      if (check && !check.ready && ((check.action === "post-hoc" && check.chapter !== chapter) || check.reason_code === "chapter_missing")) {
        setPageFeedback(`第 ${Number(chapter)} 章尚未开始：${check.message} ${check.next_step || `请先审核第 ${Number(check.chapter)} 章的档案，再续写。`}`);
        setProject(current => ({...current, autoNext:false, autoScope:"manual", autoLaunchStage:""}));
        setView("chapters"); return;
      }
      const stage = action === "assess" ? "reader-sim" : action === "audit" ? "post-hoc"
        : action === "repair" ? "polish" : check && !check.ready ? check.action
        : context.has_body ? ["polish", "reader-sim", "post-hoc", "export"].find(id => !context.completed.includes(id)) || "export" : "mvp";
      const index = stepItems.findIndex(item => item.id === stage);
      if (index < 0) throw new Error("对应工作流尚未加载，请刷新工作流目录。");
      setProject(current => ({...selectProductionChapter(current, context, stage, index, automatic && (!check || check.ready)),
        assessmentOnly: action === "assess", repairReviewOnly: action === "audit",
        autoChapterStarted: automatic && (!check || check.ready) ? (current.autoChapterStarted || 1) + 1 : current.autoChapterStarted,
        autoNext: action === "assess" || action === "audit" || (automatic && (!check || check.ready)),
        autoScope: action === "assess" || action === "audit" ? "short_full" : automatic && (!check || check.ready) ? "serial_batch" : "manual",
        autoLaunchStage: action === "assess" || action === "audit" ? stage : automatic && (!check || check.ready) ? stage : "",
        continuationIssue: check && !check.ready ? check : null,
        assistantPlan: check && !check.ready && check.action === "outline" ? chapterPlanRefreshPrompt(chapter, check.message) : current.assistantPlan,
      }));
      setReviewChapter(chapter); setView("flow");
      if (check && !check.ready && check.action === "outline") setAssistantOpen(true);
      setPageFeedback(`${check && !check.ready ? check.next_step || check.message : `已进入第 ${Number(chapter)} 章「${stepItems[index].title}」。${action === "write" && !context.has_body ? "沿用本书设定与写法，确认本章意图后点击开始；无需重新运行小说顾问。" : ""}`} ${context.message}`);
    } catch (failure) {
      const errorMsg = failure instanceof Error ? failure.message : String(failure);
      const isBusy = errorMsg.includes('仍有创作或评估任务正在处理') || errorMsg.includes('正在处理');

      if (isBusy) {
        setPageFeedback(`⚠️ 章节操作暂时无法启动：当前有其他任务正在执行中。请等待任务完成后再试，或在创作流程页面查看任务状态。原有正文和进度保留。`);
      } else {
        setPageFeedback(`章节操作未开始：${errorMsg}。原有正文和进度保留。`);
      }

      setProject(current => ({...current, autoNext:false, autoScope:"manual", autoLaunchStage:""}));
    } finally { chapterOpeningGuard.current = false; setChapterOpening(false); }
  };
  const manageChapter = async (chapter: string, operation: "delete" | "regenerate") => {
    if (chapterOpeningGuard.current) return;
    chapterOpeningGuard.current = true; setChapterOpening(true);
    const requestedWorkspace = workspace;
    const label = operation === "regenerate" ? "重新生成" : "删除";
    setPageFeedback(`正在检查第 ${Number(chapter)} 章的${label}范围…`);
    try {
      const preview = await previewNovelChapterRemoval(workflowId("build"), workspace, chapter);
      if (!sameWorkspace(activeWorkspace.current, requestedWorkspace)) return;
      if (!window.confirm(`确定${label}第 ${Number(chapter)} 章吗？\n\n${preview.message}\n\n${operation === "regenerate" ? "确认后使用各步骤当前配置的模型，从正文生成开始执行本章完整流程。" : "删除后可在章节目录重新生成这一章，不会跳过章节编号。"}\n旧稿会保存在本书的章节备份目录。`)) {
        setPageFeedback(`已取消${label}，原章节保留。`); return;
      }
      setPageFeedback(`正在备份并${label}第 ${Number(chapter)} 章…`);
      const result = await removeNovelChapter({workflow_id:workflowId("build"), workspace, chapter, operation,
        expected_sha256:preview.body_sha256, expected_revision:preview.revision});
      if (!sameWorkspace(activeWorkspace.current, requestedWorkspace)) return;
      const restored = mergeProjectState(workspace, result.state as Partial<Project>);
      lastSavedProject.current = JSON.stringify(restored);
      setProject(operation === "regenerate" ? {...restored, autoNext:true, autoScope:"short_full",
        autoLaunchStage:"mvp", autoChapterStarted:1} : restored);
      setReviewChapter(chapter); setView(operation === "regenerate" ? "flow" : "chapters");
      setPageFeedback(`${operation === "regenerate" ? `第 ${Number(chapter)} 章已准备重新生成，正在启动正文流程。` : `第 ${Number(chapter)} 章已从正文目录删除，可在下方重新生成。`} ${preview.later_chapters.length ? `后续第 ${preview.later_chapters.map(Number).join("、")} 章需要衔接复核。` : ""} 原稿备份：${result.backup_path}`);
      await refreshFiles(); await refreshProjects();
    } catch (failure) {
      setPageFeedback(`${label}未完成：${failure instanceof Error ? failure.message : String(failure)}。请按提示处理后重试。`);
    } finally { chapterOpeningGuard.current = false; setChapterOpening(false); }
  };
  const repairChapter = async (feedbackPath: string, modelId: string, chapter: string) => {
    if (chapterOpeningGuard.current) return;
    chapterOpeningGuard.current = true; setChapterOpening(true);
    try {
      const context = await getNovelChapterContext(workflowId("build"), workspace, chapter, "repair");
      const index = stepItems.findIndex(stage => stage.id === "polish");
      if (index < 0) throw new Error("润色工作流尚未加载，请刷新目录。");
      setProject(current => beginReaderRepair(selectProductionChapter(current, context, "polish", index), index, feedbackPath, modelId));
      setReviewChapter(chapter); setPageFeedback(`已准备第 ${Number(chapter)} 章定向返修。原稿已备份。${context.message}`); setView("flow");
    } finally { chapterOpeningGuard.current = false; setChapterOpening(false); }
  };
  const openFlow = (index = project.index) => { setProject((current) => ({ ...current, index: Math.max(0, Math.min(index, Math.max(stepItems.length - 1, 0))), stageId: stepItems[index]?.id })); setView("flow"); };
  const selectProject = (item: { workspace: string; state: Partial<Project>; progress?: NovelProgress }, targetView: View = "home") => {
    localStorage.setItem("xs2-novel-workspace", item.workspace);
    setWorkspace(item.workspace);
    if (!sameWorkspace(item.workspace, workspace)) setFiles([]);
    setWorkspaceDraft(item.workspace);
    const restored = mergeProjectState(item.workspace, item.state);
    lastSavedProject.current = JSON.stringify(restored);
    setProject(restored);
    setLoadedWorkspace(item.workspace);
    setPageFeedback(targetView === "flow" ? `已进入「${item.state.title || "未命名作品"}」的创作流程。` : `已打开作品：${item.state.title || "未命名作品"}`);
    setView(targetView);
  };
  const removeProject = async (targetWorkspace: string) => {
    const target = projectList.find((item) => item.workspace === targetWorkspace);
    const title = target?.state.title || "未命名作品";
    if (!window.confirm(`确定删除「${title}」吗？这会永久删除该作品目录、正文、设定、蒸馏和质量记录。`)) return;
    setPageFeedback("正在删除作品目录…");
    try {
      await deleteNovelProject(workflowId("build"), targetWorkspace);
      localStorage.removeItem(storageKey(targetWorkspace));
      const remaining = projectList.filter((item) => item.workspace !== targetWorkspace);
      setProjectList(remaining);
      if (workspace.toLowerCase() === targetWorkspace.toLowerCase()) {
        if (remaining[0]) selectProject(remaining[0]);
        else {
          const fresh = `data/workspaces/books/short-${Date.now()}-${Math.random().toString(36).slice(2,7)}`;
          setWorkspace(fresh); setWorkspaceDraft(fresh); setProject({ ...restore(fresh), persisted: false, index: 0, stageId: "novel-advisor" }); setView("home");
        }
      }
      setPageFeedback(`已删除作品「${title}」及其工作区目录。`);
    } catch (failure) { setPageFeedback(failure instanceof Error ? `删除失败：${failure.message}` : "删除失败，请稍后重试。"); }
  };
  const resetNew = (mode: Mode) => {
    const next = `data/workspaces/books/${mode}-${Date.now()}-${Math.random().toString(36).slice(2,7)}`;
    setWorkspace(next); setWorkspaceDraft(next);
    setFiles([]);
    setLoadedWorkspace(next);
    const base = restore(next);
    setProject({ ...base, mode, persisted: false, index: 0, stageId: "novel-advisor", autoScope: "manual", autoChapterLimit: mode === "short" ? 1 : 3, values: { ...base.values, conflict_plan_mode: mode === "serial" ? "serial_opening" : "short_full", conflict_point_count: mode === "serial" ? "4" : "3", foreshadowing_count: mode === "serial" ? "3" : "2" } }); setPageFeedback("新作品尚未保存；开始第一个工作流步骤后才会登记到作品管理。"); setView("flow");
  };
  const saveSettings = async (updated: Project) => {
    const title = updated.title.trim();
    if (!title) throw new Error("请先填写作品名称。");
    let state = { ...updated, title };
    if (state.persisted) {
      const result = await saveNovelProject(workflowId("build"), workspace, state);
      if (activeWorkspace.current !== workspace) return;
      state = { ...state, _revision: result.revision };
      lastSavedProject.current = JSON.stringify(state);
      localStorage.setItem(storageKey(workspace), JSON.stringify(state));
      setProjectList(items => items.map(item => sameWorkspace(item.workspace, workspace) ? { ...item, state } : item));
    }
    setProject(state);
    setPageFeedback(state.persisted ? `已保存「${title}」的作品设置。` : `「${title}」设置已应用到草稿，开始工作流后才会保存作品。`);
  };
  const refreshFilesFromHeader = async () => { setPageFeedback("正在读取作品资料…"); try { await refreshFiles(); setPageFeedback("作品资料已刷新。"); } catch (failure) { setPageFeedback(failure instanceof Error ? `刷新失败：${failure.message}` : "作品资料刷新失败，请稍后重试。"); } };
  return <div className="h-full overflow-hidden bg-background"><div className="flex h-full min-h-0"><aside className="novel-sidebar hidden w-64 shrink-0 flex-col border-r border-border bg-card/80 lg:flex"><div className="border-b border-border px-6 py-6"><div className="flex items-center gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary/15 text-primary"><BookOpen className="h-5 w-5" /></div><div><p className="font-semibold tracking-wide">XS2</p><p className="text-xs text-muted-foreground">小说工作台</p></div></div></div><nav className="space-y-1 p-4"><SidebarButton active={view === "home"} icon={BookOpen} label="我的作品" onClick={() => setView("home")} /><SidebarButton active={view === "archive"} icon={FileText} label="小说档案" onClick={() => setView("archive")} /><SidebarButton active={view === "chapters"} icon={ListChecks} label="章节目录" onClick={() => setView("chapters")} /><SidebarButton active={view === "flow"} icon={WandSparkles} label="创作流程" onClick={() => setView("flow")} /><SidebarButton active={view === "review"} icon={Headphones} label="读者评估" onClick={() => setView("review")} /><SidebarButton active={view === "library"} icon={Library} label="写法库" onClick={() => setView("library")} /><SidebarButton active={view === "reference"} icon={SlidersHorizontal} label="本书参考写法" onClick={() => openReference()} /><SidebarButton active={view === "humanware"} icon={Users} label="角色声音" onClick={() => setView("humanware")} /><SidebarButton active={view === "distill"} icon={Upload} label="资料蒸馏" onClick={() => setView("distill")} /><SidebarButton active={view === "settings"} icon={Settings2} label="作品设置" onClick={() => setView("settings")} /></nav><NovelUnitMotif /></aside><main className="min-w-0 flex-1 overflow-y-auto"><header className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-background/90 px-5 py-4 backdrop-blur lg:px-8"><div className="flex items-center gap-3"><div className="max-w-[360px] truncate rounded-lg border border-border bg-card px-3 py-2 text-xs">工作区 · {workspace}</div><span className="hidden text-xs text-muted-foreground xl:inline">{pageFeedback || "工作区中的作品资料会持续保存"}</span></div><div className="flex items-center gap-3"><NovelDisplaySettings /><button onClick={() => void refreshFilesFromHeader()} className="rounded-lg border border-border p-2 text-muted-foreground hover:text-foreground" title="刷新作品文件"><RefreshCw className={`h-4 w-4 ${loadingFiles ? "animate-spin" : ""}`} /></button><button aria-expanded={assistantOpen} onClick={() => { if(stepItems[project.index]?.id === "novel-advisor") {setView("flow");setAssistantOpen(false);} else setAssistantOpen(open=>!open); }} className="flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground"><MessageCircle className="h-4 w-4" />创作助手</button></div></header><div className="novel-content mx-auto max-w-[1500px] px-5 py-6 lg:px-8">{pageFeedback && <p role="status" className="mb-4 rounded-xl border border-primary/25 bg-primary/5 p-3 text-sm text-primary">{pageFeedback}</p>}<div className="mb-4 flex flex-wrap gap-2 lg:hidden">{(["home", "archive", "flow", "library", "reference", "humanware", "distill", "settings", "chapters", "review"] as View[]).map((item,i) => <button key={item} onClick={() => setView(item)} className="rounded-lg border border-border px-3 py-2 text-sm">{["我的作品", "小说档案", "创作流程", "写法库", "本书参考写法", "角色声音", "资料蒸馏", "作品设置", "章节目录", "读者评估"][i]}</button>)}</div>{view === "archive" && <ArchiveView project={project} workspace={workspace} onBack={() => setView("home")} onFlow={() => setView("flow")} />}{view === "settings" && <SettingsView key={`${workspace}:${loadedWorkspace}`} project={project} onSave={saveSettings} onDistill={() => setView("distill")} onContinue={() => openFlow()} onLibrary={() => setView("library")} workspace={workspace} onBack={() => setView("home")} />}{view === "library" && <WritingLibraryView workflowId={workflowId("build")} project={project} workspace={workspace} onAttach={async (id, refresh = false) => { const attached = await attachWritingLibrary({workflow_id:workflowId("build"), workspace, library_id:id, refresh}); if (attached.already_attached) return; setProject(current => ({...current, writingMode:"reuse", libraryRefs:[...new Set([...current.libraryRefs,id])], selected:current.selected, refs:Object.fromEntries(Object.entries(current.refs).filter(([stage]) => !["style-compatibility-advisor"].includes(stage))), stageId:current.stageId, index:current.index})); }} onConfirm={() => openReference()} onBack={() => setView("home")} />}{view === "home" && <HomeView chapterOpening={chapterOpening} nextChapter={nextChapterNumber} onNextChapter={() => void openChapterProduction(nextChapterNumber)} project={project} projects={projectList} currentWorkspace={workspace} chapters={chapters} files={files} stageTitle={stepItems[project.index]?.title || "开始创作"} workspaceDraft={workspaceDraft} setWorkspaceDraft={setWorkspaceDraft} applyWorkspace={applyWorkspace} catalogError={catalogError} onNew={resetNew} onContinue={() => openFlow(project.index)} onChapters={() => setView("chapters")} onOpenFlowProject={(item) => selectProject(item, "flow")} onOpenArchive={(item) => selectProject(item, "archive")} onSettings={(item) => selectProject(item, "settings")} onDeleteProject={removeProject} />}{view === "chapters" && <ChapterView project={project} chapters={chapters} removedChapters={removedChapters} onRegenerate={chapter => void manageChapter(chapter, "regenerate")} onDelete={chapter => void manageChapter(chapter, "delete")} onCreateMissing={chapter => void openChapterProduction(chapter)} workspace={workspace} chapterOpening={chapterOpening} nextChapter={nextChapterNumber} onNextChapter={() => void openChapterProduction(nextChapterNumber)} onBack={() => setView("home")} onOpen={(chapter) => { setReviewChapter(chapter); setView("review"); }} onRepair={(chapter) => { setReviewChapter(chapter); setPageFeedback(`已打开第 ${Number(chapter)} 章返修，请查看该章读者报告并规划返修；缺少有效报告时可先重新评估。`); setView("review"); }} />}{view === "review" && <ReviewView project={project} workspace={workspace} chapter={reviewChapter || project.values.chapter_number} opening={chapterOpening} onBack={() => setView("chapters")} onFlow={() => setView("flow")} onAssess={() => void openChapterProduction(reviewChapter || project.values.chapter_number, "assess")} onAudit={() => void openChapterProduction(reviewChapter || project.values.chapter_number, "audit")} onRepairFlow={() => void openChapterProduction(reviewChapter || project.values.chapter_number)} onRepair={(feedbackPath, modelId) => repairChapter(feedbackPath, modelId, reviewChapter || project.values.chapter_number)} />}{view === "humanware" && <div className="space-y-6"><div className="flex items-center justify-between mb-6"><h1 className="text-2xl font-bold">角色声音锚点</h1><button onClick={() => setView("home")} className="rounded-lg border border-border px-4 py-2 text-sm">返回首页</button></div><CharacterVoiceEditor workspaceId={workspace} /></div>}<div hidden={view !== "distill"}><DistillationView catalog={catalog} onRefreshCatalog={refreshCatalog} onLibrary={() => setView("library")} /></div>{view === "reference" && <><div className="mb-5 flex flex-wrap items-center justify-between gap-3"><p className="text-sm leading-7 text-muted-foreground">本书参考写法是可选准备。没有候选时也可以直接创作；新增参考不改动已有正文与创作进度。</p><div className="flex gap-2"><button onClick={() => openReference(true)} className="rounded-lg border border-border px-4 py-2 text-sm">让 AI 检查适配</button><button onClick={() => openReference()} className="rounded-lg border border-border px-4 py-2 text-sm">选择与确认</button><button onClick={() => setView("flow")} className="rounded-lg border border-primary/30 px-4 py-2 text-sm text-primary">返回创作流程</button></div></div><FlowView moduleOnly project={{...project, index:referenceIndex, stageId:REFERENCE_STAGES[referenceIndex].id, autoNext:false, autoScope:"manual"}} setProject={setReferenceProject} stages={REFERENCE_STAGES} currentStage={REFERENCE_STAGES[referenceIndex]} catalog={catalog} workspace={workspace} files={files} chapters={chapters} onHome={() => setView("library")} onRefreshCatalog={refreshCatalog} onRefreshFiles={refreshFiles} onReview={() => { setReviewChapter(project.values.chapter_number); setView("review"); }} onLibrary={() => setView("library")} onReferenceAdopted={continueAfterReferenceAdoption} onOpenAssistant={() => setAssistantOpen(true)} onOpenReference={openReference} /></>}{view === "flow" && <FlowView chapterOpening={chapterOpening} nextChapterNumber={nextChapterNumber} onContinueChapter={openChapterProduction} project={project} setProject={setProject} stages={stepItems} currentStage={stepItems[project.index] || stepItems[0]} catalog={catalog} workspace={workspace} files={files} chapters={chapters} onHome={() => setView("home")} onRefreshCatalog={refreshCatalog} onRefreshFiles={refreshFiles} onReview={() => { setReviewChapter(project.values.chapter_number); setView("review"); }} onLibrary={() => setView("library")} onReferenceAdopted={continueAfterReferenceAdoption} onOpenAssistant={() => setAssistantOpen(true)} onOpenReference={openReference} />}</div>{assistantOpen && stepItems[project.index]?.id !== "novel-advisor" && <aside aria-label="创作助手面板" className="novel-assistant-drawer fixed bottom-0 right-0 top-16 z-30 w-full max-w-[450px] overflow-y-auto border-l border-border bg-background px-4 py-5 shadow-2xl"><div className="mb-3 flex items-center justify-between"><span className="text-xs text-muted-foreground">本书共用一个助手 · 讨论与方案随作品保存</span><button aria-label="收起创作助手" onClick={()=>setAssistantOpen(false)} className="rounded-lg border border-border px-3 py-1.5 text-xs">收起</button></div><AssistantPanel key={workspace} workspace={workspace} project={project} setProject={setProject} currentStage={stepItems[project.index] || STAGES[1]} nextStage={stepItems[project.index+1]} candidateSet={null} impactInventory={outlineImpactInventory(files)} hasStoryFacts={files.some(file=>file.path==='meta/world_foundation.md')} onManualSelect={() => openReference()}/></aside>}</main></div></div>;
}

function SidebarButton({ active, icon: Icon, label, onClick }: { active: boolean; icon: typeof BookOpen; label: string; onClick: () => void }) { return <button aria-current={active ? "page" : undefined} onClick={onClick} className={`novel-nav-item flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-sm transition ${active ? "bg-primary/15 text-primary" : "text-muted-foreground hover:bg-secondary hover:text-foreground"}`}><Icon className="h-4 w-4" />{label}</button>; }

function SettingsView({ project, workspace, onSave, onContinue, onLibrary, onDistill, onBack }: { project: Project; workspace: string; onSave: (updated: Project) => Promise<void>; onContinue: () => void; onLibrary: () => void; onDistill: () => void; onBack: () => void }) {
  const [title, setTitle] = useState(project.title);
  const [mode, setMode] = useState(project.mode);
  const [values, setValues] = useState({ ...project.values });
  const [configuredFields, setConfiguredFields] = useState(project.configuredFields || []);
  const editedFields = useRef(new Set<string>());
  useEffect(() => {
    setValues(current => ({ ...current, ...Object.fromEntries(Object.entries(project.values).filter(([key]) => !editedFields.current.has(key))) }));
  }, [project.assistantConfigurations, project.values]);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [failed, setFailed] = useState(false);
  const guard = useRef(false);
  const started = Object.keys(project.refs).length > 0;
  const update = (key: string, value: string) => { editedFields.current.add(key); setValues(current => ({ ...current, [key]: value })); setConfiguredFields(current => [...new Set([...current, key])]); setFeedback(""); };
  const save = async (next?: () => void) => {
    if (guard.current) return;
    guard.current = true; setSaving(true); setFailed(false); setFeedback("正在保存作品设置…");
    try {
      if (!title.trim()) throw new Error("请填写作品名称。");
      if (!values.genre.trim()) throw new Error("请填写题材。");
      for (const key of ["conflict_point_count", "foreshadowing_count"]) if (!/^\d+$/.test(values[key] || "") || Number(values[key]) > 50) throw new Error("冲突和伏笔数量须为 0 到 50 的整数。");
      await onSave({ ...project, title: title.trim(), mode, configuredFields, values: { ...project.values, ...values } });
      setTitle(title.trim());
      setFeedback(project.persisted ? "作品设置已保存，名称已同步到作品管理。" : "设置已应用到新作品草稿；开始第一个工作流步骤后才会保存作品。");
      next?.();
    } catch (failure) { setFailed(true); setFeedback(failure instanceof Error ? failure.message : "保存失败，请重试。"); }
    finally { guard.current = false; setSaving(false); }
  };
  return <div className="space-y-5">
    <PageHeader eyebrow="作品设置" title={project.title} description="设置本书名称和创作参数；保存后供 AI 助手与后续工作流使用。" onBack={onBack} />
    <section className={`${cardClass} p-5 text-sm leading-7`}><h2 className="font-semibold">这些设置有什么作用？</h2><p className="mt-2 text-muted-foreground">作品名称用于作品管理和档案展示。题材、创意、视角、字数、冲突与伏笔要求会作为后续工作流和 AI 助手的输入；写法来源决定本书参考哪些写法。</p><p className="mt-2 text-muted-foreground">已生成的正文、人物、世界观和风格档案不会因修改设置而自动重写。需要调整时，请回到对应步骤重新生成；正在运行的任务沿用启动时的设置。</p></section>
    <form onSubmit={event => { event.preventDefault(); void save(); }} className="space-y-5">
      <fieldset disabled={saving} className="grid gap-5 lg:grid-cols-2">
        <section className={`${cardClass} space-y-4 p-5`}><h2 className="font-semibold">作品信息</h2>
          <label className="block text-sm">作品名称<input maxLength={120} className={`${inputClass} mt-2`} value={title} onChange={event => { setTitle(event.target.value); setFeedback(""); }} /><span className="mt-1 block text-xs text-muted-foreground">修改名称后点击保存。作品目录保持原位置。</span></label>
          <label className="block text-sm">作品类型<select className={`${inputClass} mt-2`} disabled={started} value={mode} onChange={event => { const next = event.target.value as Mode; setMode(next); update("conflict_plan_mode", next === "serial" ? "serial_opening" : "short_full"); }}><option value="short">短篇</option><option value="serial">长篇连载</option></select>{started && <span className="mt-1 block text-xs text-muted-foreground">作品已经开始创作，类型沿用当前设定。</span>}</label>
          <label className="block text-sm">题材<input className={`${inputClass} mt-2`} value={values.genre} onChange={event => update("genre", event.target.value)} /></label>
          <label className="block text-sm">故事创意<textarea rows={4} className={`${inputClass} mt-2`} value={values.premise} onChange={event => update("premise", event.target.value)} placeholder="主角想达成什么，遇到什么问题，故事有什么看点？" /></label>
          <label className="block text-sm">世界观方向<textarea rows={4} className={`${inputClass} mt-2`} value={values.world_direction || ""} onChange={event => update("world_direction", event.target.value)} placeholder="故事发生在哪里，有哪些影响人物选择的规则？" /><span className="mt-1 block text-xs leading-6 text-muted-foreground">供小说顾问与建立世界观使用的规划草稿；正式档案会在对应步骤生成。</span></label>
        </section>
        <section className={`${cardClass} space-y-4 p-5`}><h2 className="font-semibold">创作要求</h2>
          <label className="block text-sm">叙事视角<select className={`${inputClass} mt-2`} value={values.narrative_pov} onChange={event => update("narrative_pov", event.target.value)}><option value="third_person">第三人称</option><option value="first_person">第一人称</option></select></label>
          {mode === "serial" ? <label className="block text-sm">当前章节结尾<select aria-label="当前章节结尾" className={`${inputClass} mt-2`} value={values.chapter_ending_mode || "continue"} onChange={event => update("chapter_ending_mode",event.target.value)}><option value="continue">普通连载章节，继续推进故事</option><option value="book_final">本书终章，完成全书收尾</option></select><span className="mt-1 block text-xs text-muted-foreground">默认保留主线与后续悬念；只有明确写终章才选择全书收尾。终章导出后自动批次停止。</span></label> : <p className="text-sm leading-6 text-muted-foreground">短篇结尾：完成本篇主要冲突、关键伏笔与人物选择，保留余味。</p>}
          <label className="block text-sm">输出语言<input className={`${inputClass} mt-2`} value={values.language} onChange={event => update("language", event.target.value)} /></label>
          <label className="block text-sm">正文目标字数<input className={`${inputClass} mt-2`} value={values.target_word_count} onChange={event => update("target_word_count", event.target.value)} /><span className="mt-1 block text-xs text-muted-foreground">用于下一次正文生成，支持字数范围，例如 3000-4000。</span></label>
          <label className="block text-sm">预计篇幅<input className={`${inputClass} mt-2`} value={values.estimated_length} onChange={event => update("estimated_length", event.target.value)} /></label>
          <label className="block text-sm">每章字数<input className={`${inputClass} mt-2`} value={values.words_per_chapter} onChange={event => update("words_per_chapter", event.target.value)} /><span className="mt-1 block text-xs text-muted-foreground">预计篇幅和每章字数用于大纲规划。</span></label>
        </section>
        <section className={`${cardClass} space-y-4 p-5`}><h2 className="font-semibold">冲突与伏笔</h2><p className="text-xs leading-6 text-muted-foreground">规划时遵循目标、前置伏笔、阻碍、解决代价和后续问题的因果递进，正文与审核继续跟踪回收。</p>
          <label className="block text-sm">规划范围<select className={`${inputClass} mt-2`} value={values.conflict_plan_mode} onChange={event => update("conflict_plan_mode", event.target.value)}>{mode === "short" ? <option value="short_full">短篇全文</option> : <><option value="serial_opening">长篇开局</option><option value="serial_arc">长篇当前卷</option><option value="serial_chapter">长篇当前章节</option></>}</select></label>
          <div className="grid grid-cols-2 gap-3"><label className="block text-sm">冲突点数量<input type="number" min={0} max={50} className={`${inputClass} mt-2`} value={values.conflict_point_count} onChange={event => update("conflict_point_count", event.target.value)} /></label><label className="block text-sm">伏笔数量<input type="number" min={0} max={50} className={`${inputClass} mt-2`} value={values.foreshadowing_count} onChange={event => update("foreshadowing_count", event.target.value)} /></label></div>
        </section>
        <section className={`${cardClass} space-y-4 p-5`}><h2 className="font-semibold">写法来源</h2><p className="text-sm leading-7 text-muted-foreground">{project.writingMode === "original" ? "原创起步：由故事规划生成本书的统一风格基线。" : project.writingMode === "reuse" ? `已选择 ${project.libraryRefs.length} 份写法库结果，可在「本书参考写法」查看实际采用的风格、写法和冲突。` : "已使用参考资料；本书实际采用内容以确认记录为准。"}</p><p className="text-xs leading-6 text-muted-foreground">写法库可跨作品复用。未选择或未确认的写法不会自动成为创作要求。</p><div className="flex flex-wrap gap-2"><button type="button" onClick={() => void save(onLibrary)} className="rounded-xl border border-border px-4 py-2 text-sm">选择写法库</button><button type="button" onClick={() => void save(onDistill)} className="rounded-xl border border-border px-4 py-2 text-sm">导入新资料</button></div><p className="break-all text-xs text-muted-foreground">作品资料目录：{workspace}</p></section>
      </fieldset>
      <div className="flex flex-wrap items-center gap-3"><button type="submit" disabled={saving} className="rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground disabled:opacity-60">{saving ? "正在保存…" : project.persisted ? "保存作品设置" : "应用草稿设置"}</button><button type="button" disabled={saving} onClick={() => void save(onContinue)} className="rounded-xl border border-border px-4 py-2.5 text-sm disabled:opacity-60">保存并进入创作流程</button></div>
      {feedback && <p role={failed ? "alert" : "status"} className={`rounded-xl border p-3 text-sm ${failed ? "border-destructive/30 text-destructive" : "border-primary/30 text-primary"}`}>{feedback}</p>}
    </form>
  </div>;
}

function HomeView({ chapterOpening, nextChapter, onNextChapter, project, projects, currentWorkspace, chapters, files, stageTitle, workspaceDraft, setWorkspaceDraft, applyWorkspace, catalogError, onNew, onContinue, onChapters, onOpenFlowProject, onOpenArchive, onSettings, onDeleteProject }: {
  chapterOpening: boolean; nextChapter: string; onNextChapter: () => void;
  project: Project;
  projects: Array<{ workspace: string; state: Partial<Project>; progress?: NovelProgress }>;
  currentWorkspace: string;
  chapters: Array<{ number: string; file: WorkspaceFile }>;
  files: WorkspaceFile[];
  stageTitle: string;
  workspaceDraft: string;
  setWorkspaceDraft: (value: string) => void;
  applyWorkspace: () => void;
  catalogError: string;
  onNew: (mode: Mode) => void;
  onContinue: () => void;
  onChapters: () => void;
  onOpenFlowProject: (item: { workspace: string; state: Partial<Project>; progress?: NovelProgress }) => void;
  onOpenArchive: (item: { workspace: string; state: Partial<Project>; progress?: NovelProgress }) => void;
  onSettings: (item: { workspace: string; state: Partial<Project>; progress?: NovelProgress }) => void;
  onDeleteProject: (workspace: string) => Promise<void>;
}) {
  const [progress, setProgress] = useState<NovelProgress | null>(null);
  const [progressError, setProgressError] = useState("");
  useEffect(() => {
    let active = true;
    const refresh = async () => { try { const result = await getNovelProgress(workflowId("build"), currentWorkspace); if (active) { setProgress(result); setProgressError(""); } } catch (failure) { if (active) setProgressError(failure instanceof Error ? failure.message : "读取进度失败"); } };
    setProgress(null); void refresh();
    const timer = window.setInterval(() => void refresh(), 4000);
    return () => { active = false; window.clearInterval(timer); };
  }, [currentWorkspace]);
  const totalChars = chapters.reduce((sum, item) => sum + (item.file.character_count ?? 0), 0);
  return <div className="space-y-6">
    <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.22em] text-primary">XS2 小说工作台</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">我的作品</h1><p className="mt-2 text-sm text-muted-foreground">作品设置、创作进度和小说档案都绑定在独立工作区中。</p></div><div className="flex gap-2"><button onClick={() => onNew("short")} className="rounded-xl border border-border px-4 py-2.5 text-sm">新建短篇</button><button onClick={() => onNew("serial")} className="rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground">新建长篇连载</button></div></div>
    {catalogError && <div className="flex items-center gap-2 rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"><CircleAlert className="h-4 w-4" />工作流目录暂时无法刷新，已保留本地作品状态。</div>}
    {!project.persisted && <div className="rounded-xl border border-warning/30 bg-warning/10 p-4 text-sm leading-6 text-warning">当前是未保存的新作品草稿。开始第一个工作流步骤后，作品才会登记并出现在作品管理中。</div>}
    <section className={`${cardClass} overflow-hidden bg-gradient-to-br from-primary/15 via-card to-card`}><div className="grid gap-6 p-6 lg:grid-cols-[1fr_0.8fr]"><div><div className="flex items-center gap-2 text-xs text-muted-foreground"><Clock3 className="h-4 w-4" />当前作品</div><div className="mt-4 flex flex-wrap items-center gap-4"><div className="flex h-24 w-20 items-center justify-center rounded-xl bg-primary/15 text-primary"><BookOpen className="h-8 w-8" /></div><div><div className="flex items-center gap-2"><h2 className="text-2xl font-semibold">{project.title}</h2><span className="rounded-full bg-secondary px-2 py-1 text-xs">{project.mode === "serial" ? "长篇连载" : "短篇"}</span></div><p className="mt-2 text-sm text-muted-foreground">当前进度：{progress?.label || stageTitle} · 第 {project.values.chapter_number}</p><p className="mt-1 text-sm text-muted-foreground">工作区已有 {chapters.length} 章 · {Math.max(totalChars, 0).toLocaleString()} 字符</p></div></div><button onClick={onContinue} className="mt-5 flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground">继续创作 <ArrowRight className="h-4 w-4" /></button>{project.mode === "serial" && chapters.length > 0 && <button disabled={chapterOpening} onClick={onNextChapter} className="mt-3 flex items-center gap-2 rounded-xl border border-primary/40 px-4 py-2.5 text-sm font-semibold text-primary disabled:opacity-50">{chapterOpening ? "正在检查续章…" : `创作第 ${Number(nextChapter)} 章`}</button>}</div><div className="rounded-2xl border border-border/70 bg-background/40 p-5"><div className="flex items-center justify-between text-sm"><span>{project.mode === "serial" ? "当前章节生产进度" : "本篇生产进度"}</span><span className="text-muted-foreground">{progress ? `${progress.percent}%` : "正在核对实际进度…"}</span></div><p role="status" className="mt-2 text-xs leading-6 text-muted-foreground">{progressError ? `进度读取失败：${progressError}` : progress ? `${progress.label} · 已完成 ${progress.completed_count}/${progress.total_count} 个生产步骤` : "按实际任务与产物核对进度"}</p>{progress?.reader_verdict && ["revise", "reject"].includes(progress.reader_verdict) && <p className="mt-2 text-xs text-warning">读者建议返修，已导出不等于质量已通过。</p>}<div className="mt-4 h-2 rounded-full bg-secondary"><div className="h-2 rounded-full bg-primary" style={{ width: `${progress?.percent || 0}%` }} /></div><div className="mt-4 grid grid-cols-3 gap-2 text-center text-xs text-muted-foreground"><div><Gauge className="mx-auto mb-1 h-4 w-4" />{progress?.chapter_count || chapters.length} 章</div><div><ListChecks className="mx-auto mb-1 h-4 w-4" />章节目录</div><div><Sparkles className="mx-auto mb-1 h-4 w-4" />小说档案</div></div>{progress?.can_download && <NovelManuscriptDownload title={project.title} workspace={currentWorkspace} previous={!progress.export_current} />}</div></div></section>
    <section><div className="mb-3 flex items-center justify-between"><div><h2 className="text-lg font-semibold">作品管理</h2><p className="mt-1 text-xs text-muted-foreground">打开作品可查看小说档案；删除会同时移除该作品的实际目录。</p></div><button onClick={onChapters} className="text-sm text-primary">查看当前章节目录</button></div>{projects.length === 0 ? <div className={`${cardClass} p-8 text-center text-sm text-muted-foreground`}>还没有已保存作品。开始当前作品的第一个工作流步骤后，它会出现在这里。</div> : <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{projects.map(item => <ProjectCard key={item.workspace} workspace={item.workspace} title={item.state.title || "未命名作品"} mode={item.state.mode === "serial" ? "serial" : "short"} description={item.state.values?.premise || item.state.values?.genre || "尚未填写故事简介"} chapters={item.progress?.chapter_count ?? (item.workspace.toLowerCase() === currentWorkspace.toLowerCase() ? chapters.length : 0)} progress={item.progress} isCurrent={item.workspace.toLowerCase() === currentWorkspace.toLowerCase()} stageTitle={item.progress?.label || STAGES.find(stage => stage.id === item.state.stageId)?.title || "创作流程"} onOpen={() => onOpenFlowProject(item)} onOpenArchive={() => onOpenArchive(item)} onSettings={() => onSettings(item)} onDelete={() => onDeleteProject(item.workspace)} />)}</div>}</section>
    <aside className={`${cardClass} p-5`}><div className="flex items-center gap-2"><FolderOpen className="h-4 w-4 text-primary" /><h2 className="font-semibold">当前作品工作区</h2></div><p className="mt-2 text-xs leading-5 text-muted-foreground">每本作品的正文、世界观、角色、卷纲、伏笔账本和读者报告都保存在这里。</p><input value={workspaceDraft} onChange={(event) => setWorkspaceDraft(event.target.value)} className={`${inputClass} mt-4 text-xs`} /><button onClick={applyWorkspace} className="mt-2 w-full rounded-xl border border-border px-3 py-2 text-xs">切换工作区</button><div className="mt-5 border-t border-border pt-4 text-xs text-muted-foreground">已发现 {files.length} 个可读文件 · {currentWorkspace}</div></aside>
  </div>;
}

function ProjectCard({ workspace, title, mode, description, chapters, progress, isCurrent, stageTitle, onOpen, onOpenArchive, onSettings, onDelete }: { workspace: string; title: string; mode: Mode; description: string; chapters: number; progress?: NovelProgress; isCurrent: boolean; stageTitle: string; onOpen: () => void; onOpenArchive: () => void; onSettings: () => void; onDelete: () => void }) {
  return <article className={`${cardClass} p-5 ${isCurrent ? "border-primary/50" : ""}`}><div className="flex items-start justify-between gap-3"><div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary"><BookOpen className="h-5 w-5" /></div><div className="flex items-center gap-2"><span className="rounded-full bg-secondary px-2 py-1 text-xs">{mode === "serial" ? "长篇连载" : "短篇"}</span>{isCurrent && <span className="rounded-full bg-success/15 px-2 py-1 text-xs text-success">当前</span>}</div></div><h3 className="mt-4 text-lg font-semibold">{title}</h3><p className="mt-2 min-h-10 text-sm leading-5 text-muted-foreground">{description}</p><p className="mt-3 truncate text-xs text-muted-foreground" title={workspace}>步骤：{stageTitle}</p><div className="mt-4 flex gap-4 text-xs text-muted-foreground"><span>{chapters ? `${chapters} 章` : "尚未产出正文"}</span><span className="truncate" title={workspace}>{workspace}</span></div>{progress && <div className="mt-3"><p className="text-xs text-muted-foreground">{mode === "serial" ? "当前章节生产进度" : "本篇生产进度"} · {progress.percent}%</p><div className="mt-2 h-1.5 rounded-full bg-secondary"><div className="h-1.5 rounded-full bg-primary" style={{width:`${progress.percent}%`}} /></div>{progress.can_download && <NovelManuscriptDownload workspace={workspace} title={title} previous={!progress.export_current} />}</div>}<div className="mt-5 flex gap-2"><button onClick={onOpenArchive} className="flex-1 rounded-xl border border-primary/30 px-3 py-2.5 text-sm text-primary">打开作品档案</button><button onClick={onOpen} className="rounded-xl border border-border px-3 py-2.5 text-sm">创作流程</button><button onClick={onSettings} className="rounded-xl border border-border px-3 py-2.5 text-sm" aria-label={`修改${title}的名称和设置`} title="修改名称和作品设置"><Settings2 className="h-4 w-4" /></button><button onClick={onDelete} className="rounded-xl border border-destructive/30 px-3 py-2.5 text-destructive" title="删除作品目录" aria-label={`删除${title}`}><Trash2 className="h-4 w-4" /></button></div></article>;
}

type ArchiveDescriptor = { path: string; label: string; group: string };
const ARCHIVE_DESCRIPTORS: ArchiveDescriptor[] = [
  { path: "export/manuscript.md", label: "完整小说成品", group: "正文与成品" },
  { path: "meta/story_plan.md", label: "故事总纲", group: "故事结构" },
  { path: "outline/volume_outline.md", label: "卷纲", group: "故事结构" },
  { path: "outline/near_term_outline.md", label: "近期章节纲", group: "故事结构" },
  { path: "meta/character_profiles.md", label: "主要人物档案", group: "人物与关系" },
  { path: "meta/character_voice.md", label: "人物声音锚点", group: "人物与关系" },
  { path: "meta/world_foundation.md", label: "世界观总档案", group: "世界设定" },
  { path: "world/core_laws.json", label: "核心法则", group: "世界设定" },
  { path: "world/space_time.json", label: "时空地理", group: "世界设定" },
  { path: "world/society.json", label: "社会与权力", group: "世界设定" },
  { path: "world/history_culture.json", label: "历史与文化", group: "世界设定" },
  { path: "world/existence.json", label: "存在基础", group: "世界设定" },
  { path: "world/information.json", label: "信息传播", group: "世界设定" },
  { path: "meta/hooks.md", label: "伏笔登记", group: "连续性" },
  { path: "meta/conflict_ledger.md", label: "冲突与伏笔账本", group: "连续性" },
  { path: "meta/debts.md", label: "叙事债务", group: "连续性" },
  { path: "meta/style_profile.md", label: "统一风格基线", group: "写法基线" },
  { path: "learning/active_context.md", label: "当前采用的写法", group: "写法基线" },
];
const archiveGroupColors: Record<string, string> = { "正文与成品": "text-success", "故事结构": "text-primary", "人物与关系": "text-accent", "世界设定": "text-warning", "连续性": "text-destructive", "写法基线": "text-success" };
function ArchiveReading({ item }: { item: ArchiveDescriptor & { content: string } }) {
  const reference = ["人物与关系", "世界设定", "连续性"].includes(item.group);
  return reference && !item.path.endsWith(".json") ? <NovelReferenceContent key={item.path} content={item.content} /> : <NovelArchiveContent content={item.content} structured={item.path.endsWith(".json")} reference={reference} />;
}
const ARCHIVE_STAGE_HINTS = [
  "建立世界观：产出地点、运行规则、社会、历史等世界设定。",
  "创建角色：产出主要人物、信念、关系和声音档案。",
  "规划故事：产出故事引擎（目标、核心矛盾、推进方向）和统一风格基线。",
  "生成卷纲：产出卷纲与近期章节纲。",
  "生成正文与质量审核：持续登记伏笔、冲突、叙事债务和角色状态。",
];

function hasArchiveContent(path: string, content: string): boolean {
  if (!content.trim()) return false;
  if (path === "meta/conflict_ledger.md" && content.includes("当前还没有登记的冲突")) return false;
  if (path === "learning/active_context.md" && content.includes("本阶段没有已选参考写法")) return false;
  if (path.endsWith(".json")) {
    try { const value = JSON.parse(content); if (value === null || (typeof value === "object" && Object.keys(value).length === 0)) return false; }
    catch { /* Display malformed outputs for inspection. */ }
  }
  return content.split(/\r?\n/).some(line => {
    const value = line.trim();
    return value && !value.startsWith("#") && !/^(?:（无）|\(无\)|暂无(?:档案信息)?|无|\[\]|\{\})[。.]?$/.test(value);
  });
}

function ArchiveView({ project, workspace, onBack, onFlow }: { project: Project; workspace: string; onBack: () => void; onFlow: () => void }) {
  const [items, setItems] = useState<Array<ArchiveDescriptor & { content: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [readError, setReadError] = useState("");
  const [selectedPath, setSelectedPath] = useState("");
  const [expandedReading, setExpandedReading] = useState(false);
  const [downloadBusy, setDownloadBusy] = useState(false);
  const [downloadFeedback, setDownloadFeedback] = useState("");
  useEffect(() => { setSelectedPath(""); setItems([]); }, [workspace]);
  const [archiveStatus,setArchiveStatus]=useState('');
  useEffect(() => {
    let active=true;
    setLoading(true);setReadError('');
    const refresh=async()=>{
      const failures:string[]=[];
      const [base,dynamic]=await Promise.all([
        Promise.all(ARCHIVE_DESCRIPTORS.map(async descriptor=>{try{return {...descriptor,content:(await readWorkspaceFile(workflowId('build'),workspace,descriptor.path)).content};}catch(failure){const message=failure instanceof Error?failure.message:String(failure);if(!message.includes('404'))failures.push(message);return null;}})),
        fetchNovelArchiveState(workflowId('build'),workspace).catch(failure=>{failures.push(failure instanceof Error?failure.message:String(failure));return null;})
      ]);
      if(!active)return;
      setItems([...base.filter((item):item is ArchiveDescriptor & {content:string}=>item!==null && hasArchiveContent(item.path,item.content)),...(dynamic?.items || [])]);
      setArchiveStatus(dynamic?.message || '动态档案状态暂时无法读取');
      setReadError(failures.length?`部分档案读取失败：${failures[0]}`:'');setLoading(false);
    };
    void refresh();const timer=window.setInterval(()=>void refresh(),5000);
    const updated=()=>void refresh();window.addEventListener('novel-artifacts-updated',updated);
    return()=>{active=false;window.clearInterval(timer);window.removeEventListener('novel-artifacts-updated',updated);};
  }, [workspace, revision]);
  const groups = Array.from(new Set(items.map(item => item.group)));
  const downloadManuscript = async () => {
    if (downloadBusy) return;
    setDownloadBusy(true); setDownloadFeedback("正在准备成品下载…");
    try {
      const filename = `${project.title.replace(/[<>:"/\\|?*]/g, "_") || "小说成品"}.md`;
      const query = new URLSearchParams({ workflow_id: workflowId("export"), workspace, filename });
      const url = `/api/novel-console/export/download?${query}`;
      const response = await fetch(url, { method: "HEAD" });
      if (!response.ok) throw new Error(response.status === 404 ? "成品文件不存在，请先完成导出。" : `下载服务暂不可用（${response.status}）。`);
      const link = document.createElement("a"); link.href = url; link.download = filename;
      document.body.appendChild(link); link.click(); link.remove();
      setDownloadFeedback(`已发起下载：${filename}。请在浏览器下载列表查看。`);
    } catch (failure) { setDownloadFeedback(failure instanceof Error ? `下载失败：${failure.message}` : "下载失败，请稍后重试。"); }
    finally { setDownloadBusy(false); }
  };
  const selectedItem = items.find(item => item.path === selectedPath) || items[0];
  return <div className="space-y-5">
    <PageHeader eyebrow="小说档案" title={project.title} description="基础设定与当前状态分开查看，动态档案以已确认正文为依据。" onBack={onBack} />
    <p role="status" className="rounded-xl border border-primary/25 bg-primary/5 px-4 py-3 text-sm leading-7">{archiveStatus || "正在核对档案更新进度…"} · 任务完成后自动同步；正文返修后重新审核。</p>
    <div className="flex flex-wrap items-center justify-between gap-3"><p className="text-sm text-muted-foreground" role="status">{loading ? "正在读取档案…" : `已生成 ${items.length} 份档案`}</p><button disabled={loading} onClick={() => setRevision(value => value + 1)} className="flex items-center gap-2 rounded-xl border border-border px-4 py-2 text-sm disabled:opacity-60"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />{loading ? "正在读取…" : "刷新档案"}</button></div>
    {downloadFeedback && <p role="status" className="rounded-xl border border-primary/25 bg-primary/5 p-3 text-sm leading-6 text-primary">{downloadFeedback}</p>}
    {readError && <p role="alert" className="text-sm text-warning">{readError}</p>}
    {!loading && !readError && items.length === 0 && <section className={`${cardClass} p-10 text-center`}><FileText className="mx-auto h-8 w-8 text-muted-foreground/60" /><p className="mt-3 text-sm text-muted-foreground">暂无档案信息</p><p className="mt-2 text-xs text-muted-foreground">完成建立世界观、创建角色或规划故事等步骤后，这里会自动显示对应资料。</p><button onClick={onFlow} className="mt-5 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground">进入创作流程</button></section>}
    {selectedItem && <div className="grid items-start gap-5 lg:grid-cols-[220px_minmax(0,1fr)]">
      <nav aria-label="小说档案目录" className={`${cardClass} max-h-[65vh] overflow-auto p-3 lg:sticky lg:top-24`}><div className="space-y-4">{groups.map(group => <div key={group}><h2 className={`mb-1 px-3 text-xs font-semibold ${archiveGroupColors[group] || "text-muted-foreground"}`}>{group}</h2><div className="flex flex-wrap gap-1 lg:block">{items.filter(item => item.group === group).map(item => <button key={item.path} aria-current={selectedItem.path === item.path ? "page" : undefined} onClick={() => setSelectedPath(item.path)} className={`rounded-lg px-3 py-2.5 text-left text-sm transition-colors lg:w-full ${selectedItem.path === item.path ? "bg-primary/10 font-medium text-primary" : "text-foreground/80 hover:bg-secondary/60"}`}>{item.label}</button>)}</div></div>)}</div></nav>
      <section key={selectedItem.path} className={`${cardClass} min-w-0 overflow-hidden`}><header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4 sm:px-8"><div><p className={`text-xs font-semibold ${archiveGroupColors[selectedItem.group] || "text-muted-foreground"}`}>{selectedItem.group}</p><h2 className="mt-1 text-xl font-semibold">{selectedItem.label}</h2></div><div className="flex gap-2"><button onClick={() => setExpandedReading(true)} className="rounded-lg border border-border px-3 py-2 text-sm hover:bg-secondary/60">展开阅读</button>{selectedItem.path === "export/manuscript.md" && <button disabled={downloadBusy} onClick={() => void downloadManuscript()} className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">{downloadBusy ? "正在准备下载…" : "下载小说成品"}</button>}</div></header><div className="max-h-[75vh] overflow-auto overscroll-contain px-5 py-6 sm:px-8"><div className="mx-auto max-w-[76ch]"><ArchiveReading item={selectedItem} /></div></div></section>
    </div>}
    {expandedReading && selectedItem && <NovelReadingDialog title={selectedItem.label} onClose={() => setExpandedReading(false)}><ArchiveReading item={selectedItem} /></NovelReadingDialog>}
    <details className="text-sm text-muted-foreground"><summary className="cursor-pointer">档案在哪些步骤生成？</summary><div className="mt-3 space-y-2">{ARCHIVE_STAGE_HINTS.map((hint, index) => <p key={index} className="leading-6">{hint}</p>)}</div></details>
    {items.length > 0 && <button onClick={onFlow} className="rounded-xl border border-primary/30 px-4 py-2.5 text-sm text-primary">回到创作流程</button>}
  </div>;
}

function ChapterView({ project, chapters, removedChapters, workspace, chapterOpening, nextChapter, onNextChapter, onBack, onOpen, onRepair, onRegenerate, onDelete, onCreateMissing }: {
  project: Project; chapters: Array<{ number: string; file: WorkspaceFile }>; workspace: string;
  removedChapters: string[];
  chapterOpening: boolean; nextChapter: string; onNextChapter: () => void;
  onBack: () => void; onOpen: (chapter: string) => void; onRepair: (chapter: string) => void;
  onRegenerate: (chapter: string) => void; onDelete: (chapter: string) => void; onCreateMissing: (chapter: string) => void;
}) {
  return <div className="space-y-5">
    <PageHeader eyebrow="章节目录" title={`${project.title} · 章节目录`} description="按章阅读和返修，续章沿用本书设定与写法。" onBack={onBack} />
    {project.mode === "serial" && <button disabled={chapterOpening} onClick={onNextChapter} className="flex items-center gap-2 rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground disabled:opacity-50">{chapterOpening ? <Loader2 className="h-4 w-4 animate-spin"/> : <Play className="h-4 w-4"/>}{chapterOpening ? "正在检查续章…" : `创作第 ${Number(nextChapter)} 章`}</button>}
    <section className={`${cardClass} divide-y divide-border`}>
      {!chapters.length && <p className="p-8 text-center text-sm text-muted-foreground">工作区里还没有章节正文。</p>}
      {[...chapters].sort((a,b) => a.number.localeCompare(b.number)).map(item => <div key={item.number} className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
        <div><h2 className="font-semibold">第 {Number(item.number)} 章</h2><p className="mt-1 text-xs text-muted-foreground">{item.file.character_count == null ? "待统计字数" : `${item.file.character_count.toLocaleString()} 字符`}</p></div>
        <div className="flex flex-wrap gap-2"><button onClick={() => onOpen(item.number)} className="rounded-lg border border-border px-4 py-2 text-sm">阅读与评估</button><button disabled={chapterOpening} onClick={() => onRepair(item.number)} className="rounded-lg border border-primary/30 px-4 py-2 text-sm text-primary disabled:opacity-50">返修第 {Number(item.number)} 章</button><button disabled={chapterOpening} onClick={() => onRegenerate(item.number)} className="rounded-lg border border-border px-4 py-2 text-sm disabled:opacity-50">重新生成第 {Number(item.number)} 章</button><button disabled={chapterOpening} onClick={() => onDelete(item.number)} className="flex items-center gap-1 rounded-lg border border-destructive/30 px-3 py-2 text-sm text-destructive disabled:opacity-50"><Trash2 className="h-3.5 w-3.5"/>删除第 {Number(item.number)} 章</button></div>
      </div>)}
      {removedChapters.map(number => <div key={number} className="flex flex-wrap items-center justify-between gap-4 px-5 py-4"><div><h2 className="font-semibold">第 {Number(number)} 章 · 待重新生成</h2><p className="mt-1 text-xs text-muted-foreground">正文已删除，章节计划与旧稿备份保留。</p></div><button disabled={chapterOpening} onClick={() => onCreateMissing(number)} className="rounded-lg border border-primary/30 px-4 py-2 text-sm text-primary disabled:opacity-50">生成第 {Number(number)} 章</button></div>)}
    </section>
    <p className="text-sm leading-7 text-muted-foreground">阅读旧章不会切换正在创作的章节。返修会备份原稿，只修改指定章；人物、伏笔与后续衔接会重新核对。</p>
    <p className="text-xs text-muted-foreground">当前工作区：{workspace}</p>
  </div>;
}

function PageHeader({ eyebrow, title, description, onBack }: { eyebrow: string; title: string; description: string; onBack: () => void }) { return <div className="flex flex-wrap items-start justify-between gap-4"><div><button onClick={onBack} className="mb-3 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft className="h-3 w-3" />返回作品</button><p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">{eyebrow}</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">{title}</h1><p className="mt-2 text-sm text-muted-foreground">{description}</p></div></div>; }

function ReviewView({ project, workspace, chapter, opening, onBack, onFlow, onRepair, onAssess, onAudit, onRepairFlow }: { project: Project; workspace: string; chapter: string; opening: boolean; onBack: () => void; onFlow: () => void; onAssess: () => void; onAudit: () => void; onRepairFlow: () => void; onRepair: (feedbackPath: string, modelId: string) => Promise<void> }) {
  const [content, setContent] = useState("");
  const [report, setReport] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  const [readError, setReadError] = useState("");
  useEffect(() => {
    let active = true;
    setLoading(true);
    setReport(null);
    setContent("");
    setReadError("");
    const chapterPromise = readWorkspaceFile(workflowId("mvp"), workspace, `story/${chapter}/chapter.md`);
    const reportPromise = getNovelReaderReport(workflowId('reader-sim'), workspace, chapter);
    void Promise.allSettled([chapterPromise, reportPromise]).then(([chapterResult, reportResult]) => {
      if (!active) return;
      if (chapterResult.status === "fulfilled") setContent(chapterResult.value.content);
      else setContent("");
      if (reportResult.status === "fulfilled") {
        try {
          const value: unknown = reportResult.value.report;
          if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("报告格式不完整");
          setReport(value as Record<string, unknown>);
        } catch { setReadError("评估报告格式不完整，请重新执行模拟读者步骤。"); }
      } else {
        const message = reportResult.reason instanceof Error ? reportResult.reason.message : String(reportResult.reason);
        if (!message.includes("404")) setReadError(`评估读取失败：${message}`);
      }
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [chapter, workspace, revision]);
  return <div className="space-y-5">
    <PageHeader eyebrow="模拟读者" title={`第 ${Number(chapter)} 章 · 章节阅读`} description="阅读已有正文，查看读者评估或继续返修。" onBack={onBack} />
    <div className="flex flex-wrap items-center gap-3"><button disabled={loading} onClick={() => setRevision(value => value + 1)} className="flex items-center gap-2 rounded-xl border border-border px-4 py-2 text-sm disabled:opacity-60"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />{loading ? "正在读取评估…" : "刷新评估"}</button>{readError && <p role="alert" className="text-sm text-warning">{readError}</p>}</div>
    <div className="flex flex-wrap gap-3"><button disabled={loading || opening || !content} onClick={onAssess} className="rounded-xl border border-primary/30 px-4 py-2.5 text-sm text-primary disabled:opacity-50">{opening ? "正在准备…" : `重新评估第 ${Number(chapter)} 章`}</button><button disabled={loading || opening || !content} onClick={onAudit} className="rounded-xl border border-border px-4 py-2.5 text-sm disabled:opacity-50">重新审核档案</button><p className="self-center text-xs text-muted-foreground">缺少有效报告时先重新评估，再规划返修。</p></div>
    <div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
      <section className={`${cardClass} p-6`}><div className="flex items-center justify-between"><h2 className="font-semibold">正文预览</h2><span className="text-xs text-muted-foreground">{loading ? "正在读取" : content ? `${content.replace(/\s/g, "").length.toLocaleString()} 字符` : "暂无正文"}</span></div><div className="mt-5 max-h-[800px] overflow-auto pr-3"><NovelArchiveContent content={content || "还没有找到这一章的正文。可以回到创作流程生成。"} /></div></section>
      <aside className="space-y-5"><NovelRepairPanel key={`${workspace}:${chapter}`} workspace={workspace} chapter={chapter} project={{title:project.title, mode:project.mode, values:{...project.values, chapter_number:chapter, prev_chapter:String(Number(chapter)-1).padStart(4,"0")}, selected_candidate_ids:project.selected}} readerSummary={String(report?.summary || "")} ready={!loading && !!content && !!report} onRepair={onRepair} onFlow={onRepairFlow} /><section className={`${cardClass} p-5`}><div className="flex items-center gap-2"><Headphones className="h-4 w-4 text-primary" /><h2 className="font-semibold">模拟读者评估</h2></div><NovelReaderReport report={report} /><button onClick={onFlow} className="mt-5 w-full rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground">返回创作流程</button></section></aside>
    </div>
  </div>;
}

function DistillationView({catalog,onRefreshCatalog,onLibrary}:{catalog:CatalogItem[];onRefreshCatalog:()=>Promise<void>;onLibrary:()=>void}) {
  const [job,setJob]=useState<{workspace:string;project:Project}>(()=>{try{const saved=JSON.parse(localStorage.getItem('xs2-distillation-job')||'null');if(saved?.workspace&&saved?.project)return saved;}catch{/* invalid job */}const workspace=`data/workspaces/reference-jobs/job-${Date.now()}`;return {workspace,project:{...restore(workspace),title:'参考资料',stageId:'reference-distillation',autoNext:false,persisted:false}};});
  const [jobFiles,setJobFiles]=useState<WorkspaceFile[]>([]),[feedback,setFeedback]=useState('');
  useEffect(()=>{localStorage.setItem('xs2-distillation-job',JSON.stringify(job));},[job]);
  const refresh=useCallback(async()=>{setJobFiles((await listWorkspaceFiles(workflowId('reference-distillation'),job.workspace)).files);},[job.workspace]);
  useEffect(()=>{void refresh().catch(()=>{});},[refresh]);
  const update=useCallback<React.Dispatch<React.SetStateAction<Project>>>(value=>setJob(current=>({...current,project:typeof value==='function'?value(current.project):value})),[]);
  const fresh=async()=>{try{const ref=job.project.refs['reference-distillation'];if(ref){const result=await getTask(ref.workflow_id,ref.task_id);if(!terminal.includes(result.task.status))throw new Error('当前资料仍在蒸馏，请等任务结束后再新建。');}const workspace=`data/workspaces/reference-jobs/job-${Date.now()}`;setJob({workspace,project:{...restore(workspace),title:'参考资料',stageId:'reference-distillation',autoNext:false,persisted:false}});setFeedback('已新建独立资料任务，之前的结果和小说资料均保留。');}catch(error){setFeedback(error instanceof Error?error.message:'新建失败，请重试。');}};
  return <div className="space-y-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><h1 className="text-2xl font-semibold">资料蒸馏</h1><p className="mt-2 text-sm leading-7 text-muted-foreground">独立分析参考作品，完成后自动进入共享写法库。不会登记成一本小说，也不改变当前作品的创作进度。</p></div><button onClick={()=>void fresh()} className="rounded-lg border border-border px-4 py-2 text-sm">新建资料任务</button></div>{feedback&&<p role="status" className="text-sm text-primary">{feedback}</p>}<label className="block max-w-xl text-sm">资料名称<input aria-label="资料名称" className={inputClass+' mt-2'} disabled={!!job.project.refs['reference-distillation']} value={job.project.title} onChange={e=>update(current=>({...current,title:e.target.value}))}/></label><FlowView key={job.workspace} moduleOnly project={job.project} setProject={update} stages={[STAGES[0]]} currentStage={STAGES[0]} catalog={catalog} workspace={job.workspace} files={jobFiles} chapters={[]} onHome={onLibrary} onRefreshCatalog={onRefreshCatalog} onRefreshFiles={refresh} onReview={onLibrary} onLibrary={onLibrary}/></div>;
}

function FlowView({ chapterOpening = false, nextChapterNumber, onContinueChapter, moduleOnly = false, project, setProject, stages, currentStage, catalog, workspace, files, chapters, onHome, onRefreshCatalog, onRefreshFiles, onReview, onLibrary, onReferenceAdopted, onOpenAssistant, onOpenReference }: { chapterOpening?: boolean; nextChapterNumber?: string; onContinueChapter?: (chapter: string, action?: string, automatic?: boolean) => Promise<void>; moduleOnly?: boolean; project: Project; setProject: React.Dispatch<React.SetStateAction<Project>>; stages: StageMeta[]; currentStage: StageMeta; catalog: CatalogItem[]; workspace: string; files: WorkspaceFile[]; chapters: Array<{ number: string; file: WorkspaceFile }>; onHome: () => void; onRefreshCatalog: () => Promise<void>; onRefreshFiles: () => Promise<void>; onReview: () => void; onLibrary: () => void; onReferenceAdopted?: () => Promise<void>; onOpenAssistant?: () => void; onOpenReference?: (advisor?: boolean) => void }) {

  const [referenceFiles, setReferenceFiles] = useState<File[]>([]); const [importUrl, setImportUrl] = useState(""); const [importUrlBusy, setImportUrlBusy] = useState(false); const [importUrlError, setImportUrlError] = useState(""); const [importWarnings, setImportWarnings] = useState<string[]>([]); const [importChapters, setImportChapters] = useState<Array<{ index: number; title: string; url: string; selected?: boolean }>>([]); const [urlImported, setUrlImported] = useState(false); const [libraryName, setLibraryName] = useState(""); const [saveMessage, setSaveMessage] = useState(""); const [savingLibrary, setSavingLibrary] = useState(false); const [refreshingCatalog, setRefreshingCatalog] = useState(false); const [refreshingFiles, setRefreshingFiles] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
const [task, setTask] = useState<any>(null); const [verified, setVerified] = useState(false); const [launching, setLaunching] = useState(false); const [error, setError] = useState(""); const [actionFeedback, setActionFeedback] = useState(""); const [preview, setPreview] = useState(""); const [modelPending, setModelPending] = useState(false); const [candidateSet, setCandidateSet] = useState<CandidateSet | null>(null); const [showAllFields, setShowAllFields] = useState(false);
  const launchGuard = useRef(false); const autoAdvancedKey = useRef(""); const autoStartedKey = useRef(""); const autoStartIndex = useRef<number | null>(null); const autoPublishedKey = useRef(""); const outlineConfirmed = useRef(false); const outlineSnapshot = useRef<{taskId: string; content: string; inventory: ReturnType<typeof outlineImpactInventory>} | null>(null); const outlineReportedTask = useRef(""); const filesRefreshedTask = useRef(""); const adoptionNotified = useRef(""); const [outlineImpactOpen, setOutlineImpactOpen] = useState(false); const [outlineUpdateReport, setOutlineUpdateReport] = useState<(ReturnType<typeof compareNovelOutlines> & {inventory: ReturnType<typeof outlineImpactInventory>}) | null>(null); const outlineInventory = useMemo(() => outlineImpactInventory(files), [files]); const stageIndex = Math.max(0, stages.findIndex((item) => item.id === currentStage.id)); const ref = project.refs[currentStage.id]; const workflow = catalog.find((item) => item.workflow_id === workflowId(currentStage.id)); const busy = launching || (!!task && !terminal.includes(task.status)); const done = verified && task?.status === "completed" && task.workflow_id === workflowId(currentStage.id) && task.task_id === ref?.task_id; const outlineHasExisting = currentStage.id === "outline" && (files.some(file => file.path === "outline/near_term_outline.md") || (done && preview.trim().length > 0)); const variables = useMemo(() => workflow?.definition?.variables || [], [workflow]);
  // URL 导入结果写在作品工作区里，页面刷新后文件选择状态会丢失；通过工作区文件恢复“已有语料”状态。
  const importedCorpusPresent = files.some((file) => file.path === "references/url-imported-corpus.txt") || project.values.reference_path === "references/url-imported-corpus.txt";
  const [adoptedIds, setAdoptedIds] = useState<string[]>([]);
  const [adoptionReady, setAdoptionReady] = useState(false);
  const [adoptedStyles, setAdoptedStyles] = useState<string[]>([]);
  const [adoptedConflicts, setAdoptedConflicts] = useState<string[]>([]);
  const [adoptedReferences, setAdoptedReferences] = useState<Array<{choice_id: string; title: string; guidance: string}>>([]);
  const pendingWriting = [...project.selected.filter(id => !adoptedIds.includes(id)), ...(project.selectedStyles || []).filter(id => !adoptedStyles.includes(id)), ...(project.selectedConflicts || []).filter(id => !adoptedConflicts.includes(id))];
  const canAddWriting = currentStage.id === "adopt-reference" && adoptionReady && pendingWriting.length > 0;
  // 提取复杂表达式供依赖数组使用（eslint exhaustive-deps 要求静态可检查）
  const adoptReferenceTaskId = project.refs["adopt-reference"]?.task_id;
  useEffect(() => {
    let active = true;
    setAdoptionReady(false);
    setAdoptedIds([]);
    void getNovelAdoptedWriting(workflowId("build"), workspace).then(result => {
      if (!active) return;
      const ids = result.selected_candidate_ids || [];
      setAdoptedIds(ids); setAdoptedStyles(result.selected_style_ids || []); setAdoptedConflicts(result.selected_conflict_ids || []); setAdoptedReferences([...(result.styles || []), ...(result.conflicts || [])]);
      setAdoptionReady(true);
      setProject(current => {
        const selected = retainAdoptedWriting(current.selected, ids);
        const selectedStyles = retainAdoptedWriting(current.selectedStyles || [], result.selected_style_ids || []);
        const selectedConflicts = retainAdoptedWriting(current.selectedConflicts || [], result.selected_conflict_ids || []);
        return JSON.stringify([selected, selectedStyles, selectedConflicts]) === JSON.stringify([current.selected, current.selectedStyles || [], current.selectedConflicts || []]) ? current : {...current, selected, selectedStyles, selectedConflicts};
      });
    }).catch(failure => { if (active) setError(`读取已采用写法失败：${failure instanceof Error ? failure.message : String(failure)}`); });
    return () => { active = false; };
  }, [workspace, currentStage.id, adoptReferenceTaskId, done, setProject]);
  useEffect(() => {
    if (currentStage.id === "reference-distillation" && importedCorpusPresent && !urlImported) setUrlImported(true);
  }, [currentStage.id, importedCorpusPresent, urlImported]);
  const visibleVariables = useMemo(() => { const inputs = variables.filter((field) => field.source_type !== "output" && !field.hidden && field.type !== "file" && !(currentStage.id === "reference-distillation" && field.key === "reference_path")); if (showAllFields) return inputs; const preferred = currentStage.preferredFields || []; const selected = inputs.filter((field) => preferred.includes(field.key) || field.required); return selected.length ? selected : inputs.slice(0, 6); }, [currentStage.id, currentStage.preferredFields, showAllFields, variables]);
  const available = !!workflow; const update = (key: string, value: string) => setProject((current) => ({ ...current, configuredFields: [...new Set([...(current.configuredFields || []), key])], values: { ...current.values, [key]: value } })); const valueFor = (field: WorkflowVariable) => project.values[field.key] ?? field.default ?? FALLBACK_DEFAULTS[field.key] ?? "";
  // ref 由 project.refs[currentStage.id] 派生，每次渲染都是新对象；补全会让 3 秒轮询
  // effect 在每次 project 变化时重启定时器。ref?.task_id / ref?.workflow_id 已覆盖语义。
  useEffect(() => { let active = true; setTask(null); setVerified(false); setPreview(""); setError(""); filesRefreshedTask.current = ""; if (!ref) return; const refresh = async () => { try { const result = await getTask(ref.workflow_id, ref.task_id); if (!active) return; setTask(result.task); if (result.task.status === "running" || result.task.status === "pending" || result.task.status === "pre_running") setActionFeedback(`任务 ${result.task.task_id}：${statusLabel(result.task.status)}…`); if (result.task.status === "failed") setActionFeedback(`任务 ${result.task.task_id} 执行失败，请查看错误详情后重试。`); if (result.task.status === "completed") { setActionFeedback(`任务 ${result.task.task_id} 已完成，正在读取产物…`); try { const output = currentStage.id === "reader-sim" ? {content:JSON.stringify((await getNovelReaderReport(ref.workflow_id, workspace, project.values.chapter_number || "0001")).report)} : await readWorkflowWorkspaceFile(ref.workflow_id, ref.task_id, currentStage.artifact.replace("{chapter}", project.values.chapter_number || "0001")); if (active) { setPreview(output.content); setVerified(!!output.content.trim()); setActionFeedback(`任务 ${result.task.task_id} 已完成，产物已就绪。`); if (filesRefreshedTask.current !== result.task.task_id) { filesRefreshedTask.current = result.task.task_id; void onRefreshFiles().catch(() => {}); } } } catch { if (active) { setVerified(false); setError("任务已结束，但没有读到本步骤的产物。自动推进已暂停，请刷新作品资料或重新执行。"); } } } } catch (failure) { if (active) setError(failure instanceof Error ? failure.message : "读取任务失败"); } }; void refresh(); const timer = window.setInterval(refresh, 3000); return () => { active = false; window.clearInterval(timer); }; }, [currentStage.artifact, currentStage.id, onRefreshFiles, project.values.chapter_number, ref?.task_id, ref?.workflow_id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!done || currentStage.id !== "outline" || !ref?.task_id || outlineReportedTask.current === ref.task_id) return;
    const previous = outlineSnapshot.current;
    if (!previous || previous.taskId !== ref.task_id) return;
    outlineReportedTask.current = ref.task_id;
    const result = compareNovelOutlines(previous.content, preview);
    setOutlineUpdateReport({...result, inventory: previous.inventory});
    if (!result.comparisonAvailable) {
      setActionFeedback("大纲已更新。章节标题格式无法自动逐章比较，请通读新大纲并核对已有计划、正文与伏笔档案。旧版已备份。生成正文前仍会检查设定与大纲是否一致。");
      return;
    }
    const changed = result.changedChapters.map(Number);
    setActionFeedback(changed.length
      ? `大纲已更新，检测到第 ${changed.join("、")} 章发生变化。请核对对应计划、正文与档案后再继续。旧版已备份。`
      : "大纲已更新，逐章对比未发现章节内容变化。旧版已备份。");
  }, [currentStage.id, done, preview, ref?.task_id]);
  useEffect(() => {
    if (!moduleOnly || currentStage.id !== "adopt-reference" || !done || !ref?.task_id ||
        project.pendingReferenceAdoption !== ref.task_id || adoptionNotified.current === ref.task_id) return;
    adoptionNotified.current = ref.task_id;
    void onReferenceAdopted?.();
  }, [currentStage.id, done, moduleOnly, onReferenceAdopted, project.pendingReferenceAdoption, ref?.task_id]);
  useEffect(() => {
    if (!done || currentStage.id !== "reference-distillation" || !ref?.task_id || autoPublishedKey.current === ref.task_id) return;
    autoPublishedKey.current = ref.task_id;
    void (async () => {
      // 后端按来源合并并校验分析内容；同一资料的新分析也必须提交，不能只按来源跳过。
      const result = await publishWritingLibrary({
        workflow_id: workflowId("reference-distillation"),
        workspace,
        name: libraryName.trim() || `${project.title}写法`,
        automatic: true,
        task_id: ref.task_id,
        genres: project.values.genre ? [project.values.genre] : [],
        pov: project.values.narrative_pov ? [project.values.narrative_pov] : [],
        language: project.values.language || "中文",
      });
      if (!result.item) {
        setSaveMessage("这份结果已从写法库删除，不会自动重新加入。需要恢复时可点击下方手动保存。");
        return;
      }
      setLibraryName(result.item.name);
      setSaveMessage(`已自动保存「${result.item.name}」，可在共享写法库中复用。`);
      setActionFeedback("蒸馏结果已自动登记到共享写法库。");
    })().catch((failure) => {
      autoPublishedKey.current = "";
      setSaveMessage(failure instanceof Error ? `自动登记失败：${failure.message}` : `自动登记失败：${String(failure)}`);
    });
  }, [currentStage.id, done, libraryName, preview, project.title, project.values.genre, project.values.language, project.values.narrative_pov, ref?.task_id, workspace]);
  // 提取复杂表达式供依赖数组使用（eslint exhaustive-deps 要求静态可检查）
  const distillRefTaskId = project.refs["reference-distillation"]?.task_id;
  useEffect(() => { let active = true; setCandidateSet(null); if (!["reference-distillation", "novel-advisor", "style-compatibility-advisor", "adopt-reference"].includes(currentStage.id)) return; void getNovelReferenceCandidates(workflowId("build"), workspace).then(output => { if(active) setCandidateSet(output as CandidateSet); }).catch(() => { if(active) setCandidateSet(null); }); return () => { active=false; }; }, [currentStage.id, workspace, project.libraryRefs, distillRefTaskId]);
  const skipPreparation = () => moduleOnly ? onHome() : setProject(current => ({ ...current, directionConfirmed:true, autoLaunchStage:"", autoPauseReason:"", index:stages.findIndex(stage => stage.id === "build"), stageId:"build" }));
  const inspectUrl = async () => { setImportUrlError(""); setImportWarnings([]); setImportUrlBusy(true); try { const result = await inspectNovelImportUrl(importUrl.trim()); setImportChapters(result.chapters); setImportWarnings(result.warnings || []); if (!result.chapters.length && !result.has_page_text) throw new Error("番茄页面没有识别到正文或章节"); } catch (failure) { setImportUrlError(failure instanceof Error ? failure.message : String(failure)); } finally { setImportUrlBusy(false); } };
  const fetchUrl = async () => { setImportUrlError(""); setImportUrlBusy(true); try { const selected = importChapters.filter(chapter => chapter.selected); const result = await importNovelUrl({ workflow_id:workflowId("reference-distillation"), workspace, url:importUrl.trim(), source_mode:project.values.reference_mode || "auto", chapters:selected }); setUrlImported(true); setImportWarnings(result.warnings || importWarnings); setProject(current => ({...current, writingMode:"distill", values:{...current.values, reference_path:result.path}})); setImportUrlError(`已导入 ${result.chapter_count} 个番茄小说章节，可开始蒸馏。`); } catch (failure) { setImportUrlError(failure instanceof Error ? failure.message : String(failure)); } finally { setImportUrlBusy(false); } };
  const saveLibrary = async () => { if (savingLibrary) return; setSaveMessage(""); setSavingLibrary(true); try { const result = await publishWritingLibrary({ workflow_id:workflowId("reference-distillation"), workspace, name:libraryName.trim() || project.title + "写法", genres:[project.values.genre], language:project.values.language }); setSaveMessage(`已保存「${result.item.name}」，可在其他作品中复用。`); } catch(failure) { setSaveMessage(failure instanceof Error ? failure.message : String(failure)); } finally { setSavingLibrary(false); } };
  const refreshCatalogNow = async () => { if (refreshingCatalog) return; setRefreshingCatalog(true); setActionFeedback("正在刷新工作流目录…"); try { await onRefreshCatalog(); setActionFeedback("工作流目录已刷新，页面状态已同步。"); } catch (failure) { setActionFeedback(failure instanceof Error ? `刷新失败：${failure.message}` : "工作流目录刷新失败，请稍后重试。"); } finally { setRefreshingCatalog(false); } };
  const refreshFilesNow = async () => { if (refreshingFiles) return; setRefreshingFiles(true); setActionFeedback("正在刷新作品资料…"); try { await onRefreshFiles(); setActionFeedback("作品资料已刷新。"); } catch (failure) { setActionFeedback(failure instanceof Error ? `刷新失败：${failure.message}` : "作品资料刷新失败，请稍后重试。"); } finally { setRefreshingFiles(false); } };
  const selectedChapterCount = importChapters.filter((chapter) => chapter.selected).length;
  const launch = useCallback(async () => {
    if (launchGuard.current || busy || modelPending || (done && !canAddWriting && currentStage.id !== "outline")) return;
    if (currentStage.id === "outline" && outlineHasExisting && !outlineConfirmed.current) {
      const reason = "检测到已有大纲。重新生成前请确认它会影响后续章节计划、伏笔核对和档案回写；已有正文不会被自动覆盖。";
      setOutlineImpactOpen(true);
      setActionFeedback(reason);
      setProject(current => ({ ...current, autoNext: false, autoScope: "manual", autoLaunchStage: "", autoPauseReason: reason }));
      return;
    }
    launchGuard.current = true; setLaunching(true); setError(""); setActionFeedback("已收到请求，正在准备当前步骤…");
    let previousOutline = "";
    try {
      if (!available) throw new Error("当前工作流还没有被插件目录提供，请刷新工作流目录后重试。");
      if (currentStage.id === "mvp") {
        setActionFeedback("正文启动前先核对上一章档案、当前大纲和已采用的章节方案…");
        const check = await checkNovelContinuation(workflowId("build"), workspace, project.values.chapter_number || "0001");
        if (!check.ready) {
          const nextId = check.action || "outline";
          const nextIndex = Math.max(0, stages.findIndex(stage => stage.id === nextId));
          const needsPlanRefresh = nextId === "outline";
          setProject(current => ({
            ...current,
            continuationIssue: check,
            index: nextIndex,
            stageId: nextId,
            values: { ...current.values, chapter_number: check.chapter, prev_chapter: String(Math.max(0, Number(check.chapter) - 1)).padStart(4, "0") },
            assistantPlan: needsPlanRefresh ? chapterPlanRefreshPrompt(check.chapter, check.message) : current.assistantPlan,
            autoNext: false,
            autoScope: "manual",
            autoLaunchStage: "",
            autoPauseReason: `正文没有启动。${check.message}${needsPlanRefresh ? " 请先让创作助手重新规划并采用本章方案，然后回到正文生成。" : " 请先完成提示的前置步骤，再重新启动正文。"}`,
          }));
          setActionFeedback(`已在正文生成前完成检查，尚未创建正文任务。${check.message}`);
          if (needsPlanRefresh) onOpenAssistant?.();
          return;
        }
        setProject(current => ({ ...current, continuationIssue: null, autoPauseReason: "" }));
      }
      setActionFeedback("正在读取工作流定义…");
      const definition = (await getWorkflow(workflowId(currentStage.id))).definition;
      const parameters: Record<string, string> = { ...project.values, conflict_plan_mode: project.mode === "short" ? "short_full" : (["serial_opening", "serial_chapter", "serial_arc"].includes(project.values.conflict_plan_mode) ? project.values.conflict_plan_mode : "serial_chapter") }; if (project.values.world_direction?.trim() || project.values.source_idea?.trim() || project.values.advisor_guidance?.trim()) parameters.premise = premiseWithWorldDirection(project.values); if (currentStage.id === "reference-distillation" || currentStage.id === "style-compatibility-advisor") parameters.source_mode = project.values.reference_mode || "auto"; if (currentStage.id === "style-compatibility-advisor") parameters.target_work_mode = project.mode;
       if (currentStage.id === "outline" && outlineHasExisting) {
        setActionFeedback("正在备份旧大纲，避免新版本覆盖后无法回看…");
         previousOutline = await backupCurrentOutline(workspace, done ? preview : "");
        if (!previousOutline.trim()) throw new Error("旧大纲没有读到有效内容，已停止更新以避免误覆盖。请刷新作品资料后重试。");
       }
       if (currentStage.id === "reference-distillation") {
        setActionFeedback("正在准备参考语料…");
        if (!referenceFiles.length && !urlImported && !importedCorpusPresent) throw new Error("请先选择参考文件或导入公开网址。");
        const sources = await Promise.all(referenceFiles.map(async(file,i) => ({ id:`source-${i+1}`, name:file.name, text:await file.text() })));
        if (urlImported || importedCorpusPresent) { parameters.reference_path = "references/url-imported-corpus.txt"; } else { if(sources.some(source => !source.text.trim() || source.text.includes("\ufffd"))) throw new Error("参考文件需为非空 UTF-8 文本，请检查编码。");
        parameters.reference_path="references/imported-corpus.txt";
        await writeNovelWorkspaceText(workflowId(currentStage.id), workspace, parameters.reference_path, sources.map(source => `===== SOURCE FILE: ${source.name} =====\n\n${source.text}`).join("\n\n")); }
        setProject(current => ({...current, writingMode:"distill", values:{...current.values, reference_path:parameters.reference_path}}));
      }
  if (currentStage.id === "adopt-reference") { if (!candidateSet) throw new Error("还没有读取到蒸馏结果。"); if (!adoptionReady) throw new Error("正在核对已采用写法，请稍后再确认。"); const adaptationError = validateReferenceAdaptations([...(candidateSet.style_choices || []), ...(candidateSet.conflict_choices || [])], [...(project.selectedStyles || []), ...(project.selectedConflicts || [])], [...adoptedStyles, ...adoptedConflicts], project.referenceAdaptations || {}); if (adaptationError) throw new Error(adaptationError); parameters.selection_path = "learning/selection.json"; parameters.selection_json = JSON.stringify({ candidates_sha256: candidateSet.candidates_sha256, selected_candidate_ids: retainAdoptedWriting(project.selected, adoptedIds),
    reference_choices_sha256:candidateSet.reference_choices_sha256,
    selected_style_ids:retainAdoptedWriting(project.selectedStyles || [], adoptedStyles),
    selected_conflict_ids:retainAdoptedWriting(project.selectedConflicts || [], adoptedConflicts),
    reference_adaptations:project.referenceAdaptations || {} }); } const inputs = Object.fromEntries((definition.variables || []).filter((field) => field.source_type !== "output" && (field.type !== "file" || field.key === "author_feedback_file") && parameters[field.key] !== undefined).map((field) => [field.key, parameters[field.key]])); const missing = (definition.variables || []).find((field) => field.required && !field.hidden && field.type !== "file" && !(inputs[field.key] ?? field.default ?? "").trim()); if (missing) throw new Error(`请先填写${missing.name || missing.key}。`); setActionFeedback("参数已校验，正在创建任务…"); const repairModels = (project.repairReviewOnly || (project.readerRepairCount || 0) > 0) && project.repairModel && ["polish", "reader-sim"].includes(currentStage.id) ? repairNodeModels(definition, project.repairModel) : undefined; const created = await createTask(workflowId(currentStage.id), inputs, undefined, undefined, workspace, undefined, undefined, repairModels); const nextRef = { workflow_id: workflowId(currentStage.id), task_id: created.task_id };
        if (currentStage.id === "outline") {
          outlineSnapshot.current = previousOutline.trim() ? { taskId: created.task_id, content: previousOutline, inventory: outlineInventory } : null;
          outlineConfirmed.current = false;
          setOutlineImpactOpen(false);
          setOutlineUpdateReport(null);
        }
        setProject((current) => ({ ...current, persisted: true, autoLaunchStage: "", autoPauseReason: "", refs: { ...current.refs, [currentStage.id]: nextRef }, directionConfirmed: current.directionConfirmed || currentStage.id === "adopt-reference", advisorAccepted: currentStage.id === "novel-advisor" ? true : current.advisorAccepted })); setActionFeedback(`任务 ${created.task_id} 已创建，正在启动…`); await runTask(workflowId(currentStage.id), created.task_id); setTask({ ...nextRef, status: "running", name: definition.name }); setActionFeedback(`任务 ${created.task_id} 已启动，正在执行…`); } catch (failure) { if (currentStage.id === "outline") outlineConfirmed.current = false; const errorMsg = failure instanceof Error ? failure.message : "启动失败"; const isBusy = errorMsg.includes('仍有创作或评估任务正在处理') || errorMsg.includes('正在处理'); setError(isBusy ? "⚠️ 当前有其他任务正在运行，请等待完成后再启动新任务。可以刷新工作流查看任务状态。" : errorMsg); setActionFeedback(isBusy ? "启动被阻止：有任务正在执行。等待完成或停止该任务后重试。" : "启动没有完成，请查看下方提示后重试。"); setProject(current => ({ ...current, autoNext: false, autoScope: "manual", autoLaunchStage: "", autoPauseReason: current.autoNext || current.autoLaunchStage ? (isBusy ? "有其他任务正在运行，自动流程已暂停。" : "自动启动失败，请处理错误后重新启用。") : "" })); } finally { launchGuard.current = false; setLaunching(false); } }, [available, busy, canAddWriting, adoptionReady, adoptedIds, adoptedStyles, adoptedConflicts, candidateSet, currentStage.id, done, importedCorpusPresent, outlineHasExisting, outlineInventory, preview, project.selected, project.selectedStyles, project.selectedConflicts, project.referenceAdaptations, project.mode, project.values, project.repairReviewOnly, project.repairModel, project.readerRepairCount, modelPending, referenceFiles, urlImported, workspace, stages, setProject, onOpenAssistant]);
  let readerVerdict = "";
  if (currentStage.id === "reader-sim") { try { readerVerdict = JSON.parse(preview).verdict || ""; } catch { /* Wait for a valid report. */ } }
  const readerNeedsRepair = ["revise", "reject"].includes(readerVerdict);
  const repairProject = useRef(project);
  repairProject.current = project;
  const polishIndex = stages.findIndex(item => item.id === 'polish');
  useEffect(() => {
    if (!project.autoNext || !project.autoRepairPlanId || currentStage.id !== 'reader-sim') return;
    let active = true;
    let timer: number | undefined;
    const requestId = project.autoRepairPlanId;
    const chapter = project.values.chapter_number || '0001';
    const poll = async () => {
      try {
        if (polishIndex < 0) throw new Error('缺少原有润色工作流，无法执行返修。');
        setActionFeedback('AI 正在读取本章正文和完整读者报告，规划本轮返修；方案完成后自动修改并复评…');
        const result = await advanceRepairPlan(requestId, {
          active: () => active,
          history: async () => (await fetchNovelAssistantHistory(workflowId('build'), workspace)).entries,
          ask: async () => (await askNovelAssistant({workflow_id:workflowId('build'), workspace,
            request_id:requestId, purpose:'reader_repair', chapter, stage:'自动下一步 · 读者返修规划',
            project:{title:repairProject.current.title, mode:repairProject.current.mode, values:repairProject.current.values, selected_candidate_ids:repairProject.current.selected},
            question:`请基于第${chapter}章当前正文与完整读者报告，制定可执行的定向返修方案，逐项回应问题、保留约束并列出复评验收点。自动流程将按这份方案修改本章。`})).entry,
          apply: entry => applyNovelRepairPlan({workflow_id:workflowId('polish'), workspace, entry_id:entry.id, plan:entry.reply}),
        });
        if (!active) return;
        if (result) {
          setActionFeedback('AI 方案已保存，正在按方案启动润色返修，完成后重新评估…');
          setProject(current => current.autoNext && current.autoRepairPlanId === requestId
            ? beginReaderRepair(current, polishIndex, result.feedback_path, result.model_id, false) : current);
        } else timer = window.setTimeout(() => void poll(), 2500);
      } catch (failure) {
        if (!active) return;
        const reason = `自动返修已暂停：${failure instanceof Error ? failure.message : String(failure)}`;
        setActionFeedback(reason);
        setProject(current => ({...current, autoNext:false, autoScope:'manual', autoLaunchStage:'', autoRepairPlanId:'', autoPauseReason:reason}));
      }
    };
    void poll();
    return () => {active = false; if (timer) window.clearTimeout(timer);};
  }, [project.autoNext, project.autoRepairPlanId, project.values.chapter_number, currentStage.id, workspace, polishIndex, setProject]);
  useEffect(() => {
    if (!project.autoNext || !task || !terminal.includes(task.status) || task.status === 'completed' || task.task_id !== ref?.task_id) return;
    const reason = `当前步骤${statusLabel(task.status)}，自动推进已暂停。请查看任务详情并处理后再继续。`;
    setActionFeedback(reason);
    setProject(current => ({...current, autoNext:false, autoScope:'manual', autoLaunchStage:'', autoRepairPlanId:'', autoPauseReason:reason}));
    // task 每 3 秒轮询更新（引用变化），补全会让暂停检测 effect 周期性重跑并重复写
    // actionFeedback/setProject；task?.status / task?.task_id 已是精确语义。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.autoNext, task?.status, task?.task_id, ref?.task_id, setProject]);
  const completeAndNext = useCallback(() => {
    if (!done || stageIndex >= stages.length - 1) return;
    const pause = (reason: string) => { autoStartIndex.current = null; setActionFeedback(reason); setProject(current => ({ ...current, autoNext: false, autoScope: "manual", autoLaunchStage: "", autoPauseReason: reason })); };
    if (currentStage.id === "reader-sim") {
      const decision = readerRepairDecision(readerVerdict, project.autoNext, project.readerRepairCount || 0, project.autoRepairLimit || 2);
      if (decision.pauseReason) { pause(decision.pauseReason); return; }
      if (decision.repair) {
        if (!project.autoNext) {onReview(); return;}
        setActionFeedback('读者建议返修，正在准备基于本章正文和完整报告的 AI 返修方案…');
        setProject(current => ({...current, autoRepairPlanId: current.autoRepairPlanId || crypto.randomUUID(), autoLaunchStage:'', autoPauseReason:''}));
        return;
      }
    }
    const nextIndex = stageIndex + 1;
    const startAutomatically = project.autoNext && project.autoScope !== "manual" && !["reference-distillation", "novel-advisor", "adopt-reference"].includes(stages[nextIndex]?.id);
    autoStartIndex.current = startAutomatically ? nextIndex : null;
    setProject(current => {
      return { ...current, index: nextIndex, stageId: stages[nextIndex]?.id, autoLaunchStage: startAutomatically ? stages[nextIndex]?.id : "", autoPauseReason: "",
        completed: [...new Set([...current.completed, currentStage.id])],
        advisorAccepted: currentStage.id === "novel-advisor" ? true : current.advisorAccepted };
    });
  }, [currentStage.id, done, project.autoNext, project.autoScope, project.readerRepairCount, project.autoRepairLimit, readerVerdict, stageIndex, stages, setProject, onReview]);
  const nextChapter = useCallback(async () => {
    if (!onContinueChapter || chapterOpening) return;
    await onContinueChapter(String(Number(project.values.chapter_number || "1") + 1).padStart(4, "0"), "write", project.autoNext && project.autoScope === "serial_batch");
  }, [onContinueChapter, chapterOpening, project.values.chapter_number, project.autoNext, project.autoScope]);
  useEffect(() => {
    if (!project.autoNext || project.autoScope === "manual" || !done) return;
    const key = `${currentStage.id}:${ref?.task_id || ""}`;
    if (autoAdvancedKey.current === key) return;
    autoAdvancedKey.current = key;
    if (project.assessmentOnly && currentStage.id === 'reader-sim') {
      setProject(state => ({...state, assessmentOnly:false, autoNext:false, autoScope:'manual', autoLaunchStage:'',
        completed:[...new Set([...state.completed, 'reader-sim'])]}));
      onReview(); return;
    }
    if (project.repairReviewOnly && currentStage.id === 'reader-sim') {
      if (readerVerdict === 'pass') {
        const qualityIndex = stages.findIndex(stage => stage.id === 'post-hoc');
        setProject(state => ({...state, index:qualityIndex, stageId:'post-hoc', autoLaunchStage:'post-hoc',
          completed:[...new Set([...state.completed, 'reader-sim'])], autoPauseReason:''}));
        return;
      }
      setProject(state => ({...state, repairReviewOnly:false, autoNext:false, autoScope:'manual', autoLaunchStage:'',
        completed:[...new Set([...state.completed, 'reader-sim'])], autoPauseReason:'本次返修与复评已完成，请查看新报告后决定后续操作。'}));
      onReview();
      return;
    }
    if (project.repairReviewOnly && currentStage.id === 'post-hoc') {
      setProject(state => ({...state, repairReviewOnly:false, autoNext:false, autoScope:'manual', autoLaunchStage:'',
        completed:[...new Set([...state.completed, 'post-hoc'])], autoPauseReason:'返修复评已通过，人物、世界与伏笔档案已同步更新。'}));
      onReview();
      return;
    }
    if (currentStage.id === "export") {
      if (shouldAdvanceSerialChapter(project.mode, project.autoScope, project.autoChapterStarted, project.autoChapterLimit, project.values.chapter_ending_mode)) { void nextChapter(); }
      else { setProject(state => ({ ...state, autoNext: false, autoScope: "manual", autoLaunchStage: "", completed: [...new Set([...state.completed, "export"])] })); setActionFeedback(project.mode === "serial" ? "指定章节已完成并导出。" : "本篇已完成并导出。"); }
      return;
    }
    if (stageIndex < stages.length - 1) completeAndNext();
  }, [completeAndNext, currentStage.id, done, nextChapter, project.autoChapterLimit, project.autoChapterStarted, project.autoNext, project.autoScope, project.mode, project.repairReviewOnly, project.assessmentOnly, project.values.chapter_ending_mode, ref?.task_id, stageIndex, stages, readerVerdict, setProject, onReview]);
  useEffect(() => {
    if (!project.autoNext || project.autoScope === "manual" || (autoStartIndex.current !== stageIndex && project.autoLaunchStage !== currentStage.id) || ref || launching || task) return;
    const key = `${currentStage.id}:${stageIndex}:${project.values.chapter_number}:${project.readerRepairCount || 0}`;
    if (autoStartedKey.current === key) return;
    if (!available) {
      if (catalog.length > 0) { const reason = "当前步骤的工作流尚未安装，自动推进已暂停。请刷新工作流目录后重试。"; setActionFeedback(reason); setProject(current => ({ ...current, autoNext: false, autoScope: "manual", autoLaunchStage: "", autoPauseReason: reason })); }
      return;
    }
    autoStartedKey.current = key; autoStartIndex.current = null;
    void launch();
  }, [available, catalog.length, currentStage.id, launch, launching, project.autoNext, project.autoScope, project.autoLaunchStage, project.readerRepairCount, project.values.chapter_number, ref, stageIndex, task, setProject]);
  const setAuto = (checked: boolean) => { autoAdvancedKey.current = ""; autoStartedKey.current = ""; setProject(current => ({ ...current, autoNext: checked, autoScope: checked ? (current.mode === "serial" ? "serial_batch" : "short_full") : "manual", autoChapterStarted: checked && current.mode === "serial" ? 1 : null, autoPauseReason: "", autoLaunchStage: "", autoRepairPlanId: "", repairReviewOnly: false })); };
  const advisorMode = !moduleOnly && currentStage.id === "novel-advisor";
  const hasStoryFacts = files.some(file => /^(meta\/(world_foundation|character_profiles)|story\/.*chapter\.md)/.test(file.path));
  const fieldsForStage = currentStage.id === "adopt-reference" ? [] : visibleVariables.filter(field => !(["novel-advisor", "story-plan", "outline"].includes(currentStage.id) && ["conflict_plan_mode", "conflict_point_count", "foreshadowing_count"].includes(field.key)));
  const manualControls = (<>        {!moduleOnly && currentStage.id !== "reference-distillation" && <div className="mt-5 rounded-xl border border-border bg-secondary/30 p-4"><div className="flex flex-wrap items-center justify-between gap-3"><label className="flex items-center gap-2 text-sm font-medium">作品模式<select value={project.mode} disabled={stageIndex > 0} onChange={(event) => { const mode = event.target.value as Mode; setProject((current) => ({ ...current, mode, autoScope: mode === "serial" ? "serial_batch" : "short_full", values: { ...current.values, conflict_plan_mode: mode === "serial" ? "serial_opening" : "short_full" } })); }} className="ml-2 rounded-lg border border-border bg-background px-2 py-1.5 text-xs"><option value="short">短篇</option><option value="serial">长篇连载</option></select></label><span className="text-xs text-muted-foreground">{project.mode === "serial" ? "本次可自动推进指定章数" : "本次可自动完成本篇"}</span></div></div>}
        {project.mode === "serial" && ["mvp", "polish", "reader-sim"].includes(currentStage.id) && <label className="mt-4 block text-sm">当前章节结尾<select aria-label="当前章节结尾" disabled={busy} value={project.values.chapter_ending_mode || "continue"} onChange={event => update("chapter_ending_mode", event.target.value)} className={`${inputClass} mt-2`}><option value="continue">普通连载章节，继续推进故事</option><option value="book_final">本书终章，完成全书收尾</option></select><span className="mt-1 block text-xs text-muted-foreground">只有终章才收束全书；导出和本批次最后一章不代表完结。</span></label>}
        {["novel-advisor", "story-plan", "outline"].includes(currentStage.id) && <div className={cardClass + " mt-5 border-primary/25 bg-primary/5 p-4"}><div className="flex items-start gap-3"><ListChecks className="mt-0.5 h-4 w-4 shrink-0 text-primary" /><div className="min-w-0 flex-1"><p className="text-sm font-semibold">冲突与伏笔规划</p><p className="mt-1 text-xs leading-5 text-muted-foreground">每个冲突都要有前置目标、伏笔或已知信息。解决后留下代价，再由代价触发下一阻碍；章节后验会把状态写回冲突与伏笔账本，防止后续遗忘。</p><div className="mt-3 grid gap-3 sm:grid-cols-3"><label className="text-xs"><span className="mb-1 block font-medium">规划范围</span><select value={project.values.conflict_plan_mode || (project.mode === "serial" ? "serial_opening" : "short_full")} onChange={(event) => update("conflict_plan_mode", event.target.value)} className={inputClass}>{project.mode === "short" ? <option value="short_full">短篇全文</option> : <><option value="serial_opening">长篇前几章</option><option value="serial_chapter">长篇当前章节</option><option value="serial_arc">长篇当前卷</option></>}</select></label><label className="text-xs"><span className="mb-1 block font-medium">冲突点数量</span><input type="number" min={1} max={12} value={project.values.conflict_point_count || (project.mode === "serial" ? "4" : "3")} onChange={(event) => update("conflict_point_count", event.target.value)} className={inputClass} /></label><label className="text-xs"><span className="mb-1 block font-medium">伏笔数量</span><input type="number" min={0} max={12} value={project.values.foreshadowing_count || (project.mode === "serial" ? "3" : "2")} onChange={(event) => update("foreshadowing_count", event.target.value)} className={inputClass} /></label></div><p className="mt-3 text-[11px] text-muted-foreground">账本生成后会持续更新；短篇按全文维护，长篇按章节和卷回读。</p></div></div></div>}
        {currentStage.id === "export" && done && <NovelManuscriptDownload title={project.title} workspace={workspace} />}{currentStage.id === "reference-distillation" && <div className="mt-5 space-y-4">{!moduleOnly && <div className="grid gap-2 sm:grid-cols-3"><button disabled={busy} onClick={skipPreparation} className="rounded-xl border border-border p-4 text-sm">{adoptedIds.length ? "保留已采用写法继续创作" : "原创起步"}<br /><span className="text-xs text-muted-foreground">直接建立世界与角色</span></button><button disabled={busy} onClick={onLibrary} className="rounded-xl border border-border p-4 text-sm">复用写法库<br /><span className="text-xs text-muted-foreground">选择已有结果，无需重蒸馏</span></button><button className="rounded-xl border border-primary/40 p-4 text-sm" onClick={() => setProject((current) => ({ ...current, writingMode: "distill" }))}>新资料蒸馏<br /><span className="text-xs text-muted-foreground">分析语言、结构和叙事</span></button></div>}<label className="block"><span className="mb-2 block text-sm">参考语料类型</span><select aria-label="参考语料类型" value={project.values.reference_mode || "auto"} disabled={busy || done} onChange={(event) => update("reference_mode", event.target.value)} className={inputClass}><option value="auto">自动识别</option><option value="short_full">短篇全文</option><option value="serial_chapters">长篇章节样本</option></select><span className="mt-1 block text-xs text-muted-foreground">短篇重点分析前几百字和全文回收；长篇重点分析开局、章节追读和卷级持续性。</span></label><div className="rounded-xl border border-primary/25 bg-primary/5 p-4"><span className="mb-2 block text-sm">从番茄小说导入</span><div className="flex flex-wrap gap-2"><input aria-label="番茄小说作品网址" value={importUrl} onChange={(event) => setImportUrl(event.target.value)} placeholder="粘贴 fanqienovel.com 的作品详情页或正文页网址" className={`${inputClass} min-w-[260px] flex-1`} disabled={busy || done || importUrlBusy} /><button onClick={() => void inspectUrl()} disabled={!importUrl.trim() || busy || done || importUrlBusy} className="rounded-xl border border-primary/40 px-3 py-2 text-sm">{importUrlBusy && importChapters.length === 0 ? "读取中…" : "识别章节"}</button></div>{importChapters.length > 0 && <div className="mt-3 max-h-48 space-y-1 overflow-auto rounded-lg border border-border bg-background/60 p-2">{importChapters.map((chapter) => <label key={`${chapter.index}-${chapter.url}`} className="flex items-center gap-2 px-2 py-1 text-xs"><input type="checkbox" checked={chapter.selected === true} onChange={(event) => setImportChapters((current) => current.map((item) => item.url === chapter.url ? { ...item, selected: event.target.checked } : item))} /><span className="truncate">{chapter.index}. {chapter.title}</span></label>)}</div>}<div className="mt-3 flex flex-wrap items-center gap-2"><button onClick={() => void fetchUrl()} disabled={!importUrl.trim() || busy || done || importUrlBusy || (importChapters.length > 0 && !importChapters.some((chapter) => chapter.selected))} className="rounded-xl bg-primary px-3 py-2 text-sm text-primary-foreground">{importUrlBusy && importChapters.length > 0 ? "正在导入所选章节…" : importChapters.length ? `导入所选章节（已选 ${selectedChapterCount} 章）` : "导入页面正文"}</button>{importUrlBusy && importChapters.length > 0 && <span role="status" className="text-xs text-muted-foreground">正在逐章读取已选 {selectedChapterCount} 章，可能需要几十秒，请保持页面打开。</span>}{importUrlError && <span className="text-xs text-primary">{importUrlError}</span>}</div>{importWarnings.map((warning, index) => <p key={index} className="mt-2 text-xs text-warning">{warning}</p>)}<p className="mt-2 text-xs text-muted-foreground">只读取番茄小说无需登录的公开页面；遇到验证码、登录或访问限制时请改用官方导出或本地文件。</p></div><label className="block rounded-xl border border-dashed border-primary/40 p-4"><span className="mb-3 block text-sm">选择参考文件（可多选 TXT / Markdown）</span><input aria-label="选择参考文件" type="file" multiple accept=".txt,.md,text/plain,text/markdown" disabled={busy || done} onChange={(event) => { const picked = Array.from(event.target.files || []); setReferenceFiles((current) => [...current, ...picked.filter((file) => !current.some((item) => item.name === file.name && item.size === file.size))]); event.target.value = ""; }} /></label>{referenceFiles.map((file, index) => <div key={`${file.name}-${index}`} className="flex items-center justify-between text-xs"><span>{file.name} · {(file.size / 1024).toFixed(1)} KB</span><button disabled={busy || done} onClick={() => setReferenceFiles((current) => current.filter((_, currentIndex) => currentIndex !== index))} className="text-primary">移除</button></div>)}{importedCorpusPresent && <p className="rounded-lg bg-success/10 px-3 py-2 text-xs text-success">已恢复当前资料任务的导入语料，可以开始蒸馏。</p>}<p className="text-xs text-muted-foreground">保留每份来源的证据；相同写法合并，差异作为变体保留。大部头可分卷导入，样本不足时只给暂定结论。</p>{done && <div className="space-y-2"><input aria-label="写法库名称" value={libraryName} onChange={(event) => setLibraryName(event.target.value)} className={inputClass} placeholder="给这份写法取一个便于复用的名称" /><button onClick={() => void saveLibrary()} disabled={savingLibrary} className="rounded-xl border border-primary/40 px-4 py-2 text-sm">{savingLibrary ? "正在保存…" : "保存到共享写法库"}</button><p className="text-xs text-primary">{saveMessage}</p></div>}</div>}
        {currentStage.optional && !["reference-distillation", "novel-advisor"].includes(currentStage.id) && stageIndex < stages.length - 1 && !busy && <button className="mt-4 text-xs text-primary" onClick={() => setProject((current) => ({ ...current, index: stageIndex + 1, stageId: stages[stageIndex + 1]?.id }))}>跳过此可选步骤</button>}
        {currentStage.id === "adopt-reference" && <CandidateChooser candidateSet={candidateSet} selected={project.selected} project={project} adoptedStyles={adoptedStyles} adoptedConflicts={adoptedConflicts} adoptedReferences={adoptedReferences} adoptedIds={adoptedIds} disabled={busy || !adoptionReady} setProject={setProject} />}
        {currentStage.id !== "adopt-reference" && <div className="mt-6 space-y-4">{fieldsForStage.map((field) => <WorkflowField key={field.key} field={field} value={valueFor(field)} disabled={busy || (done && currentStage.id !== "outline") || ["chapter_number", "prev_chapter"].includes(field.key)} onChange={(value) => update(field.key, value)} />)}{variables.filter((field) => !field.hidden && field.source_type !== "output" && field.type !== "file").length > fieldsForStage.length && <button onClick={() => setShowAllFields((value) => !value)} className="flex items-center gap-1 text-xs text-primary">{showAllFields ? "收起参数" : "查看全部参数"}<ChevronDown className={`h-3 w-3 transition ${showAllFields ? "rotate-180" : ""}`} /></button>}</div>}
        {actionFeedback && <p role="status" aria-live="polite" className={`novel-task-feedback mt-5 flex items-center gap-2 rounded-xl border border-primary/25 bg-primary/5 p-3 text-sm text-primary ${error ? "" : busy ? "" : ""}`} data-state={error ? "failed" : busy ? "running" : done ? "completed" : "idle"}><span className={`h-2 w-2 rounded-full ${busy ? "animate-pulse bg-primary" : "bg-success"}`} />{actionFeedback}</p>}{error && <p role="alert" className="mt-3 flex gap-2 rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"><CircleAlert className="h-4 w-4 shrink-0" />{error}</p>}
        <div className="mt-6 flex flex-wrap gap-3">{(!done || canAddWriting || currentStage.id === "outline") && <button onClick={() => void launch()} disabled={busy || modelPending || (currentStage.id === "adopt-reference" && (!candidateSet || !adoptionReady || !(candidateSet.candidates.length || candidateSet.style_choices?.length || candidateSet.conflict_choices?.length)))} title={!available ? "工作流目录仍在加载，点击后会显示具体状态" : undefined} className="flex items-center gap-2 rounded-xl bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground disabled:opacity-50">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}{busy ? "正在执行" : currentStage.id === "outline" && done ? "重新生成大纲" : task?.status === "failed" ? "重新执行" : currentStage.id === "adopt-reference" ? pendingWriting.length ? `确认新增 ${pendingWriting.length} 项参考` : "确认保留已有写法" : advisorMode ? "运行详细顾问报告" : "开始当前步骤"}</button>}{done && !canAddWriting && stageIndex < stages.length - 1 && <button onClick={completeAndNext} className="flex items-center gap-2 rounded-xl bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground">{readerNeedsRepair ? "进入定向返修" : currentStage.id === "post-hoc" ? "进入导出" : "下一步"}<ArrowRight className="h-4 w-4" /></button>}{done && project.mode === "serial" && project.values.chapter_ending_mode !== "book_final" && ["post-hoc", "export"].includes(currentStage.id) && <button disabled={chapterOpening} onClick={() => void nextChapter()} className="rounded-xl border border-primary/40 px-5 py-3 text-sm font-semibold text-primary">继续写下一章</button>}{currentStage.id === "reader-sim" && <button onClick={onReview} className="rounded-xl border border-border px-5 py-3 text-sm">查看章节正文</button>}</div>
  </>);
  return <div className="space-y-6">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <button onClick={onHome} className="mb-3 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft className="h-3 w-3" />{moduleOnly ? "返回写法库" : "返回作品"}</button>
        <div className="flex flex-wrap items-center gap-3"><h1 className="text-3xl font-semibold tracking-tight">{project.title}</h1><span className="rounded-full bg-secondary px-2.5 py-1 text-xs">{currentStage.id === "reference-distillation" ? "资料分析" : project.mode === "serial" ? "长篇连载" : "短篇"}</span><span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs text-primary">工作流版本 {workflow?.version ?? "—"}</span></div>
        <p className="mt-2 text-sm text-muted-foreground">{moduleOnly ? currentStage.id === "reference-distillation" ? "独立资料分析，完成后进入共享写法库" : "可选的参考准备，不改变本书创作进度" : advisorMode ? "先确定故事方向，再开始正式创作" : project.mode === "serial" ? `第 ${project.values.chapter_number} 章 · 自动计划最多推进 ${project.autoChapterLimit} 章` : "短篇可以在确认方向后自动完成本篇"}</p>
      </div>
      <div className="flex flex-wrap gap-2"><button onClick={() => void refreshCatalogNow()} disabled={refreshingCatalog} className="rounded-xl border border-border px-3 py-2 text-xs"><RefreshCw className={`mr-1 inline h-3.5 w-3.5 ${refreshingCatalog ? "animate-spin" : ""}`} />{refreshingCatalog ? "刷新中…" : "刷新工作流"}</button><button onClick={() => void refreshFilesNow()} disabled={refreshingFiles} className="rounded-xl border border-border px-3 py-2 text-xs"><FolderOpen className={`mr-1 inline h-3.5 w-3.5 ${refreshingFiles ? "animate-pulse" : ""}`} />{refreshingFiles ? "读取中…" : "刷新作品资料"}</button></div>
    </div>
    {!moduleOnly && project.mode === "serial" && onContinueChapter && chapters.length > 0 && <section className={`${cardClass} flex flex-wrap items-center justify-between gap-3 p-4`}><div><p className="font-medium">长篇章节管理</p><p className="mt-1 text-xs text-muted-foreground">当前生产：第 {Number(project.values.chapter_number)} 章。阅读和指定返修可在章节目录中选择。</p></div><button disabled={busy || chapterOpening} onClick={() => void onContinueChapter(nextChapterNumber || String(Number(project.values.chapter_number)+1).padStart(4,"0"))} className="rounded-lg border border-primary/30 px-4 py-2.5 text-sm text-primary disabled:opacity-50">{chapterOpening ? "正在检查续章…" : `创作第 ${Number(nextChapterNumber || Number(project.values.chapter_number)+1)} 章`}</button></section>}
    {project.assessmentOnly && <p role="status" className="rounded-xl border border-primary/30 p-4 text-sm text-primary">仅重新评估指定章节，完成后回到该章读者页，不会生成下一章或修改正文。</p>}
    {project.autoRepairPlanId && <p role="status" className="rounded-xl border border-primary/30 bg-primary/10 p-4 text-sm leading-7 text-primary"><Loader2 className="mr-2 inline h-4 w-4 animate-spin"/>AI 正在根据本章正文和完整读者报告制定第 {(project.readerRepairCount || 0) + 1} 轮返修方案。随后会按方案修改、重新评估；通过后才继续审核与导出。请保持本页打开，方案与状态会保存。</p>}
    {project.repairReviewOnly && <p role="status" className="rounded-xl border border-primary/30 bg-primary/10 p-4 text-sm leading-7 text-primary">正在按已确认的 AI 方案返修本章：润色返修 → 模拟读者复评 → 通过后同步档案，再回到读者页。未通过时暂停并展示问题。请保持本页打开。</p>}
    {!moduleOnly && !advisorMode && <section className={`${cardClass} p-4`}><div className="flex flex-wrap items-center justify-between gap-4"><div className="flex items-center gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary"><Sparkles className="h-5 w-5" /></div><div><p className="font-medium">自动下一步</p><p className="text-xs text-muted-foreground">从当前步骤开始，自动推进；有问题时先由 AI 规划，再返修复评，通过后导出。需保持创作页面打开；关闭后回来可恢复。</p></div></div><div className="flex flex-wrap items-center gap-3"><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={project.autoNext} disabled={busy} onChange={(event) => setAuto(event.target.checked)} />启用</label>{project.autoNext && <><label className="flex items-center gap-2 text-xs">每章最多返修<select aria-label="每章自动返修上限" value={project.autoRepairLimit || 2} onChange={event => setProject(current => ({ ...current, autoRepairLimit: Number(event.target.value) }))} className="rounded-lg border border-border bg-background px-2 py-2">{[1,2,3,5].map(count => <option key={count} value={count}>{count} 次</option>)}</select></label><select value={project.autoScope} onChange={(event) => setProject((current) => ({ ...current, autoScope: event.target.value as AutoScope }))} className="rounded-lg border border-border bg-background px-2 py-2 text-xs"><option value="short_full">自动完成本篇</option><option value="serial_batch">自动推进指定章节</option></select>{project.mode === "serial" && <select value={project.autoChapterLimit} onChange={(event) => setProject((current) => ({ ...current, autoChapterLimit: Number(event.target.value), autoChapterStarted: 1 }))} className="rounded-lg border border-border bg-background px-2 py-2 text-xs"><option value={1}>1 章</option><option value={3}>3 章</option><option value={5}>5 章</option><option value={10}>10 章</option></select>}</>}</div></div></section>}
    {project.autoPauseReason && <p role="alert" className="rounded-xl border border-warning/25 bg-warning/5 p-4 text-sm leading-7 text-warning">{project.autoPauseReason}</p>}
    {project.continuationIssue && <section role="alert" className={`${cardClass} border-warning/35 bg-warning/5 p-5`}><div className="flex items-start gap-3"><CircleAlert className="mt-0.5 h-5 w-5 shrink-0 text-warning"/><div className="min-w-0 flex-1"><h3 className="font-semibold">正文前置检查已拦截</h3><p className="mt-2 text-sm leading-7">第 {Number(project.continuationIssue.chapter)} 章尚不能安全启动：{project.continuationIssue.message}</p>{project.continuationIssue.action === "outline" ? <><p className="mt-2 text-sm leading-7 text-muted-foreground">原采用方案仍会保留供对照。重新生成近期大纲本身不会更新这份章节方案；需要在剧情讨论中重新规划并确认采用，正文生成前会再次自动核对。</p><button onClick={() => { setProject(current => ({...current, assistantPlan:chapterPlanRefreshPrompt(project.continuationIssue!.chapter, project.continuationIssue!.message)})); onOpenAssistant?.(); }} className="mt-4 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground">打开创作助手，重新规划第 {Number(project.continuationIssue.chapter)} 章</button></> : <p className="mt-2 text-sm text-muted-foreground">请先完成左侧「{stages.find(stage => stage.id === project.continuationIssue?.action)?.title || project.continuationIssue.action}」步骤，然后重新启动正文。</p>}</div></div></section>}
    {outlineImpactOpen && currentStage.id === "outline" && <section role="alertdialog" aria-label="确认更新大纲的影响" className={`${cardClass} border-warning/35 bg-warning/5 p-5`}><div className="flex items-start gap-3"><CircleAlert className="mt-0.5 h-5 w-5 shrink-0 text-warning" /><div className="min-w-0 flex-1"><h3 className="font-semibold">重新生成大纲前，请确认影响范围</h3><p className="mt-2 text-sm leading-7 text-muted-foreground">系统发现本书已经有一版大纲。新大纲会作为新的规划依据，旧版会自动备份；它不会静默改写已经写出的正文或已确认档案。</p><div className="mt-4 grid gap-3 sm:grid-cols-3"><div className="rounded-xl border border-border bg-background/50 p-3"><p className="text-xs text-muted-foreground">已有章节计划</p><p className="mt-1 text-lg font-semibold">{outlineInventory.plannedChapters.length} 章</p></div><div className="rounded-xl border border-border bg-background/50 p-3"><p className="text-xs text-muted-foreground">已有正文</p><p className="mt-1 text-lg font-semibold">{outlineInventory.writtenChapters.length} 章</p></div><div className="rounded-xl border border-border bg-background/50 p-3"><p className="text-xs text-muted-foreground">已确认档案</p><p className="mt-1 text-lg font-semibold">{outlineInventory.confirmedChapters.length} 章</p></div></div><div className="mt-3 space-y-1 rounded-lg bg-background/40 p-3 text-xs leading-6 text-muted-foreground"><p>章节计划：{chapterListSummary(outlineInventory.plannedChapters)}</p><p>已写正文：{chapterListSummary(outlineInventory.writtenChapters)}</p><p>已确认档案：{chapterListSummary(outlineInventory.confirmedChapters)}</p></div><ul className="mt-4 space-y-2 text-sm leading-6 text-muted-foreground"><li>• 章节计划：受影响章节需要重新核对；如果已采用的方案依据已变化，正文生成前会拦截并引导你重新讨论、采用。</li><li>• 正文与档案：已写内容和已确认事实会保留，不会被自动覆盖或删除；需要你决定是否返修，返修后再重新审核档案。</li><li>• 伏笔与后续：除直接变更章节外，后续章节的因果、人物动机、冲突升级和伏笔回收也要复核。</li><li>• 移除章节：移出新大纲不等于删除已有计划或正文，需明确保留、改写或归档。</li><li>• 旧版大纲：会自动备份，方便回看和恢复。</li></ul><div className="mt-5 flex flex-wrap gap-3"><button onClick={() => { outlineConfirmed.current = true; setOutlineImpactOpen(false); setActionFeedback("已确认影响范围，正在重新生成大纲…"); void launch(); }} disabled={busy} className="rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground">确认影响并重新生成</button><button onClick={() => { setOutlineImpactOpen(false); setActionFeedback("已保留当前大纲，未创建更新任务。现有正文与档案不受影响。"); }} disabled={busy} className="rounded-xl border border-border px-4 py-2.5 text-sm">暂不更新</button></div></div></div></section>}
    {outlineUpdateReport && currentStage.id === "outline" && (
      <section role="status" className={`${cardClass} border-primary/25 bg-primary/5 p-5`}>
        <div className="flex items-start gap-3">
          <Check className="mt-0.5 h-5 w-5 shrink-0 text-success" />
          <div className="min-w-0 flex-1">
            <h3 className="font-semibold">大纲更新影响检查</h3>
            {outlineUpdateReport.comparisonAvailable ? (
              <>
                <p className="mt-2 text-sm leading-7">
                  逐章比较结果：<strong>{outlineChangeSummary(outlineUpdateReport.changes)}</strong>。
                </p>
                {outlineUpdateReport.changes.length > 0 ? (
                  <ul className="mt-3 space-y-2">
                    {outlineChapterImpacts(outlineUpdateReport.changes, outlineUpdateReport.inventory).map((impact) => (
                      <li key={`${impact.chapter}-${impact.type}`} className="rounded-lg border border-border bg-background/40 p-3 text-sm leading-6">
                        <strong>第 {Number(impact.chapter)} 章 · {outlineImpactLabel(impact.type)}</strong>
                        <span className="mt-1 block text-muted-foreground">{outlineArtifactImpact(impact)}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-3 rounded-lg border border-success/20 bg-success/5 p-3 text-sm leading-6 text-muted-foreground">
                    本次逐章内容没有变化，现有章节计划、正文和确认档案无需因大纲文本变更而重做。
                  </p>
                )}
                <p className="mt-3 text-xs leading-6 text-muted-foreground">
                  变更章节之后已有的内容会列为连带复核项；正文、章节计划和确认档案都会保留，不会自动删除或覆盖。
                </p>
              </>
            ) : (
              <p className="mt-2 text-sm leading-7">
                无法按章节标题自动比较，请人工通读新旧大纲，并核对已有章节计划、正文、伏笔和档案。
              </p>
            )}
            <div className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
              <span>更新前已有计划：<strong>{outlineUpdateReport.inventory.plannedChapters.length}</strong> 章</span>
              <span>更新前已有正文：<strong>{outlineUpdateReport.inventory.writtenChapters.length}</strong> 章</span>
              <span>更新前已确认档案：<strong>{outlineUpdateReport.inventory.confirmedChapters.length}</strong> 章</span>
            </div>
            <p className="mt-3 text-xs leading-6 text-muted-foreground">
              后续生成正文前，系统仍会检查当前设定、档案和章节方案是否与最新大纲一致。
            </p>
          </div>
        </div>
      </section>
    )}
    <div className={`grid gap-6 ${advisorMode ? "xl:grid-cols-[220px_minmax(0,1fr)]" : "xl:grid-cols-[250px_minmax(0,1fr)]"}`}>
      <aside className="space-y-4"><div className={`${cardClass} p-4`}><p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{moduleOnly ? "参考准备" : "创作进度"}</p><ol className="space-y-1">{stages.map((stage, index) => <li key={stage.id}><button onClick={() => { if (canOpenNovelStage(stage.id, currentStage.id, project.completed, busy)) setProject((current) => ({ ...current, index, stageId: stage.id, autoNext:false, autoScope:"manual", autoLaunchStage:"" })); }} disabled={!canOpenNovelStage(stage.id, currentStage.id, project.completed, busy)} className={`flex w-full items-start gap-3 rounded-xl px-2 py-2.5 text-left ${index === stageIndex ? "bg-primary/10 text-primary" : project.completed.includes(stage.id) ? "text-foreground" : "text-muted-foreground"}`}><span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs ${project.completed.includes(stage.id) ? "bg-success/15 text-success" : index === stageIndex ? "bg-primary text-primary-foreground" : "bg-secondary"}`}>{project.completed.includes(stage.id) ? <Check className="h-3 w-3" /> : index + 1}</span><span><span className="block text-sm">{stage.title}{stage.id === "novel-advisor" && <span className="ml-1 text-[10px] text-muted-foreground">可选</span>}</span><span className="mt-0.5 block text-[11px] opacity-70">{stage.group}</span></span></button></li>)}</ol></div><div className={`${cardClass} p-4`}><p className="text-xs text-muted-foreground">当前工作区</p><p className="mt-2 break-all text-xs leading-5">{workspace}</p><p className="mt-3 text-xs text-muted-foreground">已发现 {files.length} 个资料文件 · {chapters.length} 章正文</p></div></aside>
      <section className={`${cardClass} min-w-0 p-6`}>
        <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs text-primary">第 {stageIndex + 1} 步 / 共 {stages.length} 步</p><h2 className="mt-2 text-2xl font-semibold">{advisorMode ? "AI 小说顾问：先聊想法，再确定写法" : currentStage.title}</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">{advisorMode ? "在正式创作前，AI 帮你判断这本小说写什么、主要看点是什么、适合怎么写。有一句想法就能开始，还没想好也可以一起讨论。" : currentStage.description}</p></div><div className="flex items-center gap-2 text-xs text-muted-foreground">{available ? <><span className="h-2 w-2 rounded-full bg-success" />工作流已连接</> : <><span className="h-2 w-2 rounded-full bg-warning" />等待插件工作流</>}</div></div>
        {available && currentStage.id !== "export" && <NovelStepModels workflowId={workflowId(currentStage.id)} task={task} disabled={busy} onPendingChange={setModelPending} onSaved={() => { setActionFeedback("模型设置已同步到工作流，后续新任务会读取新配置。"); }} />}
        {advisorMode ? <><AssistantPanel advisorMode workflowBusy={busy} hasStoryFacts={hasStoryFacts} key={workspace} workspace={workspace} project={project} setProject={setProject} currentStage={currentStage} nextStage={stages[stageIndex + 1]} candidateSet={candidateSet} impactInventory={outlineInventory} onAdoptAdvisor={entry => {const outcome=adoptNovelAdvisor(project, entry, FALLBACK_DEFAULTS, stages, hasStoryFacts); if(outcome.success) setProject(outcome.project); return outcome;}} onManualSelect={onOpenReference ? () => onOpenReference() : undefined} />
          <details className="mt-6 rounded-xl border border-border p-4"><summary className="cursor-pointer text-sm font-medium">已有要求 / 手动设置</summary><p className="mt-3 text-xs leading-6 text-muted-foreground">有明确要求时可以填写；没有要求就先与 AI 讨论。你手动确定的内容会持续保留。</p>{manualControls}</details>
          <button disabled={busy} onClick={skipPreparation} className="mt-5 text-sm text-muted-foreground hover:text-primary disabled:opacity-50">已有明确创意，跳过顾问</button>
        </> : manualControls}
      </section>
      <p className="text-xs leading-6 text-muted-foreground">随时点击右上角「创作助手」讨论本章剧情、人物、伏笔与写法。</p>
    </div>
    {(!advisorMode || !!ref) && <section className={`${cardClass} p-4`}><div className="flex items-center gap-3 text-sm"><FileText className="h-4 w-4 text-primary" /><span>当前产物</span><span className="font-mono text-xs text-muted-foreground">{currentStage.artifact.replace("{chapter}", project.values.chapter_number || "0001")}</span><span className="ml-auto text-xs text-muted-foreground">{task ? statusLabel(task.status) : ref ? "正在恢复状态" : "尚未执行"}</span></div>{preview && currentStage.id !== "style-compatibility-advisor" && <NovelWorkflowArtifact content={preview} title={currentStage.title + " · 已生成内容"} readerReport={currentStage.id === "reader-sim"} />}{currentStage.id === "style-compatibility-advisor" && preview && <CompatibilityReport content={preview} candidateSet={candidateSet} setProject={setProject} adoptedIds={[...adoptedStyles,...adoptedConflicts]} />}</section>}
  </div>;
}

function WorkflowField({ field, value, disabled, onChange }: { field: WorkflowVariable; value: string; disabled: boolean; onChange: (value: string) => void }) { const options = field.options?.length ? field.options : field.key === "writer_type" ? [{ name: "单写手", value: "single" }, { name: "多写手", value: "muti" }] : field.key === "narrative_pov" ? [{ name: "第一人称（我）", value: "first_person" }, { name: "第三人称（他 / 她）", value: "third_person" }] : []; return <label className="block"><span className="mb-2 flex items-center gap-2 text-sm font-medium">{field.name || LABELS[field.key] || field.key}{field.required && <span className="text-[11px] text-warning">必填</span>}</span>{options.length ? <select disabled={disabled} value={value} onChange={(event) => onChange(event.target.value)} className={inputClass}>{options.map((option) => <option key={option.value} value={option.value}>{option.name}</option>)}</select> : field.type === "textarea" || field.key.includes("intent") || field.key === "premise" ? <textarea disabled={disabled} value={value} onChange={(event) => onChange(event.target.value)} rows={4} className={inputClass} /> : <input disabled={disabled} value={value} onChange={(event) => onChange(event.target.value)} className={inputClass} />}<span className="mt-1 block text-xs text-muted-foreground">{field.description || (field.required ? "这是工作流定义中的必填参数。" : "可留空，工作流会使用默认值。")}</span></label>; }

function CandidateChooser({candidateSet, selected, project, adoptedStyles, adoptedConflicts, adoptedReferences, adoptedIds, disabled, setProject}: {candidateSet: CandidateSet | null; selected:string[]; project:Project; adoptedStyles:string[]; adoptedConflicts:string[]; adoptedReferences:Array<{choice_id:string;title:string;guidance:string}>; adoptedIds:string[]; disabled:boolean; setProject:React.Dispatch<React.SetStateAction<Project>>}) {
  const [tab,setTab] = useState<"writing"|"style"|"conflict">("writing");
  const [onlyAdopted,setOnlyAdopted] = useState(false);
  if (!candidateSet) return <p role="status" className="mt-6 text-sm leading-7 text-muted-foreground">暂无参考内容。可以去写法库选择已有结果，也可以直接进入创作流程。</p>;
  const styles=candidateSet.style_choices || [], conflicts=candidateSet.conflict_choices || [];
  const choices=tab==="style"?styles:conflicts;
  const locked=tab==="style"?adoptedStyles:adoptedConflicts;
  const checked=tab==="style"?project.selectedStyles || []:project.selectedConflicts || [];
  const adoptedTotal=adoptedIds.length+adoptedStyles.length+adoptedConflicts.length;
  return <div className="mt-6 space-y-4"><p role="status" className="rounded-xl border border-primary/25 bg-primary/5 p-4 text-sm leading-7">已采用：风格 {adoptedStyles.length} 条 · 写法 {adoptedIds.length} 条 · 冲突 {adoptedConflicts.length} 条。已有内容持续保留，新内容经确认后生效。适配说明须使用本书的题材、视角与人物，不照搬参考作品事件。</p>
    <div className="flex flex-wrap items-center gap-3"><div role="tablist" aria-label="本书参考分类">{([['writing',`写法 · ${candidateSet.candidates.length}`],['style',`风格 · ${styles.length}`],['conflict',`冲突 · ${conflicts.length}`]] as const).map(([id,label])=><button key={id} role="tab" aria-selected={tab===id} onClick={()=>setTab(id)} className={`border-b-2 px-3 py-2 text-sm ${tab===id?'border-primary text-primary':'border-transparent text-muted-foreground'}`}>{label}</button>)}</div><label className="text-xs text-muted-foreground"><input type="checkbox" checked={onlyAdopted} onChange={e=>setOnlyAdopted(e.target.checked)} /> 只看已采用（{adoptedTotal} 项）</label></div>
    {tab==="writing" ? candidateSet.candidates.filter(item=>!onlyAdopted || adoptedIds.includes(item.candidate_id)).map(candidate=><details key={candidate.candidate_id} className="rounded-xl border border-border p-4"><summary className="cursor-pointer text-sm font-medium">{referenceTitle(candidate.mechanism)}<span className={`ml-2 text-xs ${adoptedIds.includes(candidate.candidate_id)?'text-success':'text-muted-foreground'}`}>{adoptedIds.includes(candidate.candidate_id)?'已采用 · 持续保留':selected.includes(candidate.candidate_id)?'已勾选 · 待确认':'未采用'}</span></summary><label className="mt-4 flex gap-3 text-sm leading-7"><input type="checkbox" checked={adoptedIds.includes(candidate.candidate_id)||selected.includes(candidate.candidate_id)} disabled={disabled||adoptedIds.includes(candidate.candidate_id)} onChange={e=>setProject(current=>({...current,selected:toggleWriting(current.selected,adoptedIds,candidate.candidate_id,e.target.checked)}))}/><span>{candidate.mechanism}</span></label><p className="mt-3 text-sm leading-7">{candidate.transfer_guidance}</p><p className="mt-3 text-sm leading-7 text-muted-foreground">{candidate.adaptation_guidance}</p><p className="mt-3 text-sm leading-7 text-warning">{(candidate.constraints||[]).join('；')}</p></details>) : choices.filter(item=>!onlyAdopted||locked.includes(item.choice_id)).map(choice=><details key={choice.choice_id} className="rounded-xl border border-border p-4"><summary className="cursor-pointer text-sm font-medium">{referenceTitle(choice.title)}<span className={`ml-2 text-xs ${locked.includes(choice.choice_id)?'text-success':'text-muted-foreground'}`}>{locked.includes(choice.choice_id)?'已采用 · 持续保留':checked.includes(choice.choice_id)?'已勾选 · 待确认':choice.requires_adaptation?'需适配 · 未采用':'未采用'}</span></summary><div className="mt-5"><NovelReferenceChoice choice={choice}/></div><label className="mt-5 flex gap-3 text-sm"><input type="checkbox" checked={locked.includes(choice.choice_id)||checked.includes(choice.choice_id)} disabled={disabled||locked.includes(choice.choice_id)} onChange={e=>setProject(current=>{const key=tab==='style'?'selectedStyles':'selectedConflicts';return {...current,[key]:toggleWriting(current[key]||[],locked,choice.choice_id,e.target.checked)};})}/>用于本书</label>{locked.includes(choice.choice_id)?<div className="mt-4 rounded-lg bg-success/5 p-3 text-sm leading-7"><p className="font-medium text-success">本书已确认的适配</p><p className="mt-2 whitespace-pre-wrap">{adoptedReferences.find(item=>item.choice_id===choice.choice_id)?.guidance}</p></div>:<label className="mt-4 block text-sm"><span className="mb-2 block">本书适配说明{choice.requires_adaptation?'（采用前必填）':'（可以调整）'}</span><textarea aria-label={`本书适配：${referenceTitle(choice.title)}`} rows={3} disabled={disabled} value={project.referenceAdaptations?.[choice.choice_id]??(choice.requires_adaptation?'':choice.transfer_guidance)} onChange={e=>setProject(current=>({...current,referenceAdaptations:{...current.referenceAdaptations,[choice.choice_id]:e.target.value}}))} placeholder="可先运行写法兼容顾问，参考建议填写：本书怎样使用、怎样埋伏笔、怎样回收；无需复制原作情节。" className={inputClass}/></label>}</details>)}
    {(tab==='writing'?candidateSet.candidates:choices).length===0 && <p className="text-sm leading-7 text-muted-foreground">暂无该类分析，可以保持原创设定。</p>}
  </div>;
}

function CompatibilityReport({ content, candidateSet, setProject, adoptedIds }: { content: string; candidateSet: CandidateSet | null; setProject:React.Dispatch<React.SetStateAction<Project>>; adoptedIds:string[] }) {
  const [copied,setCopied] = useState(false);
  let report: { status?: string; summary?: string; next_step?: string; global_risks?: string[]; recommendations?: Array<{ candidate_id?: string; decision?: string; score?: number; reasons?: string[]; adaptation_plan?: string[]; questions?: string[]; conflicts?: Array<{ severity?: string; field?: string; message?: string }> }> };
  try { report = JSON.parse(content) as typeof report; } catch { return null; }
  const referenceIds = new Set([...(candidateSet?.style_choices || []), ...(candidateSet?.conflict_choices || [])].map(item=>item.choice_id));
  const applicable = (report.recommendations || []).filter(item=>item.candidate_id && referenceIds.has(item.candidate_id) && !adoptedIds.includes(item.candidate_id) && ['recommend','adapt'].includes(item.decision || '') && item.adaptation_plan?.length);
  const fill = () => {setProject(current=>{const referenceAdaptations={...current.referenceAdaptations};for(const item of applicable){if(!referenceAdaptations[item.candidate_id!]?.trim())referenceAdaptations[item.candidate_id!]=item.adaptation_plan!.join('\n');}return {...current,referenceAdaptations};});setCopied(true);};
  const decisionLabels: Record<string, string> = { recommend: "推荐采用", adapt: "适配后采用", caution: "谨慎采用", reject: "不建议采用" };
  return <div className="mt-5 rounded-xl border border-primary/25 bg-primary/5 p-4"><div className="flex flex-wrap items-center justify-between gap-2"><p className="font-medium">写法兼容建议</p><span className="rounded-full bg-secondary px-2 py-1 text-xs">{report.status === "skipped" ? "已跳过" : report.status === "pending" ? "等待基线" : "已分析"}</span></div>{report.summary && <p className="mt-3 text-sm leading-7">{report.summary}</p>}{(report.global_risks || []).map((risk, index) => <p key={index} className="mt-3 text-sm leading-7 text-warning">全局风险：{risk}</p>)}<div className="mt-3 space-y-2">{(report.recommendations || []).map((item, index) => <details key={`${item.candidate_id || "candidate"}-${index}`} className="rounded-lg border border-border bg-background/50 p-3"><summary className="cursor-pointer text-sm"><span className="font-medium">{referenceTitle(candidateSet?.candidates.find(candidate => candidate.candidate_id === item.candidate_id)?.mechanism || [...(candidateSet?.style_choices || []), ...(candidateSet?.conflict_choices || [])].find(choice => choice.choice_id === item.candidate_id)?.title || `参考建议 ${index + 1}`)}</span><span className="ml-2 text-primary">{decisionLabels[item.decision || ""] || item.decision || "待判断"}</span>{typeof item.score === "number" && <span className="ml-2 text-xs text-muted-foreground">{item.score}/100</span>}</summary>{(item.reasons || []).map((reason, i) => <p key={i} className="mt-3 text-sm leading-7 text-muted-foreground">原因：{reason}</p>)}{(item.conflicts || []).map((conflict, i) => <p key={i} className="mt-3 text-sm leading-7 text-warning">{archiveScalar(conflict.severity || "提示", "severity")} · {conflict.field ? archiveLabel(conflict.field.split(".").pop() || conflict.field) : "兼容性"}：{conflict.message}</p>)}{(item.adaptation_plan || []).map((plan, i) => <p key={i} className="mt-3 text-sm leading-7">适配：{plan}</p>)}{(item.questions || []).map((question, i) => <p key={i} className="mt-3 text-sm leading-7 text-primary">需要确认：{question}</p>)}</details>)}</div>{applicable.length > 0 && <div className="mt-4"><button disabled={copied} onClick={fill} className="rounded-lg border border-primary/30 px-4 py-2 text-sm text-primary disabled:opacity-50">{copied ? "已填入适配草稿" : "将风格与冲突建议填入适配草稿"}</button><p role="status" className="mt-2 text-xs leading-6 text-muted-foreground">保留你已填写的说明；不会自动勾选或采用。到「选择与确认」检查后再确认。</p></div>}{report.next_step && <p className="mt-3 text-xs text-muted-foreground">下一步：{report.next_step}</p>}</div>;
}

 function AssistantPanel({ advisorMode = false, workflowBusy = false, onAdoptAdvisor, onManualSelect, hasStoryFacts = false, moduleOnly = false, workspace, project, setProject, currentStage, nextStage, definition, candidateSet, impactInventory }: { advisorMode?: boolean; workflowBusy?: boolean; onAdoptAdvisor?: (entry:NovelAssistantEntry)=>{success:boolean;message:string}; onManualSelect?: ()=>void; hasStoryFacts?: boolean; moduleOnly?: boolean; workspace: string; project: Project; setProject: React.Dispatch<React.SetStateAction<Project>>; currentStage: StageMeta; nextStage?: StageMeta; definition?: WorkflowDefinition; candidateSet: CandidateSet | null; impactInventory: ReturnType<typeof outlineImpactInventory> }) {
  const cacheKey = storageKey(workspace) + ":assistant-history";
  const [entries, setEntries] = useState<NovelAssistantEntry[]>(() => {
    try { const cached = JSON.parse(localStorage.getItem(cacheKey) || "[]"); return Array.isArray(cached) ? cached : []; } catch { return []; }
  });
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [readingEntry, setReadingEntry] = useState<NovelAssistantEntry | null>(null);
  const [scope,setScope] = useState<"book"|"volume"|"chapter">("chapter");
  const [totalLibrarySize, setTotalLibrarySize] = useState(0);
  const mounted = useRef(true);
  const submitGuard = useRef(false);
  const running = entries.find((entry) => entry.status === "running");
  const scopedEntries = entries.filter(entry=>advisorMode ? entry.purpose==='advisor' : (entry.scope || 'chapter')===scope && (scope==='book' || (scope==='volume' ? (entry.volume || '1')===(project.values.volume_number || '1') : !entry.chapter || entry.chapter===(project.values.chapter_number || '0001'))));
  const last = scopedEntries[scopedEntries.length - 1];
  const lastAnswer = [...scopedEntries].reverse().find((entry) => entry.status === "completed");
  const busy = submitting || !!running;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  // Fetch total library size for advisor mode
  useEffect(() => {
    if (!advisorMode) return;
    let active = true;
    void listWritingLibrary().then((result: { items?: WritingLibraryItem[] }) => {
      if (active) setTotalLibrarySize(result.items?.length || 0);
    }).catch(() => {
      if (active) setTotalLibrarySize(0);
    });
    return () => { active = false; };
  }, [advisorMode]);
  useEffect(() => {
    try { localStorage.setItem(cacheKey, JSON.stringify(entries)); } catch { /* Server remains the durable source. */ }
  }, [cacheKey, entries]);
  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    const refresh = async () => {
      let retry = false;
      try {
        const result = await fetchNovelAssistantHistory(workflowId("build"), workspace);
        if (!active) return;
        setEntries(result.entries);
        setFeedback("");
        retry = result.entries.some((entry) => entry.status === "running");
      } catch (failure) {
        if (!active) return;
        setFeedback(failure instanceof Error ? "读取分析记录失败：" + failure.message + "。稍后会自动重试。" : "暂时无法读取分析记录，之前的回答仍然保留。稍后会自动重试。");
        retry = true;
      } finally {
        if (active) {
          setLoadingHistory(false);
          if (retry) timer = window.setTimeout(() => void refresh(), 2500);
        }
      }
    };
    void refresh();
    return () => { active = false; if (timer !== undefined) window.clearTimeout(timer); };
  }, [workspace, refreshKey]);
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
    // running 由 entries.find 派生（每次渲染新对象）；补全会让 1 秒时钟 effect 每次渲染
    // 重启定时器，形成渲染-重启-渲染循环。running?.id 是精确语义。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running?.id]);
  const nextInputs = (definition?.variables || []).filter((field) => field.source_type !== "output" && !field.hidden && field.type !== "file");
  const missing = nextInputs.filter((field) => field.required && !(project.values[field.key] ?? field.default ?? "").trim());
  useEffect(() => {
    if (loadingHistory || moduleOnly || lastAnswer?.purpose !== "configure") return;
    setProject(current => applyAssistantConfiguration(current, lastAnswer, FALLBACK_DEFAULTS, hasStoryFacts));
  }, [lastAnswer, loadingHistory, moduleOnly, hasStoryFacts, setProject]);
  const ask = async (retryQuestion?: string, purpose: "general" | "configure" | "advisor" | "plot" = "general") => {
    if (busy || loadingHistory || submitGuard.current) return;
    submitGuard.current = true;
    setSubmitting(true);
    setFeedback("正在提交分析，之前的回答会继续保留…");
    const question = retryQuestion || project.assistantPlan.trim();
    const request = question || (advisorMode ? "我还没想好写什么，请结合当前作品类型给出具体故事方向、核心看点、写法建议与风险，明确推荐一个方案。" : "请为" + (nextStage?.title || "下一步") + "规划必要参数、章节看点、伏笔触发和递进冲突。");
    const requestId = crypto.randomUUID();
    const advisorBrief = project.advisorBrief?.endsWith(request) ? project.advisorBrief : [project.advisorBrief || "", request].filter(Boolean).join("\n\n补充讨论：\n");
    setProject((current) => ({ ...current, assistantPlan: request,
      ...(purpose === "advisor" ? {advisorBrief} : {}),
      ...(purpose === "configure" ? {pendingAssistantConfiguration: requestId} : {}) }));
    const conflictPlan = {
      mode: project.values.conflict_plan_mode || (project.mode === "serial" ? "serial_opening" : "short_full"),
      conflict_points: project.values.conflict_point_count || (project.mode === "serial" ? "4" : "3"),
      foreshadowing: project.values.foreshadowing_count || (project.mode === "serial" ? "3" : "2"),
      ledger: "meta/conflict_ledger.md",
      distilled_patterns: candidateSet?.conflict_patterns || [],
    };
    try {
      const result = await askNovelAssistant({
        workflow_id: workflowId("build"),
        workspace,
        request_id: requestId,
        question: request,
        purpose,
        chapter:project.values.chapter_number || "0001",
        scope: purpose==='advisor' || purpose==='configure' ? "book" : scope,
        project: { title: project.title, mode: project.mode, values: project.values, writing_mode: project.writingMode, selected_candidate_ids: project.selected, selected_style_ids: project.selectedStyles || [], selected_conflict_ids: project.selectedConflicts || [], configured_fields: project.configuredFields || [], has_story_facts: hasStoryFacts, ...(purpose === "advisor" ? {advisor_brief:advisorBrief} : {}) },
        stage: currentStage.title,
        next_stage: nextStage?.title || "",
        missing: missing.map((field) => field.name || LABELS[field.key] || field.key),
        candidates: candidateSet?.candidates || [],
        conflict_plan: conflictPlan,
      });
      if (!mounted.current) return;
      if (purpose === "configure" && result.entry.purpose === "configure") setProject(current => ({ ...current, pendingAssistantConfiguration: result.entry.id }));
      setEntries((current) => [...current.filter((entry) => entry.id !== result.entry.id), result.entry]);
      setFeedback("");
      setRefreshKey((key) => key + 1);
    } catch (failure) {
      if (!mounted.current) return;
      setFeedback(failure instanceof Error ? "提交分析未确认：" + failure.message + "。正在核对后台状态，请勿重复提交。" : "提交未确认，正在核对后台状态。之前的回答仍然保留。");
      setRefreshKey((key) => key + 1);
    } finally {
      submitGuard.current = false;
      if (mounted.current) setSubmitting(false);
    }
  };

  const handleQuickAdopt = async (entry: NovelAssistantEntry): Promise<{success: boolean; message: string}> => {
    try {
      // 1. 获取写法库列表
      const libraryList = await listWritingLibrary();
      if (!libraryList.items || libraryList.items.length === 0) {
        return { success: false, message: "写法库为空，无法快速采用。" };
      }

      // 2. 默认引用第一个写法库（后续可优化为智能匹配）
      const libraryId = libraryList.items[0].id;

      // 3. 调用引用接口，获取候选写法
      const attachResult = await attachWritingLibrary({
        workflow_id: workflowId("build"),
        workspace,
        library_id: libraryId,
        refresh: false
      });

      // 4. 提取推荐的写法机制ID
      const recommendedMechanisms = entry.advisor_sections?.mechanism_recommendations?.adopted_from_library || [];
      const mechanismNames = recommendedMechanisms.map(m => m.mechanism);

      // 5. 从候选写法中匹配推荐的机制（通过名称模糊匹配）
      const candidateIds: string[] = [];
      if (attachResult.candidates && Array.isArray(attachResult.candidates)) {
        for (const candidate of attachResult.candidates) {
          // 检查候选写法是否匹配任何推荐的机制
          const matches = mechanismNames.some(name =>
            candidate.mechanism.includes(name) || name.includes(candidate.mechanism)
          );
          if (matches) {
            candidateIds.push(candidate.candidate_id);
          }
        }
      }

      // 6. 更新项目状态：引用写法库 + 选中推荐的写法
      setProject(current => ({
        ...current,
        writingMode: "reuse",
        libraryRefs: [...new Set([...current.libraryRefs, libraryId])],
        selected: [...new Set([...current.selected, ...candidateIds])],
      }));

      // 7. 采用顾问建议的配置
      const adoptResult = onAdoptAdvisor?.(entry);
      if (!adoptResult?.success) {
        return { success: false, message: "引用写法库成功，但采用配置失败。请手动完成后续步骤。" };
      }

      // 8. 自动跳转到"本书参考写法"页面（兼容顾问阶段）
      onManualSelect?.(); // 触发跳转回调

      return {
        success: true,
        message: `✅ 已快速采用！引用了写法库「${libraryList.items[0].name}」，已选中 ${candidateIds.length} 条推荐写法。\n\n💡 下一步：点击"让 AI 检查适配"运行兼容检查，审查建议后点击"将建议填入适配草稿"，然后切换到"选择与确认"完成采用。`
      };
    } catch (error) {
      return {
        success: false,
        message: `快速采用失败：${error instanceof Error ? error.message : String(error)}`
      };
    }
  };

  if (advisorMode) return <><NovelAdvisorConversation question={project.assistantPlan} onQuestion={value=>setProject(current=>({...current,assistantPlan:value}))} onAsk={question=>void ask(question,"advisor")} entries={entries} busy={busy} loading={loadingHistory} feedback={feedback} now={now} receipts={project.assistantConfigurations} onAdopt={entry=>onAdoptAdvisor?.(entry) || {success:false,message:"暂时无法采用，请刷新页面后重试。"}} onRead={setReadingEntry} workflowBusy={workflowBusy} established={hasStoryFacts || !!project.refs.build} hasReference={!!(project.selected.length || project.selectedStyles?.length || project.selectedConflicts?.length)} librarySize={totalLibrarySize} adoptedCount={(project.selected?.length || 0) + (project.selectedStyles?.length || 0) + (project.selectedConflicts?.length || 0)} onQuickAdopt={handleQuickAdopt} onManualSelect={onManualSelect}/>
    {readingEntry && <NovelReadingDialog title="AI 小说顾问 · 讨论结果" onClose={()=>setReadingEntry(null)}><details className="mb-5 text-sm leading-7 text-muted-foreground"><summary className="cursor-pointer">查看本次讨论的原始想法</summary><p className="mt-3 whitespace-pre-wrap">{readingEntry.question}</p></details><NovelArchiveContent content={advisorMarkdown(readingEntry.reply || readingEntry.message || "暂无分析内容")}/>{readingEntry.advisor_sections && Object.entries(readingEntry.advisor_sections).map(([key,content])=><section key={key} className="mt-6"><h3 className="mb-3 font-semibold">{{direction:"推荐的故事方向",hook:"核心看点",writing:"适合的写法",risks:"需要注意的问题"}[key]}</h3><NovelArchiveContent content={advisorMarkdown(typeof content === 'string' ? content : '')}/></section>)}</NovelReadingDialog>}
  </>;
  return <aside className={cardClass + " h-fit p-5 xl:sticky xl:top-24"}>
    <div className="flex items-center gap-2"><div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary"><Sparkles className="h-4 w-4" /></div><div><h3 className="font-semibold">创作助手</h3><p className="text-xs text-success">默认调用大模型 · {currentStage.id === "reference-distillation" ? "记录随资料任务保存" : "记录随作品保存"}</p></div></div>
    <div className="mt-5 rounded-xl bg-secondary/40 p-4"><p className="text-sm leading-6">{nextStage ? "完成「" + currentStage.title + "」后，下一步是「" + nextStage.title + "」。" : moduleOnly ? "可随时讨论参考分析与适配，创作流程可独立继续。" : "当前已经是最后一步。"}</p>{nextStage && <><p className="mt-3 text-xs leading-5 text-muted-foreground">{nextInputs.length ? "会读取 " + nextInputs.slice(0, 4).map((field) => field.name || LABELS[field.key] || field.key).join("、") + (nextInputs.length > 4 ? "等参数" : "。") : "这个步骤不需要额外填写参数。"}</p>{missing.length > 0 && <p className="mt-3 flex gap-2 text-xs text-warning"><CircleAlert className="h-4 w-4 shrink-0" />还缺少：{missing.map((field) => field.name || LABELS[field.key] || field.key).join("、")}</p>}</>}</div>
    {!moduleOnly && <div className="mt-4"><label className="text-xs">讨论范围<select aria-label="讨论范围" value={scope} onChange={event=>setScope(event.target.value as typeof scope)} className={inputClass+" mt-2"}><option value="chapter">当前章节 · 第 {Number(project.values.chapter_number || '0001')} 章</option><option value="volume">当前卷</option><option value="book">整本书</option></select></label><p className="mt-2 text-xs leading-6 text-muted-foreground">结合人物处境、世界局势、伏笔与本书写法；没有参考资料也能原创。</p><div className="mt-3 flex flex-wrap gap-2">{[{label:'给几个发展方向',question:'请结合当前进度，给出2-3个有区别的后续剧情方向，说明前文依据、人物动机、冲突、代价、伏笔与期待兑现，并给出可采用的章节计划。'},{label:'检查伏笔与动机',question:'请检查当前计划中的伏笔、人物动机与世界因果，指出具体问题；没有需要修改的地方就说明原因。'},{label:'加强看点与爽点',question:'请判断当前剧情是否像过程记录，结合人物独立目标提出自然的冲突、情感和期待兑现方案，避免空降反转或固定打脸。'}].map(item=><button key={item.label} disabled={busy || loadingHistory} onClick={()=>void ask(item.question,'plot')} className="rounded-lg border border-primary/30 px-2.5 py-2 text-xs text-primary disabled:opacity-50">{item.label}</button>)}</div></div>}
    <label className="mt-4 block text-xs font-medium">告诉助手你要分析什么<textarea disabled={busy} value={project.assistantPlan} onChange={(event) => setProject((current) => ({ ...current, assistantPlan: event.target.value }))} rows={4} placeholder="例如：我想写末日丧尸短篇，请给我题材、故事创意、递进冲突和伏笔。" className={inputClass + " mt-2 text-xs"} /></label>
    <button disabled={busy || loadingHistory} onClick={() => void ask()} className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border border-primary/30 bg-primary/10 px-3 py-2.5 text-sm text-primary disabled:cursor-wait disabled:opacity-60">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <WandSparkles className="h-4 w-4" />}{submitting ? "正在提交…" : running ? "正在分析…" : loadingHistory ? "正在恢复记录…" : "分析并给出方案"}</button>
    {!moduleOnly && <><button disabled={busy || loadingHistory || project.autoNext} onClick={() => void ask(undefined, "configure")} className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-3 py-2.5 text-sm font-medium text-primary-foreground disabled:opacity-60">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Settings2 className="h-4 w-4" />}分析并完善设置</button><p className="mt-2 text-xs leading-6 text-muted-foreground">根据想法推荐字数、视角、世界观、冲突与伏笔，自动填写未确定的参数。保留手动设置和已有故事事实；可以切换页面，回来后继续填写。{project.autoNext && " 自动创作正在推进时先讨论建议，暂停后再完善设置。"}</p></>}
    {running && <p role="status" aria-live="polite" className="mt-3 text-xs leading-5 text-muted-foreground">{running.message || "大模型正在分析…"} 已等待 {Math.max(0, Math.floor((now - Date.parse(running.created_at)) / 1000))} 秒。复杂分析可能需要 1～3 分钟，可以切换页面，回来后会恢复结果。</p>}
    {feedback && <p role="status" className="mt-3 text-xs leading-5 text-warning">{feedback}</p>}
    {last?.status === "failed" && <div role="alert" className="mt-4 rounded-xl border border-warning/30 bg-warning/10 p-3 text-xs leading-5"><p className="font-medium">本次分析未完成</p><p className="mt-1">{last.message}</p><button disabled={busy || loadingHistory} onClick={() => void ask(last.question, last.purpose === "configure" ? "configure" : last.purpose === "plot" ? "plot" : "general")} className="mt-2 rounded-lg border border-border px-3 py-1.5 disabled:opacity-50">重新分析这个问题</button></div>}
     {lastAnswer && <section className="mt-5 rounded-xl border border-primary/25 bg-primary/5 p-4"><div className="flex items-center justify-between gap-2"><h4 className="text-sm font-medium">助手建议</h4><button onClick={() => setReadingEntry(lastAnswer)} className="rounded-lg border border-border px-2 py-1.5 text-xs hover:bg-secondary/60">展开阅读</button></div><details className="mt-3 border-b border-border/60 pb-3 text-sm leading-6 text-muted-foreground"><summary className="cursor-pointer">问题：{lastAnswer.question.length > 100 ? lastAnswer.question.slice(0,100)+"…" : lastAnswer.question}</summary><p className="mt-3 whitespace-pre-wrap">{lastAnswer.question}</p></details><div className="mt-3 max-h-[500px] overflow-auto"><NovelArchiveContent content={lastAnswer.reply || "暂无回复内容"} /></div><NovelConfigurationSuggestions entry={lastAnswer} receipt={project.assistantConfigurations?.[lastAnswer.id]} /><NovelPlotProposals key={lastAnswer.id} entry={lastAnswer} workspace={workspace} workflowId={workflowId("build")} impactInventory={impactInventory} disabled={busy || project.autoNext} onApplied={()=>setRefreshKey(key=>key+1)}/></section>}
    {entries.filter((entry) => entry.status !== "running" && entry.id !== lastAnswer?.id && entry.id !== (last?.status === "failed" ? last.id : "")).length > 0 && <details className="mt-4 rounded-xl border border-border p-4"><summary className="cursor-pointer text-sm text-primary">查看之前的分析记录</summary>{entries.filter((entry) => entry.status !== "running" && entry.id !== lastAnswer?.id && entry.id !== (last?.status === "failed" ? last.id : "")).reverse().map((entry) => <details key={entry.id} className="mt-3 border-t border-border pt-3"><summary className="cursor-pointer text-sm leading-6">{entry.question} · {entry.status === "completed" ? "已完成" : "未完成"}</summary><button onClick={() => setReadingEntry(entry)} className="mt-3 rounded-lg border border-border px-3 py-1.5 text-xs">展开阅读</button><div className="mt-3 max-h-[360px] overflow-auto"><NovelArchiveContent content={entry.reply || entry.message || "暂无分析内容"} /><NovelConfigurationSuggestions entry={entry} receipt={project.assistantConfigurations?.[entry.id]} /></div></details>)}</details>}
     {readingEntry && <NovelReadingDialog title="创作助手 · 分析结果" onClose={() => setReadingEntry(null)}><details className="mb-5 border-b border-border pb-4 text-sm leading-7 text-muted-foreground"><summary className="cursor-pointer">查看本次问题</summary><p className="mt-3 whitespace-pre-wrap">{readingEntry.question}</p></details><NovelArchiveContent content={advisorMarkdown(readingEntry.reply || readingEntry.message || "暂无分析内容")} />{readingEntry.advisor_sections && Object.entries(readingEntry.advisor_sections).map(([key,content])=><section key={key} className="mt-6"><h3 className="mb-3 font-semibold">{{direction:"推荐的故事方向",hook:"核心看点",writing:"适合的写法",risks:"需要确认"}[key]}</h3><NovelArchiveContent content={advisorMarkdown(typeof content === 'string' ? content : '')}/></section>)}<NovelConfigurationSuggestions entry={readingEntry} receipt={project.assistantConfigurations?.[readingEntry.id]} /><NovelPlotProposals key={readingEntry.id} entry={readingEntry} workspace={workspace} workflowId={workflowId("build")} impactInventory={impactInventory} disabled={busy || project.autoNext} onApplied={()=>{setRefreshKey(key=>key+1);setReadingEntry(null);}}/></NovelReadingDialog>}
    {!moduleOnly && <div className="mt-5 border-t border-border pt-4"><p className="text-xs font-medium">{project.autoNext ? "本次自动执行" : "本次创作要求"}</p><div className="mt-3 space-y-2 text-xs text-muted-foreground"><p>模式：{project.mode === "serial" ? "长篇连载" : "短篇"}</p><p>冲突范围：{project.values.conflict_plan_mode === "serial_opening" ? "长篇前几章" : project.values.conflict_plan_mode === "serial_arc" ? "长篇当前卷" : project.values.conflict_plan_mode === "serial_chapter" ? "长篇当前章节" : "短篇全文"}</p><p>冲突点：{project.values.conflict_point_count || (project.mode === "serial" ? "4" : "3")} · 伏笔：{project.values.foreshadowing_count || (project.mode === "serial" ? "3" : "2")}</p><p>范围：{project.mode === "serial" ? "最多 " + project.autoChapterLimit + " 章" : "完成本篇"}</p><p>视角：{project.values.narrative_pov === "first_person" ? "第一人称" : "第三人称"}</p><p>字数：{project.values.target_word_count || "使用工作流默认值"}</p></div></div>}
  </aside>;
}

export default function NovelWorkbenchPage() {
  return <NovelWorkbenchProvider><NovelWorkbenchSurface><NovelWorkbenchContent /></NovelWorkbenchSurface></NovelWorkbenchProvider>;
}

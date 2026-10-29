/**
 * REST API 客户端封装
 */
import { request } from "./http-client";

export {
  retryWorkflowNode,
  skipWorkflowNode,
} from "./workflow-node-control-api";
export type {
  NodeFailureActionResponse,
} from "./workflow-node-control-api";

/** 构建查询参数字符串（listTasks / listAllTasks 共用） */
function buildListQuery(params?: Record<string, string | number | undefined>): string {
  if (!params) return "";
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value != null) query.set(key, String(value));
  }
  const qs = query.toString();
  return qs ? `?${qs}` : "";
}

export async function fetchExtensions() {
  return request<{
    extensions: import("../extensions/types").ExtensionStatus[];
    enabled: string[];
  }>("/extensions");
}

// ============ 会话 API ============

export async function fetchSessions() {
  return request<{ sessions: import("../types").Session[]; active_sub_count: number; main_session_id: string | null }>("/sessions");
}

export async function fetchSessionTree() {
  return request<import("../types").SessionTree>("/sessions/tree");
}

export async function fetchSessionDetail(sessionId: string) {
  return request<import("../types").SessionDetail>(`/sessions/${sessionId}`);
}

export async function updateSessionModel(
  sessionId: string,
  modelId: string,
  reasoningEffort: string | null,
) {
  return request<{
    success: boolean;
    message: string;
    model_id: string;
    model_params: Record<string, unknown>;
  }>(`/sessions/${sessionId}/model`, {
    method: "PUT",
    body: JSON.stringify({
      model_id: modelId,
      reasoning_effort: reasoningEffort,
    }),
  });
}

export async function fetchSessionSystemPrompt(sessionId: string) {
  return request<{
    session_id: string;
    agent_type: string;
    system_prompt: string;
    tools: {
      name: string;
      description: string;
      parameters?: Record<string, { type: string; description: string; required: boolean }>;
      schema: {
        type: "function";
        function: {
          name: string;
          description?: string;
          parameters: Record<string, unknown>;
        };
      };
    }[];
    tools_count: number;
    message_counts: { system: number; user: number; assistant: number; tool: number };
    token_estimate: { system_prompt: number; messages: number; tools: number; total: number };
    model_config: {
      model: string;
      temperature: number;
      model_params: Record<string, unknown>;
      max_context_tokens: number;
      max_tool_rounds: number;
    };
    messages: import("../types").Message[];
    context_scope: "current_effective";
  }>(`/sessions/${sessionId}/system-prompt`);
}

export async function killSession(sessionId: string) {
  return request<{ success: boolean; message: string }>(`/sessions/${sessionId}/kill`, {
    method: "POST",
  });
}

export async function sendToSession(sessionId: string, message: string) {
  return request<{ success: boolean; message: string; reply?: string }>(`/sessions/${sessionId}/message`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export async function deleteSession(sessionId: string) {
  return request<{
    success: boolean;
    message: string;
    deleted_session_ids?: string[];
    deleted_task_ids?: string[];
  }>(`/sessions/${sessionId}`, {
    method: "DELETE",
  });
}

export async function createNewMainSession(agentType?: string) {
  return request<{ success: boolean; session_id: string; message: string }>("/sessions/main/new", {
    method: "POST",
    body: JSON.stringify({ agent_type: agentType || "main" }),
  });
}

// ============ 提示词 API ============

export async function fetchPrompt() {
  return request<import("../types").PromptData>("/prompt");
}

export async function fetchPromptHistory() {
  return request<{ history: import("../types").PromptHistoryEntry[] }>("/prompt/history");
}

// ============ 系统 API ============

export async function fetchSystemStatus() {
  return request<import("../types").SystemStatus>("/system/status");
}

export async function fetchTools() {
  return request<{ tools: import("../types").ToolInfo[]; groups: import("../types").ToolGroup[]; total: number }>("/tools");
}

export async function fetchGraphStructure() {
  const data = await request<{ graph: import("../types").GraphStructure }>("/graph/structure");
  return data.graph;
}

export async function fetchRecentEvents(limit: number = 50) {
  return request<{ events: Record<string, unknown>[]; total: number }>(`/events/recent?limit=${limit}`);
}

// ============ 编排 API ============

export async function fetchPromptTemplates() {
  return request<{ templates: string[] }>("/prompt-templates");
}

export async function deletePromptTemplate(templateName: string) {
  return request<{ success: boolean; message: string }>(`/prompt-templates/${encodeURIComponent(templateName)}`, {
    method: "DELETE",
  });
}

export async function fetchPromptSectionsWithContent(promptType: string = "main") {
  return request<{
    sections: import("../types").PromptSectionData[];
    total_token_estimate: number;
    sections_count: number;
    priority_in_use: string;
    prompt_version: number;
    template_variables?: import("../types").TemplateVariable[];
  }>(`/prompt-sections?include_content=true&prompt_type=${promptType}`);
}

export async function fetchTemplateVariables(promptType: string) {
  return request<{
    template_variables: import("../types").TemplateVariable[];
  }>(`/prompt-sections/config?prompt_type=${promptType}`);
}

export async function updateTemplateVariables(templateVariables: import("../types").TemplateVariable[], promptType: string = "main") {
  return request<{ success: boolean; template_variables: import("../types").TemplateVariable[] }>(`/prompt-sections/template-variables?prompt_type=${promptType}`, {
    method: "PUT",
    body: JSON.stringify({ template_variables: templateVariables }),
  });
}

export async function fetchAgentDefinitions() {
  return request<{
    agent_types: import("../types").AgentDefinitionData[];
  }>("/agent-definitions");
}

export async function fetchAgentTypes() {
  return request<{
    agent_types: import("../types").AgentTypeOption[];
  }>("/agent-types");
}

export async function postOrchestrationPreview(
  sectionNames: string[],
  customSections: { name: string; content: string }[] = []
) {
  return request<import("../types").OrchestrationPreviewResult>("/orchestration/preview", {
    method: "POST",
    body: JSON.stringify({ section_names: sectionNames, custom_sections: customSections }),
  });
}

// ============ 圆桌会议 API ============

export async function fetchRoundtables() {
  return request<{ roundtables: import("../types").RoundtableSummary[]; total: number }>("/roundtable");
}

export async function createRoundtable(data: import("../types").CreateRoundtableRequest) {
  return request<{ success: boolean; session: import("../types").RoundtableSummary }>("/roundtable", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function fetchRoundtableDetail(sessionId: string) {
  return request<import("../types").RoundtableSession>(`/roundtable/${sessionId}`);
}

export async function startRoundtable(sessionId: string) {
  return request<{ success: boolean; message: string }>(`/roundtable/${sessionId}/start`, {
    method: "POST",
  });
}

export async function stopRoundtable(sessionId: string) {
  return request<{ success: boolean; message: string }>(`/roundtable/${sessionId}/stop`, {
    method: "POST",
  });
}

export async function fetchTranscript(sessionId: string) {
  return request<{ transcript: import("../types").TranscriptEntry[]; total: number; current_round: number }>(`/roundtable/${sessionId}/transcript`);
}

export async function deleteRoundtable(sessionId: string) {
  return request<{ success: boolean; message: string }>(`/roundtable/${sessionId}`, {
    method: "DELETE",
  });
}

export async function fetchSharedMemory(sessionId: string) {
  return request<{ shared_memory: import("../types").SharedMemory; session_id: string }>(`/roundtable/${sessionId}/shared-memory`);
}

// ============ Phase 3 API ============

export async function pauseRoundtable(sessionId: string) {
  return request<{ success: boolean; message: string }>(`/roundtable/${sessionId}/pause`, {
    method: "POST",
  });
}

export async function resumeRoundtable(sessionId: string) {
  return request<{ success: boolean; message: string }>(`/roundtable/${sessionId}/resume`, {
    method: "POST",
  });
}

export async function injectToRoundtable(sessionId: string, content: string) {
  return request<{ success: boolean; message: string }>(`/roundtable/${sessionId}/inject`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export async function nominateSpeaker(
  sessionId: string,
  targetSeatId?: string,
  targetName?: string,
  content?: string
) {
  return request<{ success: boolean; message: string }>(`/roundtable/${sessionId}/nominate`, {
    method: "POST",
    body: JSON.stringify({
      target_seat_id: targetSeatId,
      target_name: targetName,
      content: content || "",
    }),
  });
}

export async function addSeatToRoundtable(sessionId: string, seat: {
  role_name: string;
  system_prompt?: string;
  temperature?: number;
  model_name?: string | null;
  is_moderator?: boolean;
}) {
  return request<{ success: boolean; message: string; seat?: import("../types").Seat }>(
    `/roundtable/${sessionId}/seats`,
    {
      method: "POST",
      body: JSON.stringify(seat),
    }
  );
}

export async function removeSeatFromRoundtable(sessionId: string, seatId: string) {
  return request<{ success: boolean; message: string }>(
    `/roundtable/${sessionId}/seats/${seatId}`,
    { method: "DELETE" }
  );
}

export async function fetchStructuredConclusion(sessionId: string) {
  return request<{
    session_id: string;
    has_structured_conclusion: boolean;
    structured_conclusion: import("../types").StructuredConclusion | null;
    shared_memory: import("../types").SharedMemory;
  }>(`/roundtable/${sessionId}/structured-conclusion`);
}

// ============ 工作流任务 API ============

/** 创建任务（不启动），可携带参数值 */
export async function createTask(
  workflowId: string,
  parameterValues?: Record<string, string>,
  fromNodeId?: string,
  disabledNodeIds?: string[],
  workspaceOverride?: string,
  schemeId?: string,
  selectedNodeIds?: string[],
  nodeModelOverrides?: Record<string, string>,
) {
  const body: Record<string, unknown> = {
    from_node_id: fromNodeId || null,
    parameter_values: parameterValues || null,
    workspace_override: workspaceOverride || null,
  };
  if (nodeModelOverrides) body.node_model_overrides = nodeModelOverrides;
  // 优先 selected_node_ids，其次 scheme_id，最后 disabled_node_ids
  if (selectedNodeIds && selectedNodeIds.length > 0) {
    body.selected_node_ids = selectedNodeIds;
  } else if (schemeId) {
    body.scheme_id = schemeId;
  } else if (disabledNodeIds && disabledNodeIds.length > 0) {
    body.disabled_node_ids = disabledNodeIds;
  }
  return request<{ task_id: string; workflow_id: string; status: string; definition: import("../types").WorkflowDefinition }>(
    `/workflows/${workflowId}/tasks`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

/** 启动已创建的任务 */
export async function runTask(workflowId: string, taskId: string, fromNodeId?: string) {
  return request<{ success: boolean; message: string; task_id: string; workflow_id: string }>(
    `/workflows/${workflowId}/tasks/${taskId}/run`,
    {
      method: "POST",
      body: JSON.stringify({ from_node_id: fromNodeId || null }),
    }
  );
}

/** 获取工作流变量定义（用于填参表单） */
export async function getWorkflowVariables(workflowId: string) {
  return request<import("../types").WorkflowVariable[]>(`/workflows/${workflowId}/variables`);
}

/** 获取工作流的变量→节点引用映射（用于参数过滤和引用计数） */
export async function getVariableReferences(workflowId: string) {
  return request<Record<string, string[]>>(`/workflows/${workflowId}/variable-references`);
}

/** 预启动工作流：创建 pending task + main session + workspace */
export async function preStartWorkflow(workflowId: string, mainTakeover = false) {
  return request<{ success: boolean; task_id: string; session_id: string; main_takeover: boolean; message: string }>(
    `/workflows/${workflowId}/pre-start`,
    {
      method: "POST",
      body: JSON.stringify({ main_takeover: mainTakeover }),
    }
  );
}

/** 启动预启动状态的任务（从 pre_running → running） */
export async function startPreRunningTask(workflowId: string, taskId: string) {
  return request<{ success: boolean; message: string; task_id: string }>(
    `/workflows/${workflowId}/tasks/${taskId}/start`,
    { method: "POST" }
  );
}

/** @deprecated 使用 createTask + runTask 两步流程 */
export async function createAndRunTask(workflowId: string, fromNodeId?: string) {
  return request<{ success: boolean; message: string; task_id: string; workflow_id: string }>(
    `/workflows/${workflowId}/tasks`,
    {
      method: "POST",
      body: JSON.stringify({ from_node_id: fromNodeId || null }),
    }
  );
}

export async function listTasks(
  workflowId: string,
  params?: {
    status?: string;
    search?: string;
    sort_by?: string;
    sort_order?: string;
    page?: number;
    page_size?: number;
    /** 附连续退步趋势块（R51，默认关：要多扫一遍 runs/） */
    with_trend?: boolean;
    baseline_limit?: number;
  }
) {
  const query = { ...params, with_trend: params?.with_trend ? "true" : undefined };
  const qs = buildListQuery(query);
  return request<import("../types").TaskListResponse>(
    `/workflows/${workflowId}/tasks${qs}`
  );
}

// ============ 执行方案 API ============

/** 获取工作流的所有执行方案 */
export async function getSchemes(workflowId: string) {
  return request<import("../types").ExecutionScheme[]>(`/workflows/${workflowId}/schemes`);
}

/** 创建执行方案 */
export async function createScheme(workflowId: string, name: string, selectedNodeIds: string[]) {
  return request<import("../types").ExecutionScheme>(
    `/workflows/${workflowId}/schemes`,
    { method: "POST", body: JSON.stringify({ name, selected_node_ids: selectedNodeIds }) },
  );
}

/** 更新执行方案 */
export async function updateScheme(workflowId: string, schemeId: string, name?: string, selectedNodeIds?: string[]) {
  return request<import("../types").ExecutionScheme>(
    `/workflows/${workflowId}/schemes/${schemeId}`,
    { method: "PUT", body: JSON.stringify({ name, selected_node_ids: selectedNodeIds }) },
  );
}

/** 删除执行方案 */
export async function deleteScheme(workflowId: string, schemeId: string) {
  return request<{ success: boolean }>(
    `/workflows/${workflowId}/schemes/${schemeId}`,
    { method: "DELETE" },
  );
}

/** 列出全部工作流的所有任务（全局任务历史） */
export async function listAllTasks(params?: {
  status?: string;
  search?: string;
  sort_by?: string;
  sort_order?: string;
  page?: number;
  page_size?: number;
  workflow_id?: string;
  main_session_id?: string;
  /** 附连续退步趋势块（R51，默认关：要多扫一遍 runs/） */
  with_trend?: boolean;
  baseline_limit?: number;
}) {
  const query = { ...params, with_trend: params?.with_trend ? "true" : undefined };
  const qs = buildListQuery(query);
  return request<import("../types").TaskListResponse>(`/tasks${qs}`);
}

export async function getTask(workflowId: string, taskId: string) {
  return request<import("../types").TaskDetailResponse>(`/workflows/${workflowId}/tasks/${taskId}`);
}

/** 任务运行画像：缺省最新 run，`runId` 指定历史 run（R41 ?run_id=）；
 *  `compare` 时附带与上一次 run 的对比块（R43 ?compare=true）；
 *  `baselineLimit` 时附带多 run 基线与趋势（R50 ?baseline_limit=N） */
export async function getTaskRunProfile(workflowId: string, taskId: string, runId?: string,
                                        compare?: boolean, baselineLimit?: number) {
  const params = new URLSearchParams();
  if (runId) params.set("run_id", runId);
  if (compare) params.set("compare", "true");
  // 0/未传 → 后端不返回 baseline 块（也就不会多扫一遍 runs/ 目录）
  if (baselineLimit && baselineLimit > 0) params.set("baseline_limit", String(baselineLimit));
  const qs = params.toString() ? `?${params.toString()}` : "";
  return request<import("../types").RunProfile>(`/workflows/${workflowId}/tasks/${taskId}/run-profile${qs}`);
}

export type NovelAssistantEntry = {
  id: string;
  question: string;
  stage: string;
  status: "running" | "completed" | "failed";
  source: "llm";
  reply: string;
  message?: string;
  attempt?: number;
  error_code?: string;
  model?: string;
  created_at: string;
  finished_at?: string;
  elapsed_seconds?: number;
  purpose?: "general" | "reader_repair" | "configure" | "advisor" | "plot";
  scope?: "book" | "volume" | "chapter";
  volume?: string;
  plot_options?: NovelPlotOption[];
  plot_receipts?: Record<string, { title: string; chapters: string[]; applied_at: string }>;
  integration_projects?: string[];
  advisor_sections?: {
    direction: string;
    hook: string;
    writing: string;
    risks: string;
    mechanism_recommendations?: {
      adopted_from_library?: Array<{mechanism: string; usage_in_story: string; priority: string; chapter_placement: string}>;
      new_mechanisms?: Array<{mechanism: string; reason: string; synergy_with: string[]; priority: string}>;
      avoid_combinations?: Array<{a: string; b: string; reason: string}>;
    };
  };
  suggestions?: { key: string; label: string; value: string; reason: string }[];
  configuration_base?: { mode: string; values: Record<string, string>; has_story_facts?: boolean; advisor_brief?: string };
  chapter?: string;
  reader_summary?: string;
  applied_at?: string;
  feedback_path?: string;
  applied_plan?: string;
};

export type NovelPlotChapter = {
  chapter: string; title: string; goal: string; conflict: string; choice: string;
  turning_point: string; cost: string; reveal: string; payoff: string; hook: string; time_advance: string;
  setup: { source_id: string; quote: string; use: string }[];
};
export type NovelPlotOption = {
  id: string; title: string; reason: string; risks: string[]; new_info: string[];
  chapters: NovelPlotChapter[]; score: number;
};
export async function applyNovelPlotPlan(payload: { workflow_id: string; workspace: string; entry_id: string; option_id: string }) {
  return request<{ title: string; chapters: string[]; applied_at: string; already_applied: boolean }>("/novel-console/plot/apply", {method:"POST", body:JSON.stringify(payload)});
}
export async function checkNovelContinuation(workflowId: string, workspace: string, chapter: string) {
  return request<{ready:boolean; action:string; chapter:string; message:string; next_step?:string; reason_code?:string; changed_sources?:string[]}>(`/novel-console/continuation?${new URLSearchParams({workflow_id:workflowId,workspace,chapter})}`);
}
export type NovelChapterContext = {
  chapter: string; has_body: boolean;
  refs: Record<string, {workflow_id: string; task_id: string}>;
  completed: string[]; values: Record<string, string>; later_chapters: string[]; message: string;
};
export async function getNovelChapterContext(workflowId: string, workspace: string, chapter: string, action = "write") {
  return request<NovelChapterContext>("/novel-console/chapters/context", {method:"POST",
    body:JSON.stringify({workflow_id:workflowId, workspace, chapter, action})});
}
export type NovelChapterRemovalPreview = {
  chapter: string; body_sha256: string; revision: number; later_chapters: string[];
  file_count: number; message: string;
};
export async function previewNovelChapterRemoval(workflowId: string, workspace: string, chapter: string) {
  return request<NovelChapterRemovalPreview>(`/novel-console/chapters/removal-preview?${new URLSearchParams({workflow_id:workflowId,workspace,chapter})}`);
}
export async function removeNovelChapter(payload: {
  workflow_id:string; workspace:string; chapter:string; operation:"delete"|"regenerate";
  expected_sha256:string; expected_revision:number;
}) {
  return request<NovelChapterRemovalPreview & {backup_path:string; state:Record<string, unknown>}>(
    "/novel-console/chapters/remove", {method:"POST",body:JSON.stringify(payload)});
}
export async function fetchNovelArchiveState(workflowId: string, workspace: string) {
  return request<{updated_chapter:string; message:string; stale_chapters?:string[]; pending_chapters?:string[]; items:{path:string;label:string;group:string;content:string}[]}>(`/novel-console/archive-state?${new URLSearchParams({workflow_id:workflowId,workspace})}`);
}

export async function fetchNovelAssistantHistory(workflowId: string, workspace: string) {
  const query = new URLSearchParams({ workflow_id: workflowId, workspace });
  return request<{ entries: NovelAssistantEntry[] }>(`/novel-console/assistant/history?${query}`);
}

export async function askNovelAssistant(payload: {
  workflow_id: string;
  workspace: string;
  request_id: string;
  question: string;
  project: Record<string, unknown>;
  stage: string;
  next_stage?: string;
  missing?: string[];
  candidates?: unknown[];
  conflict_plan?: Record<string, unknown>;
  purpose?: "general" | "reader_repair" | "configure" | "advisor" | "plot";
  chapter?: string;
  scope?: "book" | "volume" | "chapter";
}) {
  return request<{ success: boolean; entry: NovelAssistantEntry }>("/novel-console/assistant", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function applyNovelRepairPlan(payload: { workflow_id: string; workspace: string; entry_id: string; plan: string }) {
  return request<{ feedback_path: string; chapter: string; already_applied: boolean; model_id: string }>("/novel-console/repair/apply", {method: "POST", body: JSON.stringify(payload)});
}

export async function getNovelReaderReport(workflowId: string, workspace: string, chapter: string) {
  const query = new URLSearchParams({workflow_id: workflowId, workspace, chapter});
  return request<{report: Record<string, unknown>; chapter: string}>(`/novel-console/reader-report?${query}`);
}

/**
 * 工作流列表。
 *
 * `withHealth` 打开后每条摘要会带 `health` 块（R54）：后端要逐 workflow 扫
 * `runs/` 才算得出「最近是不是一直在挂」。默认关着，因为资源选择器之类的
 * 调用方只要 id 和名字。
 */
export async function listWorkflows(options: { withHealth?: boolean; healthLimit?: number } = {}) {
  const query = new URLSearchParams();
  if (options.withHealth) {
    query.set("with_health", "true");
    if (options.healthLimit && options.healthLimit > 0) {
      query.set("health_limit", String(options.healthLimit));
    }
  }
  const suffix = query.toString() ? `?${query}` : "";
  return request<Array<{ workflow_id: string; name: string; node_count: number; version: number; status?: string; health?: import("../types").WorkflowHealth }>>(`/workflows${suffix}`);
}

export async function listWorkspaceFiles(
  workflowId: string,
  workspace?: string,
  prefix?: string,
) {
  const query = new URLSearchParams({ workflow_id: workflowId });
  if (workspace) query.set("workspace", workspace);
  if (prefix) query.set("prefix", prefix);
  return request<{ workspace: string; files: Array<{ path: string; size_bytes: number; modified_at: number }> }>(
    `/workflows/workspace-files?${query.toString()}`,
  );
}

export async function readWorkspaceFile(workflowId: string, workspace: string | undefined, path: string) {
  const query = new URLSearchParams({ workflow_id: workflowId, path });
  if (workspace) query.set("workspace", workspace);
  return request<{ workspace: string; path: string; content: string; size_bytes: number }>(
    `/workflows/workspace-files/content?${query.toString()}`,
  );
}

export async function getWorkflow(workflowId: string) {
  return request<{ definition: import("../types").WorkflowDefinition }>(`/workflows/${encodeURIComponent(workflowId)}`);
}

export async function readWorkflowWorkspaceFile(workflowId: string, taskId: string, path: string) {
  return request<{ workflow_id: string; task_id: string; path: string; content: string; size_bytes: number }>(
    `/workflows/${encodeURIComponent(workflowId)}/tasks/${encodeURIComponent(taskId)}/workspace-file?path=${encodeURIComponent(path)}`,
  );
}

export async function writeNovelWorkspaceText(workflowId: string, workspace: string, path: string, content: string) {
  return request<{ success: boolean; path: string; sha256: string }>("/novel-console/text", {
    method: "PUT",
    body: JSON.stringify({ workflow_id: workflowId, workspace, path, content }),
  });
}

export type PublicChapterLink = { index: number; title: string; url: string; selected?: boolean };

export async function inspectNovelImportUrl(url: string) {
  return request<{ url: string; title: string; detected_type: string; chapters: PublicChapterLink[]; has_page_text: boolean; warnings?: string[] }>("/novel-console/import-url/inspect", {
    method: "POST", body: JSON.stringify({ url }),
  });
}

export async function importNovelUrl(payload: { workflow_id: string; workspace: string; url: string; source_mode: string; chapters: PublicChapterLink[] }) {
  return request<{ success: boolean; path: string; manifest_path: string; title: string; chapter_count: number; characters: number; warnings?: string[] }>("/novel-console/import-url/fetch", {
    method: "POST", body: JSON.stringify(payload),
  });
}

export async function saveNovelProject(workflow_id: string, workspace: string, state: object) {
  return request<{ success: boolean; workspace: string; revision: number }>("/novel-console/projects", { method: "PUT", body: JSON.stringify({ workflow_id, workspace, state }) });
}

export async function listNovelProjects() {
  return request<{ projects: Array<{ workspace: string; state: Record<string, unknown>; progress?: NovelProgress }> }>("/novel-console/projects");
}

export async function deleteNovelProject(workflowId: string, workspace: string) {
  const query = new URLSearchParams({ workflow_id: workflowId, workspace });
  return request<{ success: boolean; workspace: string; deleted: boolean }>(`/novel-console/projects?${query.toString()}`, {
    method: "DELETE",
  });
}

export type WritingLibraryItem = {
  id: string; name: string; genres: string[]; pov: string[]; tone: string[];
  language: string; candidate_count: number; source_sha256?: string; source_mode?: string; created_at: string; version: number;
  style_count?: number; conflict_count?: number;
};

export async function listWritingLibrary() {
  return request<{ items: WritingLibraryItem[] }>("/novel-console/library");
}

export type WritingLibraryDeleteResult = {
  success: boolean;
  deleted_ids: string[];
  missing_ids: string[];
  failed: Array<{ id: string; message: string }>;
};

export async function deleteWritingLibrary(workflowId: string, libraryIds: string[]) {
  return request<WritingLibraryDeleteResult>("/novel-console/library/delete", {
    method: "POST", body: JSON.stringify({ workflow_id: workflowId, library_ids: libraryIds }),
  });
}

export async function getWritingLibraryItem(id: string) {
  return request<{ manifest: WritingLibraryItem; profile: { markdown?: string; documents?: Record<string, string>; limitations?: string[]; upstream?: { repository?: string; commit?: string } }; candidates: { candidates: Array<Record<string, unknown>>; candidates_sha256?: string; style_choices?: ReferenceChoice[]; conflict_choices?: ReferenceChoice[]; conflict_patterns?: Array<Record<string, unknown>> } }>(
    `/novel-console/library/${encodeURIComponent(id)}`,
  );
}

export type ReferenceChoice = {choice_id: string; title: string; kind: "style" | "conflict"; transfer_guidance: string; requires_adaptation: boolean; [key: string]: unknown};
export type WritingLibraryUsage = { status: "available" | "attached" | "adopted"; selected_count: number; style_count?: number; conflict_count?: number; selected_candidate_ids?: string[]; selected_style_ids?: string[]; selected_conflict_ids?: string[]; update_available?: boolean; error?: string };
export async function getWritingLibraryUsage(workflowId: string, workspace: string) {
  const query = new URLSearchParams({ workflow_id: workflowId, workspace });
  return request<{ items: Record<string, WritingLibraryUsage> }>(`/novel-console/library-usage?${query}`);
}

export async function getNovelAdoptedWriting(workflowId: string, workspace: string) {
  const query = new URLSearchParams({ workflow_id: workflowId, workspace });
  return request<{ version: number; selected_candidate_ids: string[]; selected_style_ids: string[]; selected_conflict_ids: string[]; styles: Array<{choice_id: string; title: string; guidance: string}>; conflicts: Array<{choice_id: string; title: string; guidance: string}>; mechanisms: Array<{candidate_id: string; mechanism: string}> }>(`/novel-console/adopted-writing?${query}`);
}

export async function getNovelReferenceCandidates(workflowId: string, workspace: string) {
  const query = new URLSearchParams({ workflow_id: workflowId, workspace });
  return request<{candidates: Array<Record<string, unknown>>; candidates_sha256?: string; style_choices: ReferenceChoice[]; conflict_choices: ReferenceChoice[]; reference_choices_sha256: string}>(`/novel-console/reference-candidates?${query}`);
}

type LibraryPublishPayload = {
  workflow_id: string; workspace: string; name: string; genres?: string[]; pov?: string[]; tone?: string[]; language?: string;
  task_id?: string;
};
export function publishWritingLibrary(payload: LibraryPublishPayload & { automatic: true; task_id: string }): Promise<{ item: WritingLibraryItem | null; removed?: boolean }>;
export function publishWritingLibrary(payload: LibraryPublishPayload & { automatic?: false }): Promise<{ item: WritingLibraryItem }>;
export async function publishWritingLibrary(payload: LibraryPublishPayload & { automatic?: boolean }) {
  return request<{ item: WritingLibraryItem | null; removed?: boolean }>("/novel-console/library/publish", {
    method: "POST", body: JSON.stringify(payload),
  });
}

export async function attachWritingLibrary(payload: { workflow_id: string; workspace: string; library_id: string; refresh?: boolean }) {
  return request<{ library_id: string; already_attached?: boolean; usage?: WritingLibraryUsage; candidates: { candidates: Array<Record<string, unknown>>; candidates_sha256?: string } }>("/novel-console/library/attach", {
    method: "POST", body: JSON.stringify(payload),
  });
}

export type NovelProgress = { percent: number; completed_count: number; total_count: number; label: string; chapter_count: number; can_download: boolean; export_current: boolean; reader_verdict: string };
export async function getNovelProgress(workflowId: string, workspace: string) {
  const query = new URLSearchParams({ workflow_id: workflowId, workspace });
  return request<NovelProgress>(`/novel-console/progress?${query}`);
}

export async function syncNovelProgressHistory(workflowId: string, workspace: string) {
  return request<{ synced: Array<{ stage: string; workflow_id: string; task_id: string }>; revision: number }>(
    "/novel-console/progress/sync-history",
    { method: "POST", body: JSON.stringify({ workflow_id: workflowId, workspace }) }
  );
}

export async function stopTask(workflowId: string, taskId: string) {
  return request<{ success: boolean; message: string; task_id?: string }>(
    `/workflows/${workflowId}/tasks/${taskId}/stop`,
    { method: "POST" }
  );
}

export async function getNodeMessages(workflowId: string, taskId: string, nodeId: string) {
  return request<import("../types").NodeMessageResponse>(
    `/workflows/${workflowId}/tasks/${taskId}/nodes/${nodeId}/messages`
  );
}

export async function resolveApproval(
  workflowId: string, taskId: string, nodeId: string,
  approved: boolean, reason: string = "",
) {
  return request<{ success: boolean; message: string }>(
    `/workflows/${workflowId}/tasks/${taskId}/resolve-approval/${nodeId}`,
    { method: "POST", body: JSON.stringify({ approved, reason }) },
  );
}

export async function fetchNodeTypes() {
  return request<import("../types").NodeTypeOption[]>("/workflows/node-types/list");
}

// ============ 配置管理 API ============

export async function fetchConfig() {
  return request<import("../types").ConfigResponse>("/config");
}

export async function updateConfig(updates: Record<string, string | number | boolean>, persist: boolean = true) {
  return request<import("../types").UpdateConfigResponse>("/config", {
    method: "PUT",
    body: JSON.stringify({ updates, persist }),
  });
}

// ============ 审批 API ============

export async function fetchPendingApprovals() {
  return request<{ approvals: import("../types").ApprovalRequest[]; total: number }>("/approvals/pending");
}

export async function approveRequest(requestId: string) {
  return request<{ success: boolean; message: string }>(`/approvals/${requestId}/approve`, {
    method: "POST",
  });
}

export async function rejectRequest(requestId: string, reason: string = "") {
  return request<{ success: boolean; message: string }>(`/approvals/${requestId}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

// ============ Workspace API ============

export async function fetchWorkspaceTree(sessionId: string) {
  return request<{
    workspace: string;
    entries: { path: string; type: "file" | "directory" }[];
    total: number;
  }>(`/workspace/${sessionId}/tree`);
}

export async function fetchWorkspaceFile(sessionId: string, path: string) {
  return request<{ path: string; content: string; size: number }>(
    `/workspace/${sessionId}/file?path=${encodeURIComponent(path)}`
  );
}

export async function uploadWorkspaceAttachment(sessionId: string, file: File) {
  return request<{
    name: string;
    relative_path: string;
    absolute_path: string;
    size: number;
  }>(
    `/workspace/${encodeURIComponent(sessionId)}/attachments?filename=${encodeURIComponent(file.name)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: file,
    },
  );
}

// ============ Sections 配置 API ============

export async function updateSection(name: string, updates: Partial<import("../types").PromptSectionData>) {
  return request<{ success: boolean; message: string }>(`/prompt-sections/${name}`, {
    method: "PUT",
    body: JSON.stringify(updates),
  });
}

export async function updateSections(sections: import("../types").PromptSectionData[], promptType: string = "main") {
  return request<{ success: boolean; message: string }>(`/prompt-sections?prompt_type=${promptType}`, {
    method: "PUT",
    body: JSON.stringify({ sections }),
  });
}

export async function addSection(section: import("../types").PromptSectionData) {
  return request<{ success: boolean; message: string }>("/prompt-sections", {
    method: "POST",
    body: JSON.stringify(section),
  });
}

export async function deleteSection(name: string) {
  return request<{ success: boolean; message: string }>(`/prompt-sections/${name}`, {
    method: "DELETE",
  });
}

export async function reloadSections() {
  return request<{ success: boolean; message: string }>("/prompt-sections/reload", {
    method: "POST",
  });
}

// ============ Agent 定义配置 API ============

export async function updateAgentDefinition(agentType: string, updates: Partial<import("../types").AgentDefinitionData>) {
  return request<{ success: boolean; message: string }>(`/agent-definitions/${agentType}`, {
    method: "PUT",
    body: JSON.stringify(updates),
  });
}

export async function addAgentDefinition(agent: import("../types").AgentDefinitionData) {
  return request<{ success: boolean; message: string }>("/agent-definitions", {
    method: "POST",
    body: JSON.stringify(agent),
  });
}

export async function deleteAgentDefinition(agentType: string) {
  return request<{ success: boolean; message: string }>(`/agent-definitions/${agentType}`, {
    method: "DELETE",
  });
}

export async function reloadAgentDefinitions() {
  return request<{ success: boolean; message: string }>("/agent-definitions/reload", {
    method: "POST",
  });
}

// ============ Skills Groups API ============

export async function fetchSkillGroups() {
  return request<{ groups: import("../types").SkillGroup[] }>("/skills/groups");
}

export async function createSkillGroup(group: { id: string; name: string; description?: string }) {
  return request<{ success: boolean; group: import("../types").SkillGroup }>("/skills/groups", {
    method: "POST",
    body: JSON.stringify(group),
  });
}

export async function updateSkillGroup(groupId: string, updates: { name?: string; description?: string }) {
  return request<{ success: boolean }>(`/skills/groups/${groupId}`, {
    method: "PUT",
    body: JSON.stringify(updates),
  });
}

export async function deleteSkillGroup(groupId: string) {
  return request<{ success: boolean; message: string }>(`/skills/groups/${groupId}`, {
    method: "DELETE",
  });
}

export async function setSkillGroups(skillId: string, groupIds: string[]) {
  return request<{ success: boolean }>(`/skills/${skillId}/groups`, {
    method: "PUT",
    body: JSON.stringify({ group_ids: groupIds }),
  });
}

export async function fetchSkillsInGroup(groupId: string) {
  return request<{ skill_ids: string[] }>(`/skills/groups/${groupId}/skills`);
}

// ============ Rules Groups API ============

export async function fetchRuleGroups() {
  return request<{ groups: import("../types").RuleGroup[] }>("/rules/groups");
}

export async function createRuleGroup(group: { id: string; name: string; description?: string }) {
  return request<{ success: boolean; group: import("../types").RuleGroup }>("/rules/groups", {
    method: "POST",
    body: JSON.stringify(group),
  });
}

export async function updateRuleGroup(groupId: string, updates: { name?: string; description?: string }) {
  return request<{ success: boolean }>(`/rules/groups/${groupId}`, {
    method: "PUT",
    body: JSON.stringify(updates),
  });
}

export async function deleteRuleGroup(groupId: string) {
  return request<{ success: boolean; message: string }>(`/rules/groups/${groupId}`, {
    method: "DELETE",
  });
}

export async function fetchRulesInGroup(groupId: string) {
  return request<{ rule_ids: string[] }>(`/rules/groups/${groupId}/rules`);
}

export async function setRuleGroups(ruleId: string, groupIds: string[]) {
  return request<{ success: boolean }>(`/rules/${ruleId}/groups`, {
    method: "PUT",
    body: JSON.stringify({ group_ids: groupIds }),
  });
}

// ============ Agent Visibility API ============

export async function updateAgentVisibility(agentType: string, visibility: { visible_skill_group_ids?: string[]; visible_rule_group_ids?: string[] }) {
  return request<{ success: boolean }>(`/agent-definitions/${agentType}/visibility`, {
    method: "PUT",
    body: JSON.stringify(visibility),
  });
}

// ============ 用户消息注入 API ============

export async function fetchUserInjectionSections() {
  return request<{
    sections: import("../types").PromptSectionData[];
    version: string;
    last_updated: string;
  }>("/user-injection");
}

export async function updateUserInjectionSections(sections: import("../types").PromptSectionData[]) {
  return request<{ success: boolean; message: string }>("/user-injection", {
    method: "PUT",
    body: JSON.stringify({ sections }),
  });
}

export async function addUserInjectionSection(section: import("../types").PromptSectionData) {
  return request<{ success: boolean; section: import("../types").PromptSectionData }>("/user-injection/sections", {
    method: "POST",
    body: JSON.stringify(section),
  });
}

export async function deleteUserInjectionSection(sectionName: string) {
  return request<{ success: boolean; message: string }>(`/user-injection/sections/${sectionName}`, {
    method: "DELETE",
  });
}

export async function renameSection(oldName: string, newName: string, promptType: string = "main") {
  return request<{ success: boolean; message: string }>(`/prompt-sections/${oldName}/rename?prompt_type=${promptType}`, {
    method: "POST",
    body: JSON.stringify({ new_name: newName }),
  });
}

// ============ Tool Groups CRUD API ============

export async function createToolGroup(group: { id: string; name: string; description?: string }) {
  return request<{ success: boolean; group: import("../types").ToolGroup }>("/tools/groups", {
    method: "POST",
    body: JSON.stringify(group),
  });
}

export async function updateToolGroup(groupId: string, updates: { name?: string; description?: string }) {
  return request<{ success: boolean }>(`/tools/groups/${groupId}`, {
    method: "PUT",
    body: JSON.stringify(updates),
  });
}

export async function deleteToolGroup(groupId: string) {
  return request<{ success: boolean; message: string }>(`/tools/groups/${groupId}`, {
    method: "DELETE",
  });
}

// ============ 模型供应商 API ============

export async function getModelProviders() {
  return request<{
    providers: Record<string, Omit<import("../types").ModelProvider, "id">>;
    default_provider: string | null;
    default_model: string | null;
  }>("/model-providers");
}

export async function getProviderSchemas() {
  return request<{
    schemas: Record<string, import("../types").ProviderSchema>;
  }>("/model-providers/schemas");
}

export async function updateModelProvider(providerId: string, updates: Partial<import("../types").ModelProvider>) {
  return request<{ success: boolean; message: string }>(`/model-providers/${providerId}`, {
    method: "PUT",
    body: JSON.stringify(updates),
  });
}

export async function deleteModelProvider(providerId: string) {
  return request<{ success: boolean; message: string }>(`/model-providers/${providerId}`, {
    method: "DELETE",
  });
}

export async function addModelProvider(provider: {
  provider_id: string;
  provider_type: string;
  name: string;
  base_url: string;
  api_key?: string;
  models?: string[];
  maxContextTokens?: number;
  models_config?: import("../types").ModelProvider["models_config"];
  hyperparameter_values?: Record<string, unknown>;
}) {
  return request<{ success: boolean; message: string }>("/model-providers", {
    method: "POST",
    body: JSON.stringify(provider),
  });
}

export async function discoverProviderModels(input: {
  provider_id: string;
  provider_type?: string;
  base_url?: string;
  api_key?: string;
}) {
  return request<{ models: string[] }>("/model-providers/models/discover", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function prioritizeModelProvider(providerId: string) {
  return request<{ success: boolean; message: string }>(
    `/model-providers/${providerId}/priority`,
    { method: "PUT" },
  );
}

export async function setDefaultModel(providerId: string, modelName: string) {
  return request<{ success: boolean; message: string }>("/model-providers/default", {
    method: "PUT",
    body: JSON.stringify({ provider_id: providerId, model_name: modelName }),
  });
}

export async function getAllModels() {
  return request<{
    models: {
      value: string;
      label: string;
      display_name: string;
      provider_id: string;
      model_name: string;
      provider_type: string;
      model_params: Record<string, import("../types").ModelParamFieldSchema>;
      reasoning_efforts: string[];
      category: string;
    }[];
  }>("/models/all");
}

export async function fetchDefaultModelParams() {
  return request<{
    default_params: Record<string, unknown>;
  }>("/model-params/defaults");
}

// ============ 会话控制 API ============

export async function abortSession(sessionId: string) {
  return request<{ success: boolean; message: string }>(`/sessions/${sessionId}/abort`, {
    method: "POST",
  });
}

export async function compressSession(sessionId: string) {
  return request<{ success: boolean; message: string }>(`/sessions/${sessionId}/compress`, {
    method: "POST",
  });
}

// ============ 预设短语 API ============

export async function fetchPresetPhrases(): Promise<import("../types").PresetPhrase[]> {
  return request<import("../types").PresetPhrase[]>("/preset-phrases");
}

export async function createPresetPhrase(data: { label: string; content: string }) {
  return request<import("../types").PresetPhrase>("/preset-phrases", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updatePresetPhrase(phraseId: string, data: { label?: string; content?: string }) {
  return request<import("../types").PresetPhrase>(`/preset-phrases/${phraseId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deletePresetPhrase(phraseId: string) {
  return request<{ success: boolean }>(`/preset-phrases/${phraseId}`, {
    method: "DELETE",
  });
}

// ============ 脚本库 API ============

export async function fetchScriptLibraryGroups() {
  return request<import("../types").ScriptLibraryGroup[]>("/workflows/script-library/groups");
}

export async function fetchScriptLibraryScripts(group?: string) {
  const qs = group ? `?group=${encodeURIComponent(group)}` : "";
  return request<import("../types").ScriptLibraryScript[]>(`/workflows/script-library/scripts${qs}`);
}

export async function getLibraryScript(group: string, scriptName: string, type: string = "shell") {
  return request<{ content: string; exists: boolean }>(
    `/workflows/script-library/${encodeURIComponent(group)}/${encodeURIComponent(scriptName)}/script?type=${encodeURIComponent(type)}`
  );
}

export async function saveLibraryScript(group: string, scriptName: string, type: string, content: string) {
  return request<{ success: boolean; message: string }>(
    `/workflows/script-library/${encodeURIComponent(group)}/${encodeURIComponent(scriptName)}/script?type=${encodeURIComponent(type)}`,
    { method: "PUT", body: JSON.stringify({ content }) }
  );
}

export async function deleteLibraryScript(group: string, scriptName: string) {
  return request<{ success: boolean; message: string }>(
    `/workflows/script-library/${encodeURIComponent(group)}/${encodeURIComponent(scriptName)}`,
    { method: "DELETE" }
  );
}

export async function getLibraryScriptMeta(group: string, scriptName: string) {
  return request<{ content: string; exists: boolean }>(
    `/workflows/script-library/${encodeURIComponent(group)}/${encodeURIComponent(scriptName)}/meta`
  );
}

export async function saveLibraryScriptMeta(group: string, scriptName: string, content: string) {
  return request<{ success: boolean; message: string }>(
    `/workflows/script-library/${encodeURIComponent(group)}/${encodeURIComponent(scriptName)}/meta`,
    { method: "PUT", body: JSON.stringify({ content }) }
  );
}

export async function deleteLibraryGroup(group: string) {
  return request<{ success: boolean; message: string }>(
    `/workflows/script-library/${encodeURIComponent(group)}`,
    { method: "DELETE" }
  );
}

// ============ Cron API ============

export interface CronScheduleData {
  kind: "once" | "interval" | "cron";
  at?: string | null;
  every_minutes?: number | null;
  expr?: string | null;
}

export interface CronJobData {
  id: string;
  name: string;
  prompt: string;
  schedule: CronScheduleData;
  enabled: boolean;
  agent_type: string;
  model_override: string | null;
  silent_on_empty: boolean;
  max_turns: number;
  next_run_at: string | null;
  last_run_at: string | null;
  last_status: string | null;
  repeat: number | null;
  completed: number;
}

export interface CronStatusData {
  running: boolean;
  total_jobs: number;
  enabled_jobs: number;
  due_jobs: number;
}

export interface CronOutputFile {
  filename: string;
  size: number;
  created_at: string;
}

export async function fetchCronJobs() {
  return request<{ jobs: CronJobData[]; total: number }>("/cron/jobs");
}

export async function createCronJob(data: {
  name: string;
  prompt: string;
  schedule: CronScheduleData;
  agent_type?: string;
  silent_on_empty?: boolean;
  repeat?: number | null;
}) {
  return request<{ success: boolean; job: CronJobData }>("/cron/jobs", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function runCronJobNow(jobId: string) {
  return request<{ success: boolean; message: string }>(`/cron/jobs/${jobId}/run`, {
    method: "POST",
  });
}

export async function updateCronJob(jobId: string, data: {
  name?: string;
  prompt?: string;
  schedule?: CronScheduleData;
  enabled?: boolean;
  agent_type?: string;
  silent_on_empty?: boolean;
}) {
  return request<{ success: boolean; job: CronJobData }>(`/cron/jobs/${jobId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteCronJob(jobId: string) {
  return request<{ success: boolean; message: string }>(`/cron/jobs/${jobId}`, {
    method: "DELETE",
  });
}

export async function fetchCronStatus() {
  return request<CronStatusData>("/cron/status");
}

export async function fetchCronOutput(jobId: string, filename?: string) {
  if (filename) {
    return request<{ job_id: string; filename: string; content: string }>(
      `/cron/output/${jobId}?filename=${encodeURIComponent(filename)}`
    );
  }
  return request<{ job_id: string; files: CronOutputFile[]; total: number }>(`/cron/output/${jobId}`);
}

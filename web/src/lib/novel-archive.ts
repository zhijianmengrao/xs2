/** Presentation labels shared by current JSON outputs and older Markdown archives. */
const FIELD_LABELS: Record<string, string> = {
  snapshot: "当前处境", physical: "身体状态", resources: "资源", emotion: "情绪", knowledge: "所知信息", misbelief: "误解", change: "变化", evidence_position: "依据位置", character_changes: "人物变化", story_changes: "剧情变化", world_time: "世界时间", time_advanced_days: "经过天数", character_name: "人物", field: "变化项目", item: "涉及物品", minor_additions: "新增配角", state_changes: "状态变化", relationship_changes: "关系变化", resource_changes: "资源变化", from: "原记录", to: "实际表现", facts: "确认事实", description_of_change: "变化说明", unplanned: "计划外事件",
  writing_dna: "综合风格概述",
  causal_link: "因果衔接", style_observations: "风格观察", rule: "写法规律", limits: "适用边界", chapter_ending_mode: "本次章末类型",
  candidates: "具体写法", mechanism: "叙事机制", transfer_guidance: "迁移方法", adaptation_guidance: "适配建议", layer: "分析维度", scopes: "适用步骤", application_scope: "适用范围", pov_compatibility: "视角适配", support_count: "证据数量", risk_flags: "风险提示", conflict_patterns: "冲突递进模式", excerpt: "来源片段", source_mode: "来源类型", target_mode: "适用作品类型", reference_mode: "参考作品类型", target_work_mode: "本书类型", recommendations: "推荐写法", reasons: "推荐原因", adaptation_plan: "适配方案", questions: "需要确认", global_risks: "整体风险", next_step: "下一步建议", score: "匹配分数", assistant_reply: "助手建议", impact: "影响", repair_constraints: "返修约束", continue_reading_score: "阅读意愿分数", verdict: "评估结论",
  references: "风格参考", work: "参考作品", tags: "特点标签", learn: "借鉴要点", apply: "本书应用方式", commandments: "写作禁忌",
  expanded_premise: "完整故事前提", conflicting_elements: "冲突因素", foreground: "当前主要压力", possible_direction: "可能的发展方向",
  anger: "愤怒时的表现", lying: "说谎时的表现", nervous: "紧张时的表现", who_knows: "知情人物", who_doesnt_know_but_should: "应知情但尚未知道的人物",
  core_laws: "核心法则", space_time: "时空地理", society: "社会与权力", history_culture: "历史与文化", existence: "存在基础", information: "信息传播",
  essence: "核心概述", name: "名称", true_name: "本名", aliases: "别名", title: "标题", description: "说明", summary: "概要", content: "内容", body: "内容",
  power_system: "力量体系", axioms: "运行规则", taboos: "禁忌", power_manifestation: "外在表现", statement: "规则说明", cost: "代价", boundary: "适用边界", enforcement: "必然后果",
  world_layout: "世界格局", key_locations: "关键地点", ecology: "生态环境", era: "时代背景", environment_texture: "环境质感", terrain: "地形", feature: "特征", risk: "风险", controlling_force: "控制势力",
  races: "族群", class_structure: "阶层结构", political_system: "权力制度", forces: "主要势力", force_relations: "势力关系", power_visibility: "权力表现", traits: "特点", population: "人口", social_status: "社会地位", type: "类型", base_of_power: "权力基础", goals: "目标", methods: "手段", source: "来源", target: "对象", relation: "关系", tension_point: "矛盾焦点",
  major_events: "重大历史事件", religions: "信仰", customs: "习俗", economy: "经济", daily_slice: "日常生活", event: "事件", lasting_impact: "持续影响", calendar: "历法", lifespan: "寿命", death: "死亡规则", disease_and_birth: "疾病与生育",
  info_speed: "传播速度", knowledge_medium: "知识载体", info_barriers: "信息壁垒", rumor_and_truth: "传闻与事实",
  beliefs: "信念", character: "角色", characters: "人物", core_belief: "核心信念", belief_source: "信念来源", author_perspective: "作者视角", role: "身份定位", gender: "性别", age: "年龄", world_position: "社会位置", world_anchor: "世界观联系", relationships: "人物关系", origin_class: "出身", affiliation: "所属势力", social_role: "社会角色", stance_on_core_conflict: "核心矛盾中的立场", embodies_rule: "体现的规则", shaped_by_rule: "规则造成的影响", may_challenge_rule: "可能挑战的规则", nature: "关系性质", meaning_to_character: "对人物的意义", hidden_tension: "潜在矛盾", default_attitude: "通常态度",
  core_desire: "核心欲望", desire: "欲望", fear: "恐惧", deep_fear: "深层恐惧", deepest_fear: "深层恐惧", secret: "秘密", secrets: "秘密", weakness: "弱点", strength: "优势", motivation: "动机", wound: "旧伤", flaw: "缺陷", arc: "成长轨迹", appearance: "外貌", personality: "性格", background: "经历", speaking_style: "说话方式", voice: "声音定位", voices: "角色声线", syntax_fingerprint: "句法特点", cognitive_bias: "认知偏差", core_voice: "核心声线", core_voice_position: "核心声音定位", speech_patterns: "说话习惯", catchphrases: "惯用表达",
  story_plan: "故事规划", story_engine: "故事引擎", premise: "故事创意", genre: "题材", core_conflict: "核心矛盾", core_question: "核心问题", theme: "主题", themes: "主题", tone_reference: "基调参考", tone: "基调", macro: "整体结构", meso: "中段结构", micro: "场景推进", plot: "剧情", plot_points: "剧情节点", main_plot: "主线", subplots: "支线", ending: "结局", stakes: "利害关系", protagonist: "主角", antagonist: "对手", forces_in_motion: "推动力量", driving_force: "驱动力", issues: "待确认问题",
  style_profile: "统一风格基线", narrative_pov: "叙事视角", narrative_voice: "叙事声音", language: "语言", sentence_length: "句长偏好", sentence_rhythm: "句子节奏", vocabulary: "用词", imagery: "意象", dialogue: "对话", pacing: "叙事节奏", emotional_tone: "情绪基调", prose_style: "语言风格", narrative_distance: "叙述距离", constraints: "约束", forbidden: "写作禁忌", dos: "写作要求", donts: "写作禁忌", style_rules: "风格规则", examples: "示例",
  volume: "卷", volumes: "分卷", volume_number: "卷号", volume_title: "卷名", volume_outline: "卷纲", near_term_outline: "近期章节纲", chapter: "章节", chapters: "章节安排", chapter_number: "章节号", chapter_range: "章节范围", chapter_start: "起始章节", chapter_end: "结束章节", start_chapter: "起始章节", end_chapter: "结束章节", beats: "情节节拍", scenes: "场景", goal: "目标", obstacle: "阻碍", action: "行动", attempt: "应对行动", resolution: "解决方式", result: "结果", next_obstacle: "后续阻碍", conflict: "冲突", conflicts: "冲突记录", conflict_chain: "冲突递进链", trigger: "触发原因", trigger_condition: "触发条件", foreshadowing: "伏笔", hooks: "伏笔登记", debts: "叙事债务", payoff: "回收方式", payoff_window: "回收窗口", expected_payoff: "预计回收", expected_payoff_chapter: "预计回收章节", status: "状态", state: "当前状态", planted_in: "埋设位置", resolved_in: "回收位置", deadline: "期限", notes: "备注", evidence: "依据", remaining_questions: "未解决问题", updated_at: "更新时间", created_at: "登记时间", id: "记录编号",
  engine: "故事驱动", external: "外部压力", internal: "内在矛盾", relational: "关系矛盾", drives: "推动因素", growth_path: "成长路径", growth_direction: "成长方向", corruption_direction: "堕落方向", conflict_layers: "冲突层次", conflict_engine: "冲突引擎", tension_archetypes: "张力类型", progression_loop: "推进循环", mystery_box: "悬念核心", protagonist_trap: "主角困局", dual_story: "双重故事", emotional_rhythm: "情绪节奏", payoff_grammar: "回收规律", reader_promise: "读者期待", target_readers: "目标读者", genre_notes: "题材说明",
  style: "写作风格", style_tone: "风格基调", narrative: "叙述方式", narrative_persona: "叙述者气质", pov: "叙事视角", pov_firewall: "视角边界", dominant_sentence_type: "常用句式", dialogue_ratio: "对话比例", opening_hook: "开局钩子", middle_pacing: "中段节奏", ending_hook: "结尾表现", ending_flavor: "结尾余味", emotional_aftertaste: "情绪余韵", recommended_methods: "推荐写法", avoid_methods: "避免的写法", commercial_tags: "题材标签", core_tags: "核心标签", key_tags: "关键标签", emotion_patterns: "情绪模式", emotion_arcs: "情绪变化", tension_level: "紧张程度", atmosphere: "氛围", suspense: "悬念",
  deep_desire: "深层欲望", bottom_line: "底线", key_trauma: "关键创伤", internal_contradiction: "内在矛盾", stress_response: "压力反应", physical_state: "身体状态", current_goal: "当前目标", current_state: "当前状态", current_constraints: "当前限制", emotional_baseline: "情绪底色", possessions: "持有物", speech_style: "说话风格", sentence_preference: "句式偏好", pause_habit: "停顿习惯", forbidden_speech: "不会说的话", voice_positioning: "声线定位", reaction_when_crossed: "底线被触犯时的反应", contrast_detail: "反差细节", death_detail: "死亡描写", departure_detail: "离场细节", first_appearance: "首次登场", last_appearance: "最近登场", last_active_chapter: "最近活跃章节", story_role: "故事作用", relation_to_protagonist: "与主角的关系", arc_potential: "成长潜力", impact_on_behavior: "对行为的影响", identity: "身份", surface_goal: "表层目标", surface_relation: "表面关系", hidden_info: "隐秘信息", exposure_consequence: "暴露后果",
  surface: "表层", underlying: "深层", undercurrents: "暗线", undercurrent_progress: "暗线进展", nodes: "关键节点", key_beats: "关键情节", key_choice: "关键抉择", climax: "高潮", moral_dilemma: "道德困境", next_bridge: "后续衔接", chapter_goal: "本章目标", scene: "场景", location: "地点", start: "开始", mid: "中段", end: "结束", acts: "幕结构", duration: "持续时间", character_motivation: "人物动机", motivations: "动机", narrative_function: "叙事作用", planned: "计划内进展", actual: "实际进展", deviated: "偏离之处", landed: "已落实", missed: "未落实", decision: "决定", consequence: "后果", progress: "进展", priority: "优先级", promise: "叙事承诺", pending_promises: "待兑现承诺", hook_intent: "伏笔意图", involves: "涉及人物", chapter_created: "登记章节", chapter_resolved: "解决章节", source_chapter: "来源章节", last_advanced: "最近推进", original_intensity: "初始强度", current_intensity: "当前强度", trigger_chapter: "触发章节", trigger_event: "触发事件", source_event: "起因", revealed_chapter: "揭示章节", source_start: "起始位置", source_end: "结束位置", severity: "严重程度", reason: "原因", note: "备注", judgment: "判断", suggestion: "建议", conditions: "条件", condition: "条件", advance: "推进", resolve: "回收", defer_ids: "暂缓记录", resolve_ids: "已回收记录", new_hooks: "新增伏笔", new_debts: "新增债务", confidence: "把握程度",
};

export function archiveLabel(key: string): string {
  const normalized = key.trim().replace(/([a-z])([A-Z])/g, "$1_$2").toLowerCase().replace(/[\s-]+/g, "_");
  return FIELD_LABELS[normalized] || (/[\u3400-\u9fff]/.test(key) ? key : "补充信息");
}

export type ArchiveParseResult = { parsed: true; value: unknown } | { parsed: false };
export function parseArchiveJSON(content: string): ArchiveParseResult {
  let text = content.trim().replace(/^```(?:json)?\s*\n([\s\S]*?)\n```$/i, "$1").trim();
  if (!/^[{["]/.test(text)) return { parsed: false };
  try {
    let value: unknown = JSON.parse(text);
    // Some model outputs are JSON encoded inside a JSON string.
    for (let i = 0; i < 3 && typeof value === "string"; i++) {
      text = value.trim();
      if (!/^[{["]/.test(text)) break;
      try { value = JSON.parse(text); } catch { break; }
    }
    return { parsed: true, value };
  } catch { return { parsed: false }; }
}

export function archiveScalar(value: unknown, key = ""): string {
  if (value === null || value === undefined || value === "") return "暂无信息";
  if (typeof value === "boolean") return value ? "是" : "否";
  const text = String(value);
  if (/[\u3400-\u9fff]/.test(key)) key = Object.keys(FIELD_LABELS).find(field => FIELD_LABELS[field] === key) || key;
  const choices: Record<string, string> = { first_person: "第一人称", third_person: "第三人称", short_full: "短篇全文", serial_opening: "长篇开局", serial_chapter: "长篇章节", serial_arc: "长篇当前卷", serial_chapters: "长篇章节样本", general: "通用", continue: "普通连载章节", book_final: "本书终章" };
  const statuses: Record<string, string> = { pending: "待推进", open: "未解决", active: "推进中", planted: "已埋设", triggered: "已触发", resolved: "已解决", paid: "已偿还", closed: "已回收", overdue: "已超期", suspended: "暂时悬置" };
  const fieldChoices: Record<string, Record<string, string>> = {
    layer: { language: "语言", structure: "结构", narrative_lens: "叙事镜头", dialogue: "对话", imagery: "意象", theme: "主题", character: "人物写法" },
    confidence: { high: "较高", medium: "中等", low: "较低" },
    priority: { high: "优先处理", medium: "建议处理", low: "细节优化" },
    severity: { high: "高", medium: "中", low: "低" },
    pov_compatibility: { direct: "可直接参考", adapt: "需要适配", adaptable: "需要适配", risky: "存在风险" },
    decision: { recommend: "推荐采用", adapt: "适配后采用", caution: "谨慎采用", reject: "不建议采用" },
    verdict: { pass: "通过", revise: "建议返修", reject: "需要重写", strong: "较强", slow: "偏慢", clear: "清晰", unclear: "不够明确" },
    scopes: { build: "世界观", character: "角色创作", "story-plan": "故事规划", outline: "大纲", mvp: "正文创作", polish: "润色", "post-hoc": "质量审核" },
    author_perspective: { right: "认可", wrong: "不认可", complex: "复杂立场", ambiguous: "保留判断" },
  };
  return choices[text] || ((key === "status" || key === "state") ? statuses[text] : undefined) || fieldChoices[key]?.[text] || text;
}

function toReadableMarkdown(value: unknown, level = 3): string {
  if (Array.isArray(value)) return value.map(item => typeof item === "object" && item !== null ? toReadableMarkdown(item, level) : `- ${archiveScalar(item)}`).join("\n\n");
  if (value && typeof value === "object") return Object.entries(value).map(([key, item]) => {
    const title = archiveLabel(key);
    return typeof item === "object" && item !== null ? `${"#".repeat(Math.min(level, 6))} ${title}\n\n${toReadableMarkdown(item, level + 1)}` : `- **${title}**：${archiveScalar(item, key)}`;
  }).join("\n\n");
  return archiveScalar(value);
}

export function readableArchiveMarkdown(content: string): string {
  return content.replace(/```(json)?\s*\n([\s\S]*?)```/gi, (block, language, body) => {
    const parsed = parseArchiveJSON(body);
    if (parsed.parsed) return toReadableMarkdown(parsed.value);
    return language ? "这部分档案格式不完整，暂时无法展示。" : block;
  }).split(/\r?\n/).map(line => {
    const heading = line.match(/^(#{1,6}\s+)([A-Za-z][A-Za-z _-]*)(\s*)$/);
    if (heading) return `${heading[1]}${archiveLabel(heading[2])}`;
    const field = line.match(/^(\s*[-*]\s+)([A-Za-z\u3400-\u9fff][A-Za-z\u3400-\u9fff _-]*)([：:]\s*)(.*)$/);
    if (field) return `${field[1]}${archiveLabel(field[2])}${field[3]}${archiveScalar(field[4], field[2].trim().replace(/\s+/g, "_"))}`;
    return line;
  }).join("\n");
}

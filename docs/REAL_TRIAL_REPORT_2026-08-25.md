# 真实测试用例全链路试跑记录（2026-08-25）

> **纠错说明（2026-08-25）**：本报告中“达康书记摇车窗”和“秋日下午茶”被选为 `reference_video` 的结论已确认为错误，不应作为后续 Skill 或链路设计依据。真实设计链路的最终视频节点都只输入一张首图，应归为 `single_image`。该报告保留的是首次试跑现场和错误样本；修正后的判定规则与“泳池水枪”复测结果见 `docs/CHAIN_SELECTION_CORRECTION_TRIAL_2026-08-25.md`。

## 1. 试跑目标与边界

本次使用两条真实热点视频，验证“设计师提交热点视频 → Agent 产出可执行的节点化特效生成链路方案”能否完整跑通。

本次使用 `--manual` 协作模式：

- Step 1、2、3B、4、6 的业务判断由 Codex 根据正式 Prompt 和结构化输入完成；
- Step 1 的视频元数据、一次性抽帧和时间线总览由 FFmpeg 完成；
- Step 3A 使用本地 `BAAI/bge-small-zh-v1.5` 对 23 条正式案例进行真实召回；
- Step 5 使用确定性素材处理器；
- Step 7 使用确定性校验和交付生成器；
- 本次不调用真实图像/视频生成模型，因此交付物是链路方案，不是生成后的特效视频。

## 2. 总体结果

| 测试用例 | 任务状态 | 最终链路 | 节点数 | 固定素材 | 最终交付 |
|---|---|---|---:|---:|---|
| 达康书记摇车窗 | completed | reference_video | 1 | 1 | `outputs/trial-dakang-window/production-plan.md` |
| 秋日下午茶 | completed | reference_video | 2 | 2 | `outputs/trial-autumn-tea/production-plan.md` |

两条任务的 Step 1–7 全部完成，Schema 0.3.0 校验、素材就绪校验、节点依赖校验、Prompt 完整性校验和案例引用校验均通过。

## 3. 用例一：达康书记摇车窗

### Step 1：视频客观理解

- 视频：7.21 秒，676 × 1194，无音频。
- 抽取 16 张原始分辨率候选帧，生成时间线总览。
- 关键帧：`frame_0001`、`frame_0010`、`frame_0013`、`frame_0016`。
- 核心观察：灰猫坐在车窗旁，转头后被持续上升的玻璃逐步遮挡。

### Step 2：卖点判断

- 主卖点：让用户的宠物坐在行驶车辆的车窗旁，随车窗缓慢上升被逐步遮住，形成生活化又有幽默感的微叙事。
- 标签：`pet_anthropomorphism`、`state_transformation`、`physical_interaction`、`reveal_or_micro_narrative`。

### Step 3：RAG 与链路选择

- 本地 Embedding Top 6：`pet_fitness`、`dj_pet`、`pet_hot_dance`、`pet_diving`、`pet_head_shake_dance`、`pet_grimace`。
- 选择 `reference_video`：卖点依赖车窗上升、透明玻璃遮挡、宠物转头和运镜的连续时序。
- 覆盖缺口：历史案例覆盖宠物动作迁移，但没有直接覆盖动态玻璃遮挡。

### Step 4：节点链路设计

- 运行时输入槽位：`user_pet_image`，未来特效使用时才由终端用户提供。
- 固定素材：`reference_video`，来自本次提交的热点视频。
- 执行节点：`generate_video`，模型为 `Kling 3.0 Omni`，输入为参考视频和用户宠物图。

### Step 5：固定素材准备

- 热点视频被复制到任务 `materials/` 目录。
- 文件存在、尺寸和时长均通过检查，`ready_for_prompting = true`。
- 没有要求本次任务提前具备用户宠物图。

### Step 6：节点 Prompt

- 为 `generate_video` 生成一段包含正向描述与排除约束的完整 Prompt，并记录素材引用和案例依据。
- Prompt 按 0–3.5 秒、3.5–5.0 秒、5.0–7.21 秒描述宠物暴露、转头与玻璃上升遮挡。

### Step 7：校验与交付

- 固定素材、节点、Prompt 和案例引用全部通过。
- 保留玻璃穿模、遮挡层级错误、反射导致主体漂移等待试跑风险。

## 4. 用例二：秋日下午茶

### Step 1：视频客观理解

- 视频：5.38 秒，1186 × 1182，无音频。
- 抽取 12 张原始分辨率候选帧，生成时间线总览。
- 关键帧：`frame_0001`、`frame_0006`、`frame_0011`。
- 核心观察：人物在秋日露台端杯饮用，放低杯子后转向远处，暖光和落叶贯穿整段视频。

### Step 2：卖点判断

- 主卖点：将用户主体置于高质感秋日露台下午茶场景，通过端杯饮用、转头凝视与暖色落叶光影形成氛围化人像表演。
- 标签：`style_transformation`、`action_performance`、`scene_spectacle`、`effect_spectacle`。

### Step 3：RAG 与链路选择

- Top 6 中包含 5 条单图案例和 1 条参考视频案例。
- 选择 `reference_video`，并使用同路由的 `birthday_dress_up` 作为有效案例。
- 原因：核心体验不只是秋日风格，还包含端杯、饮用、放低、转头的连续表演和手-杯-嘴物理交互。

### Step 4：节点链路设计

- 运行时输入槽位：`user_image`。
- 固定素材：`autumn_scene_reference` 和 `reference_video`。
- 节点一 `generate_subject_image`：使用 `图片 3.0 Omni` 生成与用户身份、秋日造型和场景对齐的 `subject_image`。
- 节点二 `generate_video`：使用 `Kling 3.0 Omni` 和参考视频驱动上游主体图完成表演。

### Step 5：固定素材准备

- 复用 Step 1 的原始分辨率 `frame_0001` 作为场景参考，没有重复全局抽帧。
- 热点视频作为固定参考视频复制到任务素材目录。
- 两项素材均通过文件、尺寸和时长检查，`ready_for_prompting = true`。

### Step 6：节点 Prompt

- 分别为 `generate_subject_image` 和 `generate_video` 生成 Prompt，没有把两个节点的任务混在一起。
- 生图 Prompt 负责主体身份、造型、场景、构图和道具；生视频 Prompt 负责连续表演、时序和物理交互。

### Step 7：校验与交付

- 固定素材、运行时槽位、上游节点输出和 Prompt 引用可唯一解析。
- 保留手指畸形、杯口穿模、身份漂移、落叶遮脸和参考案例覆盖偏弱等风险。

## 5. 设计师最终会看到什么

当前主交付是 `production-plan.md`，而不是 `task-result.json`。设计师看到的内容包含：

1. 热点视频内容和核心卖点；
2. 选定链路、选择理由和参考案例；
3. 未来特效使用时需要的输入槽位；
4. 本次设计任务准备好的固定素材；
5. 按依赖顺序排列的每个执行节点；
6. 每个模型节点的模型、输入、输出、参数、完整 Prompt、约束和案例依据；
7. 真实生产前必须验证的风险与能力缺口。

`task-result.json` 保留 Step 1–7 的完整结构化输出、状态、尝试次数和 issue，用于机器继续执行、恢复和审计，不是面向设计师的主页面。

## 6. 全链路耗时

| 测试用例 | 任务创建 | Step 7 完成 | 本次墙钟耗时 |
|---|---|---|---:|
| 达康书记摇车窗 | 2026-08-25 04:24:57 UTC | 2026-08-25 05:16:06 UTC | 51 分 08.8 秒 |
| 秋日下午茶 | 2026-08-25 04:25:00 UTC | 2026-08-25 05:16:06 UTC | 51 分 06.1 秒 |

这个时间是本次“开发调试试跑”的真实墙钟时间，其中包含：

- Codex 阅读请求、生成并提交 5 个人工步骤结果的等待时间；
- 首次确认/加载 BGE 权重的冷启动时间；
- 发现并修复 `--manual` 未接 Step 3 真实召回、Step 3 人工请求被误标为 `blocked` 的时间；
- 审阅中间输出并编写人工 JSON 的时间。

因此该数字不代表未来接入真实模型 API 后的产品响应时间。任务状态中记录的单次最终提交时长只是 JSON 校验和状态落盘时间，也不能代表模型推理时间。稳态耗时应在 DeepSeek/多模态 API 接入后用统一计时埋点重新测量。

## 7. 本次试跑发现并处理的问题

1. 安装 `sentence-transformers` 只说明代码依赖已安装，不等于 BGE 模型权重已缓存；本次已完成权重下载和真实召回。
2. `--manual` 原先将 Step 3 置为占位阻塞，已改为“本地 Embedding 召回 + Codex 链路选择”。
3. Step 3 的 Codex 请求原先被包装为 `blocked`，与提交命令只接受 `needs_input` 冲突；已统一为可恢复的 `needs_input`。
4. 两条视频都被选为参考视频链路。这与两者均依赖连续动作/物理交互的卖点一致，但仍需用明确的单图驱动视频继续验证分流边界。
5. 现有模型能力表只能支持初步选型；玻璃动态遮挡、手-杯-嘴交互等具体能力必须由真实模型试跑验证。

## 8. 可追溯产物

### 达康书记摇车窗

- 设计师交付：`outputs/trial-dakang-window/production-plan.md`
- Step 1–7 完整状态与输出：`outputs/trial-dakang-window/task-result.json`
- RAG 快照：`outputs/trial-dakang-window/case-snapshot.json`
- 时间线总览：`outputs/trial-dakang-window/video-analysis/timeline-overview.jpg`
- 固定素材：`outputs/trial-dakang-window/materials/`

### 秋日下午茶

- 设计师交付：`outputs/trial-autumn-tea/production-plan.md`
- Step 1–7 完整状态与输出：`outputs/trial-autumn-tea/task-result.json`
- RAG 快照：`outputs/trial-autumn-tea/case-snapshot.json`
- 时间线总览：`outputs/trial-autumn-tea/video-analysis/timeline-overview.jpg`
- 固定素材：`outputs/trial-autumn-tea/materials/`

# 特效生成 Agent 阶段性交接说明

> 交接日期：2026-08-25  
> 文档性质：当前仓库的时点快照  
> 长期设计与协作事实源：[`DEVELOPMENT_GUIDE.md`](DEVELOPMENT_GUIDE.md)

## 1. 一句话说明现状

项目已经从“只有 Skill 和 Prompt”进入“有可恢复任务状态、可人工调用 Codex、可处理素材、可交付生产方案”的人工 MVP 阶段。

Step 1–7 的运行边界已经接通；Step 3/RAG 已实现本地 Embedding 召回、Top 6 任务快照和链路选择执行器。`--manual` 模式由 Codex 处理 Step 1/2/3B/4/6，Step 3A 使用真实本地 Embedding；`--deepseek` 模式可使用 Step 1 Codex 结果，再由 DeepSeek 执行 Step 2/3B/4/6。

## 2. 项目要解决什么

最终目标是公司内部特效生产 Agent：

```text
输入热点视频
  → 理解视频
  → 提炼卖点和复刻目标
  → 召回历史案例并选择生成链路
  → 设计节点、模型和素材
  → 准备素材并编写节点 Prompt
  → 交付结构化方案
  → 后续再转为 Keffect、跑批验证和工作台
```

当前 MVP 优先让“链路分析与方案设计”能跑起来，不执行 Keffect 和最终结果视频跑批。

直接用户是设计师，当前任务输入是热点视频。未来使用特效时才会出现的人物图或宠物图在 Step 4 中仅定义为 `runtime_inputs`，不是本次必须上传的素材。

## 3. 当前能力清单

| 模块 | 当前状态 | 大白话说明 |
| --- | --- | --- |
| TaskStore | 已实现 | 每个任务有一份可恢复状态，校验后安全保存，支持 Windows/macOS/Linux |
| WorkflowEngine | 已实现 | 按 Step 1–7 推进，能暂停、恢复、阻塞和记录错误 |
| Step 1 | 人工 MVP 已接通 | 一次性抽帧、生成时间线总览，把原视频和帧交给 Codex 理解；恢复时复用已有抽帧 |
| Step 2 | 人工 MVP 已接通 | 把 Step 1 结果和卖点 Prompt 交给 Codex，结果通过 Schema 后进入 Step 3 |
| Step 3 文档 | 已完成初版 | 已分成 3A 跨链路卖点召回和 3B 链路选择，边界清晰 |
| RAG 数据 | 已有正式初版 | 23 条 case：15 条单图、8 条参考视频；有 Schema 和图结构测试 |
| Step 3/RAG 执行 | **已实现初版** | `retrieve-cases.py` 使用本地 Embedding（85%）和标签 Jaccard（15%）召回 Top 6，`--deepseek` 接通 Step 3B |
| Step 4 | 人工 MVP 已接通 | 按 Step 3 结果路由到单图/参考视频设计 Prompt，同时提供模型能力和选中案例 |
| Step 5 | 已实现确定性工具 | 只处理本次固定素材；能复用 Step 1 帧，处理图片/视频的复制、裁切、缩放、补边、转格式、视频截段和定点提帧 |
| Step 5 生图 | 人工暂停模式 | 遇到低频生图会生成请求，等 Codex 放入图片和内容核验凭据后继续 |
| Step 6 | 人工 MVP 已接通 | 基于运行时输入槽位、已就绪固定素材、上游节点输出和案例快照编写节点 Prompt |
| Step 7 | 已实现 | 检查素材文件、节点、Prompt 和案例引用，生成 `production-plan.md` |
| 真实 VLM/LLM API | 未接入 | 当前用 Codex 人工文件交换代替 |
| Keffect/跑批/网站 | 未开始 | 属于链路方案稳定后的后续模块 |

## 4. Step 3/RAG 已经明确的设计

### 4.1 Step 3A：案例召回

- 查询只由 Step 2 的主卖点、次卖点和标签构成。
- 召回前不按 `route_type` 过滤，在 23 条单图和参考视频 case 中执行跨链路 Top 6。
- 相似度只使用卖点文本和标签；链路、节点、模型、素材和 Prompt 不参与主相似度。
- 快照保存 Top 6 的完整 case，供 Step 3B、4、6 共用；不重复召回。

### 4.2 Step 3B：链路选择

- 先基于 Step 1 视频理解和 Step 2 复刻目标分析需要的控制信号。
- 再用“最终视频模型实际媒体入参”校验链路名称。
- `single_image`：最终视频调用一张图、不输入参考视频。
- `reference_video`：最终视频调用实际输入连续参考视频，可同时输入主体图。
- `multi_image`：同一次最终视频调用至少输入两张图，不输入参考视频。当前只识别，不自动执行。
- 选择完成后，才从 Top 6 中精确保留与 `selected_chain` 相同的 case ID，不二次排序、不补位。

## 5. 当前真实运行方式

```text
创建任务
  → Step 1 抽帧并导出 Codex 请求
  → 提交 Step 1 业务 JSON
  → Step 2 导出 Codex 请求
  → 提交 Step 2 业务 JSON
  → Step 3 因未配置执行器而 blocked
```

目前单图和参考视频的全链路测试使用固定 Step 3 fixture 越过该缺口。这证明 Step 4–7 接口能工作，不证明真实召回效果。

调试命令：

```bash
effect-agent task create --task-id task-demo --video-uri <video-path>
effect-agent task run task-demo --manual
effect-agent task pending-request task-demo
effect-agent task submit task-demo --result <current-step-output.json>
```

每个任务的状态和产物在 `outputs/<task-id>/`：

- `task-result.json`：任务状态，只由 TaskStore 写入。
- `video-analysis/`：Step 1 抽帧、时间线总览和元数据。
- `manual/`：当前等待 Codex 处理的请求和响应。
- `case-snapshot.json`：待 Step 3 真实执行器接入后生成。
- `materials/`：Step 5 产物。
- `production-plan.md`：Step 7 交付。
- `evaluations/`：Step 1–2 与人工试跑的离线对比，不影响生产状态。

## 6. 已验证情况

2026-08-24 当前工作区执行全量测试：

```text
Ran 54 tests
OK
```

覆盖内容包括：

- 任务创建、Schema 校验、原子保存、锁竞争、暂停和恢复；
- Step 1 抽帧与复用；
- Codex 人工请求与提交；
- Step 4、6 的单图/参考视频路由；
- Step 5 图片、视频处理和人工生图暂停；
- Step 7 方案交付；
- 23 条 RAG case 的 Schema、节点图、素材和链路分类校验；
- 固定 Step 3 下，单图和参考视频人工闭环均能完成。

测试命令需使用 Python 3.10 或更高版本。

## 7. 还能快速完善哪些内容

以“交接后能尽快开始真实试跑”为标准，优先级如下。

### P0：完成首次真实混合试跑

1. 安装项目 `rag` 可选依赖，下载或指定 `BAAI/bge-small-zh-v1.5`。
2. 通过环境变量配置 DeepSeek Key、API 地址和模型名。
3. 用 `--deepseek` 创建真实任务，人工提交 Step 1 后检查 Step 2–7 是否连续执行。
4. 保留 `case-snapshot.json`、`task-result.json` 和 `production-plan.md` 作为首次基线。

### P1：用两个真实 case 跑通

- 选一个单图 case 和一个参考视频 case，不再使用固定 Step 3 fixture。
- 用 Codex 完成 Step 1，用 DeepSeek 完成 Step 2、3B、4、6，检查真实 `case-snapshot.json`。
- 重点记录 Prompt 理解偏差、Schema 不够用的字段、Step 4 素材要求是否可执行、Step 6 是否正确使用案例。

### P2：收口数据与说明

- 处理 [`rag/PROMPT_GAPS.md`](../rag/PROMPT_GAPS.md) 中两项真实冲突：“时空鹊桥”时长和“吹毫毛”最终模型版本。
- 确认 `birthday_dress_up` 按实际最终入参归为 `reference_video` 的结论，保留来源说明。
- 在真实试跑后更新 Schema 和 Prompt，不在试跑前为了形式完整提前冻结。

### P3：便于日常调试的小补充

- 增加一个“继续处理当前待办请求”的简化脚本或内部调试页，减少手动寻找 JSON 路径。
- 给 Step 3 快照增加 `snapshot_version`、召回方法/模型、案例源指纹和时间，方便复现。
- 在真实试跑中补一个 `needs_input` 固定设计素材的正式提交入口；当前 `source.metadata.materials` 只是设计师额外固定素材的过渡入口，不用于运行时用户图。

## 8. 明确不要误判的事

- 23 条 case 通过 Schema 不等于召回效果已经验证。
- Step 3 文档已写好不等于 Step 3 已接入 WorkflowEngine。
- 固定 Step 3 端到端测试通过不等于真实 RAG 端到端通过。
- `--manual` 是当前调试入口，不是最终部署架构。
- Step 7 交付的是生产方案，不是跑批后的结果视频质量结论。
- `production-plan.md` 应按节点展示并内嵌 Prompt；`task-result.json` 才是完整七步状态与审计记录。
- 当前自动执行 `single_image`、双图有序状态 `multi_image` 和 `reference_video`；仅 `unsupported` 会在 Step 4 前阻塞。
- 人工生图的 `evidence.json` 是可追溯的人工内容核验，不是自动视觉质量评估。

## 9. 接手后建议顺序

1. 阅读本文和 [`DEVELOPMENT_GUIDE.md`](DEVELOPMENT_GUIDE.md)。
2. 检查当前工作区，保留已有未提交修改。
3. 使用 Python 3.10+ 运行全量测试，确认基线。
4. 只优先完成 Step 3 召回、快照和执行器接线。
5. 用真实单图和参考视频案例各跑一次人工闭环。
6. 根据实际失败点调整 Prompt、Schema 和召回，不先扩展多图、Keffect 或网站。

## 10. 重要文件导航

| 内容 | 文件 |
| --- | --- |
| 完整开发基线 | [`docs/DEVELOPMENT_GUIDE.md`](DEVELOPMENT_GUIDE.md) |
| Skill 总流程 | [`skills/effect-generation-workflow/SKILL.md`](../skills/effect-generation-workflow/SKILL.md) |
| Step 3A 召回规则 | [`case-retrieval.md`](../skills/effect-generation-workflow/prompts/case-retrieval.md) |
| Step 3B 链路选择 | [`chain-selection.md`](../skills/effect-generation-workflow/prompts/chain-selection.md) |
| RAG 机器 Schema | [`rag/case.schema.json`](../rag/case.schema.json) |
| 正式案例 | [`rag/data/cases.jsonl`](../rag/data/cases.jsonl) |
| 案例阅读规范 | [`case-schema.md`](../skills/effect-generation-workflow/references/case-schema.md) |
| 待人工确认冲突 | [`rag/PROMPT_GAPS.md`](../rag/PROMPT_GAPS.md) |
| 任务状态 Schema | [`schemas/task-result.schema.json`](../schemas/task-result.schema.json) |
| 运行时编排 | [`workflow.py`](../src/effect_generation_agent/workflow.py) |
| 任务存储 | [`store.py`](../src/effect_generation_agent/store.py) |
| 当前执行器接线 | [`executors.py`](../src/effect_generation_agent/executors.py) |
| Codex 人工交换 | [`model_execution.py`](../src/effect_generation_agent/model_execution.py) |
| Step 5 素材处理 | [`materials.py`](../src/effect_generation_agent/materials.py) |
| Step 7 交付 | [`delivery.py`](../src/effect_generation_agent/delivery.py) |

## 11. 协作提醒

当前仓库存在多进程并行修改且尚未统一提交。接手时不要清理、回退或覆盖不熟悉的已有文件。修改 Step 3 或 Schema 时，同步检查 Prompt、fixture、测试、Step 4/6 案例读取和本交接文档中的状态说明。

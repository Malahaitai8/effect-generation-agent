# 特效生成 Agent

本项目的最终产物是一个公司内部特效生成 Agent。当前直接用户是设计师：设计师提交热点视频，Agent 输出可执行的节点化特效生成链路方案。未来终端用户的人物图、宠物图等只作为运行时输入槽位定义，不是当前设计任务必须上传的文件。

## 特效方案工作台

项目内置了面向运营和设计师的本地工作台，支持批量上传、独立任务进度、结构化审核、修订历史、交付冻结和 XLSX/CSV/ZIP 批量导出。工作台不直接修改 `task-result.json`。

```bash
python3 -m pip install .
effect-workbench --host 127.0.0.1 --port 8765
```

然后访问 `http://127.0.0.1:8765`。工作台中的“模拟运行”用于无模型密钥时验收界面闭环；真实 Agent 执行仍使用下方的 `--manual` 或 `--deepseek` 模式。

`skills/` 只承载流程决策、Prompt 规范和领域知识；Agent 编排、RAG、模型配置、任务状态和产物管理均位于独立模块中。

第一阶段支持：

- 单图驱动
- 参考视频驱动
- 完整串联既定的 Step 1–7
- Step 3 单次 RAG 主召回与任务级案例快照

多图驱动支持案例库覆盖的双图有序状态方案；三张以上、无明确顺序或混合视频调用的需求应输出 `unsupported` 和待人工确认原因，不能强行降级。

宏观架构、实施顺序、状态设计和协作边界见 [`docs/DEVELOPMENT_GUIDE.md`](docs/DEVELOPMENT_GUIDE.md)。
当前阶段性交接、已完成能力和最短后续路径见 [`docs/MT_HANDOFF.md`](docs/MT_HANDOFF.md)。

任务状态的机器约束以 [`schemas/task-result.schema.json`](schemas/task-result.schema.json) 为唯一事实源；跨 Step 的执行约束见 skill 内的 [`task-result-schema.md`](skills/effect-generation-workflow/references/task-result-schema.md)。

## 目录

```text
src/effect_generation_agent/   Agent 运行与编排
skills/                        Skill 与 Prompt/决策规范
rag/                           案例 schema、数据与召回实现
config/                        模型能力和运行配置
tests/                         单元与端到端测试
outputs/                       每次任务的结果、案例快照和素材
docs/                          项目计划与设计记录
```

## 当前可运行能力

当前已实现跨平台文件 TaskStore、七步 WorkflowEngine、模拟执行器，以及不依赖模型 API 的 Codex 人工交换模式。Step 1 会一次性抽帧；Step 4 区分运行时输入、Agent 管理的固定素材和节点输出；Step 5 可复用、提取、加工固定素材，并通过统一接口调用生图能力；Step 7 生成设计师可读主体和独立审计附录。Keffect 和结果视频跑批尚未接入。

`--deepseek` 混合模式已接入：Step 1 使用 Codex 人工多模态交换，Step 2/3B/4/6 真实调用 DeepSeek，Step 3A 使用本地 Embedding 召回。可将 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL` 和 `DEEPSEEK_MODEL` 写入项目根目录的 `.env.local`；CLI 启动时自动读取，系统环境变量优先，配置文件已被 Git 忽略。

使用 Python 3.10 或更高版本安装项目依赖：

```bash
python3 -m pip install .
```

检查项目状态：

```bash
PYTHONPATH=src python3 -m effect_generation_agent status
```

创建并使用模拟执行器跑通一个本地任务：

```bash
PYTHONPATH=src python3 -m effect_generation_agent task create \
  --task-id task-demo-001 \
  --video-uri inputs/example.mp4
PYTHONPATH=src python3 -m effect_generation_agent task run task-demo-001 --mock
PYTHONPATH=src python3 -m effect_generation_agent task show task-demo-001
```

并发创建和运行多个独立任务：

```json
[
  {"task_id": "blind-case-a", "video_uri": "/absolute/path/a.mov"},
  {"task_id": "blind-case-b", "video_uri": "/absolute/path/b.mov"}
]
```

将以上内容保存为 `batch-manifest.json` 后运行：

```bash
effect-agent batch create --batch-id trial-001 --manifest batch-manifest.json
effect-agent batch run trial-001 --deepseek --max-concurrency 2
effect-agent batch show trial-001
effect-agent batch resume trial-001 --deepseek --max-concurrency 2
```

批次状态保存在 `outputs/.batches/<batch-id>/batch-result.json`，每个视频仍拥有独立的 `task-result.json`。Step 1 等待人工多模态结果时，批次会显示 `needs_input`；结果提交后可恢复整个批次。单条任务失败或暂停不会终止其他任务。

使用 Codex 人工处理当前 Prompt：

```bash
PYTHONPATH=src python3 -m effect_generation_agent task run task-demo-001 --manual
PYTHONPATH=src python3 -m effect_generation_agent task pending-request task-demo-001
PYTHONPATH=src python3 -m effect_generation_agent task submit task-demo-001 --result step-output.json
```

`pending-request` 给出当前 Prompt、结构化输入和媒体路径；`submit` 只接受当前 Step 的业务 JSON，校验成功后自动继续到下一个暂停点。

旧版任务必须显式迁移后才能由当前 0.9.0 运行时读取。0.9.0 将外观策略收敛为保留输入、统一重设计、按人物呈现分别重设计三种模式；旧 Prompt 没有通过新的语义复核，迁移后会回到 Step 6 重新生成：

```bash
PYTHONPATH=src python3 -m effect_generation_agent task migrate <task-id>
```

任务因 `needs_input` 或 `blocked` 暂停，并且所需输入或外部条件已经准备好后，可使用：

```bash
PYTHONPATH=src python3 -m effect_generation_agent task resume task-demo-001 --manual
```

# 特效生成 Agent

本项目的最终产物是一个可运行的 Agent。`skills/` 只承载流程决策、Prompt 规范和领域知识；Agent 编排、RAG、模型配置、任务状态和产物管理均位于独立模块中。

第一阶段支持：

- 单图驱动
- 参考视频驱动
- 完整串联既定的 Step 1–7
- Step 3 单次 RAG 主召回与任务级案例快照

多图驱动暂不进入 MVP；当需求明显依赖多个精确视觉状态时，Agent 应输出 `unsupported` 和待人工确认原因，不能强行降级。

实施顺序与验收边界见 [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)。

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

## 当前可运行检查

```bash
PYTHONPATH=src python3 -m effect_generation_agent status
```


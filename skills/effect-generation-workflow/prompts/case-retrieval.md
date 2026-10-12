# Step 3A：案例主召回

## 1. 步骤目标

只使用 Step 2 的主卖点、次卖点及其标签构造查询，面向全部正式历史案例执行一次跨链路主召回，并保存任务级案例快照。

本阶段的目标是找到“卖点相似”的候选案例，不负责判断当前任务最终采用哪种链路。不得在召回前按 `route_type` 过滤，也不得把 Step 1 视频观察、控制要求、模型、素材或链路倾向混入向量查询。

## 2. 执行边界

- 前置：Step 2 完成，正式案例库和 case Schema 可读。
- 只执行跨链路卖点召回和快照保存，不选择链路、设计节点或解释模型能力。
- 一个任务只生成一份主召回快照；有效快照存在时复用。

## 3. 输入契约

- `workflow.step_2.output.primary_selling_point.description`
- `workflow.step_2.output.primary_selling_point.tags`
- `workflow.step_2.output.secondary_selling_points[].description`
- `workflow.step_2.output.secondary_selling_points[].tags`
- 项目根目录 `rag/data/cases.jsonl`

Step 1 仍是随后 Step 3B 选择链路的输入，但不是本次语义召回的查询内容。

## 4. 执行规则

### 查询与匹配范围

查询文本按以下顺序拼接，空的次卖点可以省略：

```text
主卖点描述
主卖点标签
次卖点描述
次卖点标签
```

历史案例只对以下字段形成可检索文本：

- `primary_selling_point.description`
- `primary_selling_point.tags`
- `secondary_selling_points[].description`
- `secondary_selling_points[].tags`

`route_type`、`materials`、`nodes`、`prompts` 和 `source_notes` 不参与主相似度计算。它们随完整 case 进入快照，供 Step 3B、Step 4 和 Step 6 按需读取。

### 召回与快照

1. 读取并校验全部正式 case；无效 case 不得进入候选集。
2. 不按链路预过滤，对所有 `single_image`、`multi_image` 和 `reference_video` case 统一计算卖点语义相似度。
3. 按相似度降序保留 Top 6；分数相同时使用 `case_id` 提供稳定顺序。
4. Top 6 保存完整 case，不裁剪节点或 Prompt。
5. 一次任务只执行一次主召回。Step 3 重试时，如快照已成功落盘则复用，不再次召回。
6. 案例不足 6 条时保存全部有效候选，不用低相关案例或其他链路规则凑数。

## 5. 输出契约

- 查询所使用的主卖点、次卖点、标签和拼接文本；
- 按分数排序的跨链路 Top 6；
- 每个候选的 `case_id`、相似度分数和完整 case；
- 案例源与召回时间等可复核元数据；
- 任务级案例快照路径。

建议的快照最小形态：

```json
{
  "query": {
    "primary_selling_point": {},
    "secondary_selling_points": [],
    "text": "..."
  },
  "retrieval": {
    "top_k": 6,
    "case_source": "rag/data/cases.jsonl"
  },
  "candidates": [
    {
      "case_id": "example_case",
      "score": 0.0,
      "case": {}
    }
  ]
}
```

快照字段可在召回实现时增加版本和 Embedding 元数据，但不得改变以下语义：候选是选链路前的跨链路结果，且包含下游所需的完整 case。

案例字段必须符合 [case-schema.md](../references/case-schema.md)。MVP 只召回正式入库的单图驱动与参考视频驱动案例；不从原文档、链接或媒体附件临时拼接案例。

## 6. 运行状态

- 案例文件、Schema、Embedding 服务或快照写入不可用时，返回可恢复的阻塞，不伪造候选。
- `scripts/retrieve-cases.py` 使用本地 Embedding 和标签分数执行召回；依赖或模型不可用时必须明确阻塞，不得改成人工 Top 6 并声称召回成功。
- 主召回无结果时仍保存可复核的空快照；Step 3B 可以基于当前视频与卖点选择链路，但必须记录案例覆盖不足。

- `completed`：快照成功写入，包含 0–6 个完整候选。
- `blocked`：案例文件、Schema、Embedding 模型或快照写入暂不可用。
- `failed`：不可恢复的案例数据或执行器错误。

## 7. 输出示例

- 标准结果：Top 6 可同时包含 `single_image`、`multi_image` 和 `reference_video`，保留相似度顺序和完整 case。
- 案例少于 6 条：保存全部有效候选，不补低相关案例。
- 空召回：保存 `candidates: []` 和元数据，由 Step 3B 记录覆盖风险。

## 8. 输出前检查

- 查询是否只包含 Step 2 的主次卖点及标签？
- 是否在召回前保持跨链路？
- 候选是否已通过 case Schema，且快照保留完整 case？
- 排序、Top 6、并列稳定性和快照复用是否符合规则？

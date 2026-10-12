# Step 1–2 人工试跑对比评测

在 Step 1 和 Step 2 已经独立完成后，对比当前结构化结果与人工试跑记录。人工记录只能作为评测基线，不能用于反向改写当前任务结果。

分别检查：

1. Step 1 是否覆盖相同的主体、场景、动作顺序、状态变化、镜头和关键帧证据；
2. 当前结果是否出现人工记录没有证据支持的事实；
3. Step 2 的主卖点、次卖点、删除测试和复刻目标是否与人工结论一致；
4. 差异来自合理的新解释、证据缺失，还是 Prompt/字段退化；
5. 只提出评测结论，不修改任务状态。

返回 JSON：

```json
{
  "overall_alignment": "aligned | partially_aligned | misaligned",
  "step_1_matches": [],
  "step_1_differences": [],
  "step_2_matches": [],
  "step_2_differences": [],
  "suspected_regressions": [],
  "notes": []
}
```

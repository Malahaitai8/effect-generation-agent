# V0.9 外观策略与防串案回归记录（2026-08-27）

## 本轮目标

验证外观与人物分支规则是否已经从案例式描述收敛为可泛化协议，并复测此前暴露问题的案例。所有任务均复用历史 Step 1 结果，没有重新抽帧或再次进行视频理解；Step 2–6 由已配置的 DeepSeek 真实执行，Step 5、7 使用确定性执行器。

## 最终规则

Step 4 使用三种外观模式：

- `preserve_input`：保留运行时主体原外观；
- `uniform_redesign`：设计所有允许主体共用的造型，不建立男女分支；
- `presentation_specific_redesign`：成人主题人物造型按 `female/male` 分支。

外观复核不再让模型自由判断最终结论。模型只提取四项事实，运行时按固定公式计算模式；第一次事实提取后冻结，修正后只做确定性验收。Step 6 不得把 Step 2 `adapt` 中的年龄、物种、性别或身体形态固定为源视频属性。

## 最终结果

### 浪漫时刻 — `blind-v09-q`

- 状态：Step 1–7 完成；
- 链路：单图驱动；
- 外观模式：`presentation_specific_redesign`；
- 首帧节点：女性、男性两份完整 Prompt；
- 视频节点：一份中性共用 Prompt；
- Step 6 语义复核：通过；
- 最终方案：[production-plan.md](../outputs/blind-v09-q/production-plan.md)；
- 任务状态：[task-result.json](../outputs/blind-v09-q/task-result.json)。

该结果解决了“首帧主动设计人物造型但没有男女分支”的问题。分支只作用于首帧生图节点，动作和视频 Prompt 没有被机械拆成两份。

### 功夫小猫 — `blind-v09-s`

- 状态：Step 1–7 完成；
- 链路：单图驱动；
- 外观模式：`uniform_redesign`；
- Prompt 分支：无；
- Step 6 语义复核：通过；
- 最终方案：[production-plan.md](../outputs/blind-v09-s/production-plan.md)；
- 任务状态：[task-result.json](../outputs/blind-v09-s/task-result.json)。

武侠造型被视为可共用主题设计，没有因为服装、发型或配饰字样机械建立成人男女分支。

### 泡面奇遇 — `blind-v09-u`

- 状态：Step 1–7 完成；
- 链路：单图驱动；
- 外观模式：`uniform_redesign`；
- Prompt 分支：无；
- 首帧 Prompt：以输入主体为准，不固定成婴儿或特定物种；
- 视频 Prompt：完整保留吸面、表情变化、喷嚏、镜头轻推和鼻孔面条反转；
- 防串案检查：未出现理发师、披风、染发膏、锡纸或吹风机；
- Step 6 语义复核：通过；
- 最终方案：[production-plan.md](../outputs/blind-v09-u/production-plan.md)；
- 任务状态：[task-result.json](../outputs/blind-v09-u/task-result.json)。

该结果同时解决了“源视频是婴儿就强制运行时主体婴儿化”和“复制无关理发案例 Prompt”两个问题。

## 并发与状态行为

本轮使用 Agent 自身的批量调度器并发执行任务。复用 Step 1 后曾发现批量恢复器把“任务正在进行”误认为“当前待开始 Step 需要恢复”，现已改为读取当前 Step 自身状态决定 `run` 或 `resume`，并增加回归测试。

错误方案不会进入最终交付：外观语义不一致时停在 Step 4；分支来源无法解析时停在 Step 7；结构非法时旧状态不被覆盖。

## 耗时

耗时受 DeepSeek API 响应、Embedding 模型加载和本轮调试重试影响：

- 浪漫时刻最终成功任务 `blind-v09-q`：约 2 分 47 秒（Step 2–7，复用 Step 1）；
- 泡面奇遇最终成功任务 `blind-v09-u`：约 6 分 41 秒（Step 2–7，复用 Step 1）；
- 功夫小猫在同一任务内经历两次可恢复的 Step 4 修正后完成，不能作为正常单次耗时基线；
- 两任务原生并发批次 `v09-final-two-regression-20260827` 的首轮墙钟时间约 10 分 22 秒，其中一条因外观复核规则问题暂停。

当前更适合记录每个 Step 的模型调用耗时后再建立稳定性能基线；本轮耗时主要用于确认流程可运行，不代表最终服务性能。

## 仍需观察

- Step 4 事实仍由文本模型提取，虽然结论已由代码计算，事实提取本身仍需更多样本验证；
- `uniform_redesign` 的具体共享造型质量需通过真实图片/视频生成验证；
- 当前三个回归样本只能验证已知边界，下一轮应加入未参与规则讨论的新案例做盲测，避免再次围绕旧案例调优。

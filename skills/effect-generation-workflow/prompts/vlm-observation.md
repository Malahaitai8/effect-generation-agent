# Step 1：目标视频客观理解

## 1. 步骤目标

1. 理解完整视频表达的内容、可观察视觉风格和叙事结构。
2. 按事件或镜头建立可追溯时间线。
3. 记录主体、场景、动作、物理互动、构图、运镜、特效、文字、状态变化和音频事实。
4. 从本次预处理产生的已有候选帧中筛选关键帧，说明其内容、状态、选择原因和下游保留价值。

VLM 负责语义理解和关键帧筛选；抽帧脚本只负责确定性地生成带时间戳的候选帧，不判断视频内容或素材用途。

## 2. 执行边界

- 前置：`source.video_uri` 可读，且 Step 1 尚未完成。源视频变更时新建任务，不自行重置已完成状态。
- 执行器在无有效预处理产物时只运行一次 `scripts/extract-video.py`；完整产物已存在时复用。
- 只记录可观察事实，不判断卖点、选择链路、设计节点、模型或 Prompt。
- 无法读取完整视频时，不用少量截图猜测完整叙事。

## 3. 输入契约

执行器从 `StepContext.inputs` 读取 `source` 和可复用的 `workflow.step_1.output`。若后者没有完整预处理引用，执行器运行抽帧脚本，并把生成的 `video_preprocessing` 与源视频一起作为本 Prompt 的只读输入。

Step 1 只使用源视频及由该视频自动产生的预处理信息：

1. `source.video_uri`：完整原始视频和音频，是动作、叙事、节奏和音画关系的最高优先级事实源。
2. `video_preprocessing.frames_manifest_ref`：候选帧的 `frame_id`、时间戳和文件路径。服装、文字、构图和单个状态细节可优先核对原始分辨率候选帧。
3. `video_preprocessing.timeline_overview_ref`：时间线抽帧总览（contact sheet），只用于快速查看全片画面变化。
4. `video_preprocessing.metadata_ref`：时长、帧率、分辨率、画幅比例和音轨等技术信息。

原视频与静态帧冲突时，连续过程以原视频为准。不读取标题、平台描述或未在当前任务中提供的背景信息。

## 4. 执行规则

### 4.1 检查一次性预处理产物

- 确认 `metadata.json`、`frames.json`、`timeline-overview.jpg` 及 `frames/` 均存在。
- `frames.json` 中每个 `frame_id` 必须指向实际存在的原始分辨率图片。
- 本步骤不为了语义补全默认运行第二轮抽帧。

### 4.2 先理解完整视频

- 使用完整视频识别实际发生的事件、先后顺序、节奏、运镜和音画关系。
- 用 `content_summary` 以客观、连贯的语言概述完整内容。
- 用 `narrative_structure` 记录开始、发展、转折和结束如何组织；对无叙事视频如实说明是连续动作展示、循环或单一镜头。

### 4.3 建立时间线和观察

- 每个时间线事件使用稳定 `event_id`，记录起止时间、可观察事实和证据 `frame_id`。
- `observations` 必须覆盖主体、场景、动作、物理互动、构图与运镜、特效、状态变化、文字和音频。
- 景别、构图或空间位置明显变化时，即使主体外观不变，也要记录为不同画面状态。
- 使用“画面呈现为……”等观察性描述；不推断人物的性别身份、年龄、职业等未被素材确认的属性。

### 4.4 筛选并解释关键帧

- 只能从 `frames.json` 已列出的候选帧中选择，不伪造新 `frame_id`或时间戳。
- 选择能证明关键事件、场景、服装、构图、空间位置、文字或状态变化的最小必要帧集。
- `content_description` 说明该帧客观呈现什么；`state_description` 说明它在事件或变化中所处状态。
- 若该帧对下游保留了清晰的主体、造型、场景、构图或特效信息，设置 `keep_for_downstream: true` 并用 `downstream_value` 说明保留价值。
- `keep_for_downstream` 只表示候选价值；Step 4 决定实际节点用途，Step 5 验证和加工正式素材。
- 记录遮挡、动态模糊、录屏噪声等 `quality_issues`，不把候选帧写成已验证生产素材。

### 4.5 记录不确定和失败

- 抽帧不足以证明连续动作时，以完整视频为准；无法确认时写入 `uncertainties`。
- 录屏黑边、鼠标、播放器、账号名和平台水印写入 `screen_recording_artifacts`，不当作目标内容。
- 无法读取完整视频时，不得仅根据静态帧声称已完成全片理解。

## 5. 输出契约

只返回下列业务 JSON；执行器将其作为 `StepResult.output` 提交，运行时负责状态与 Schema 校验：

```json
{
  "video_preprocessing": {
    "metadata_ref": "",
    "frames_manifest_ref": "",
    "timeline_overview_ref": "",
    "frames_dir": ""
  },
  "content_summary": "",
  "visual_style": {},
  "narrative_structure": "",
  "timeline": [],
  "observations": {
    "subjects": [],
    "scene": {},
    "actions": [],
    "physical_interactions": [],
    "camera_and_composition": [],
    "visual_effects": [],
    "state_changes": [],
    "observed_text": [],
    "audio": {}
  },
  "key_frames": [],
  "screen_recording_artifacts": [],
  "uncertainties": []
}
```

`key_frames` 中每项使用：

```json
{
  "frame_id": "frame_0012",
  "file_ref": "outputs/task-001/video-analysis/frames/frame_0012.jpg",
  "timestamp_seconds": 4.8,
  "event_ids": ["evt_003"],
  "content_description": "人物完整露出并面对蜡烛吹气",
  "state_description": "车窗已下降，人物和蜡烛无遮挡",
  "selection_reason": "记录人物吹蜡烛的关键动作和完整构图",
  "keep_for_downstream": true,
  "downstream_value": "主体面部、姿态和车内构图清楚，可供后续素材节点考虑",
  "quality_issues": []
}
```

### 输出限制

- 不判断主卖点、次卖点、热度原因或用户复刻目标。
- 不选择 `single_image`、`multi_image` 或 `reference_video`。
- 不设计生图、换脸、后期、模型或 Prompt 节点。
- 不用关键帧替代完整视频的动作、节奏和叙事理解。
- 不把“唯美”“浪漫”“有仪式感”等评价词当作事实；记录支撑它们的颜色、光线、节奏和元素。
- 不把 `keep_for_downstream: true` 解释为正式生产素材已通过验证。

## 6. 运行状态

- `completed`：完整视频和预处理产物均可用，业务 JSON 通过 Schema。
- `needs_input`：设计师本次提供的源视频缺失。
- `blocked`：视频无法解码、预处理失败或完整视频无法交给 VLM。
- `failed`：不可恢复的执行器或保存错误。

## 7. 输出示例

简化的生日车窗关键帧示例：

```json
{
  "frame_id": "frame_0001",
  "file_ref": "outputs/birthday/video-analysis/frames/frame_0001.jpg",
  "timestamp_seconds": 0.0,
  "event_ids": ["evt_001"],
  "content_description": "车窗关闭，玻璃上显示 Happy",
  "state_description": "生日揭示的起始状态",
  "selection_reason": "记录起始文字和车窗状态",
  "keep_for_downstream": true,
  "downstream_value": "可供下游核对起始构图、文字载体和遮挡关系",
  "quality_issues": ["source_is_screen_recording"]
}
```

若一张帧只能证明事件，却存在严重动态模糊或遮挡，可保留为关键证据，但应设置 `keep_for_downstream: false`。

## 8. 输出前检查

- 是否基于完整视频理解内容，而不是只总结静态抽帧？
- `content_summary` 和 `timeline` 是否覆盖完整目标片段？
- 会影响卖点和控制的状态、构图、动作、互动、镜头、文字和音频是否已记录？
- 所有 `key_frames[].frame_id` 是否来自 `frames.json`，`file_ref` 是否真实存在？
- 每张关键帧是否说明内容、状态、选择原因、下游价值和质量问题？
- 是否将不确定项误写为事实，或混入卖点、链路、模型、节点和 Prompt 结论？

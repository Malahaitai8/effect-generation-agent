# Step 5：固定素材准备与验证

## 1. 步骤目标

只处理 Step 4 `base_materials`：由 Agent 从热点视频复用、提取、加工或自动生成下游节点需要的固定素材。不重新分析卖点、选链路、设计节点或写 Prompt。

Step 4 `runtime_inputs` 是未来使用特效时才由终端用户提供的槽位。Step 5 不处理它们、不寻找文件、不记入 `materials`，也不因它们没有当前路径而暂停。

## 2. 执行边界

- 前置：Step 4 完成，且三类 ID 不冲突。
- 执行确定性复制/提取/裁切/转换/验证，以及不依赖运行时输入的自动固定素材生成。
- 不执行依赖 `runtime_inputs` 的生图/生视频节点，不重新分析卖点、链路或 Prompt。

## 3. 输入契约

- `workflow.step_4.output.base_materials`：本步骤唯一处理的素材列表；
- `workflow.step_4.output.runtime_inputs`：只用于确认它们不应进入当前素材处理；
- `source`：设计师提供的热点源视频；
- `workflow.step_1.output`：一次性抽帧产物和关键帧；
- `artifacts.materials_dir`：固定素材产物目录。

## 4. 执行规则

1. 逐项处理 `base_materials`，验证 ID、来源、操作和目标规格。
2. 默认复用 Step 1 原始分辨率帧，不重新运行全局抽帧。
   - 当素材 `source.kind == "step1_frame"` 时，按 `frame_id` 从 Step 1 关键帧或抽帧清单定位原图，复制到任务 `materials/`；不得使用时间线总览缩略图替代。
   - 保留 `reference_role` 作为下游 Prompt 理解该图片用途的证据；Step 5 不把参考图加工成已替换主体的首帧。
3. 允许 `direct`、`crop`、`transform`、`generate` 和固定素材的 `image_to_image`。`generate`/`image_to_image` 必须调用自动素材生成接口。
4. 依赖未来 `runtime_inputs` 的生图/生视频是链路节点，不得在 Step 5 执行。
5. 合格固定素材标记 `ready`；素材源、生图或处理能力不可用统一返回 `blocked`，不向设计师索要普通参考素材。
6. 所有必需固定素材已就绪，且 `runtime_inputs` 定义完整时，`ready_for_prompting` 为 `true`。没有固定素材也可为 `true`。

`image_to_image` 只可用于不依赖未来用户输入的固定素材；必须通过自动素材生成接口完成。

### 素材操作结构

```json
{
  "source": {"kind": "source_video"},
  "operation": "transform",
  "clip": {"start_seconds": 0, "duration_seconds": 5},
  "target": {"media_type": "video", "format": "mp4", "width": 720, "height": 1280}
}
```

`source.kind` 可为 `source_video`、`step1_frame`、`generated` 或 `business_asset`。`business_asset` 只用于无法从热点视频推导的 Logo、商品图或 IP 官方素材，当前无资产接入能力时返回 `blocked`。

## 5. 输出契约

```json
{
  "materials": [
    {
      "id": "reference_video",
      "source": "hotspot.mov",
      "operation": "direct",
      "purpose": "提供参考动作和时序",
      "path": "outputs/task-id/materials/reference_video.mov",
      "status": "ready",
      "evidence": ["文件与规格已验证"]
    }
  ],
  "unresolved_materials": [],
  "ready_for_prompting": true
}
```

`materials` 只能包含 Step 4 `base_materials` 中的 ID，不得包含 `runtime_inputs` 或节点输出。

## 6. 运行状态

- `completed`：所有必需固定素材就绪，`ready_for_prompting: true`。无固定素材也可完成。
- `blocked`：素材源、自动生图、FFmpeg/外部处理能力暂不可用，或素材事实与 Step 4 设计冲突。
- `failed`：不可恢复的处理或安全保存错误。

## 7. 输出示例

- 无固定素材：`materials: []`、`unresolved_materials: []`、`ready_for_prompting: true`。
- 直接复用热点视频：`reference_video` 验证后为 `ready`。
- 复用热点关键帧：`hotspot_visual_reference` 按 Step 1 `frame_id` 复制并验证为 `ready`，供前置生图节点与运行时用户图共同输入。
- 自动生图能力不可用：列入 `unresolved_materials`，返回 `blocked`；不将未来用户图列入其中。

## 8. 输出前检查

- `materials[].id` 是否全部来自 Step 4 `base_materials`？
- 是否复用 Step 1 原始分辨率帧，没有重跑全局抽帧？
- `ready` 文件是否真实存在并符合目标规格？
- 是否没有因 `runtime_inputs` 没有文件而暂停？

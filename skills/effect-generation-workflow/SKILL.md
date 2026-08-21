---
name: effect-generation-workflow
description: Plan an executable effect-generation workflow from a target video, choosing single-image or reference-video generation and producing materials, model nodes, prompts, risks, and delivery artifacts. Use for effect-production planning or execution; do not force unsupported multi-image requirements into a supported chain.
---

# Effect Generation Workflow

Use this skill as the domain workflow layer of the effect-generation Agent. The Agent runtime, RAG implementation, task state, model configuration, and output persistence live outside this skill.

## Supported MVP chains

- `single_image`: the final video model receives one image.
- `reference_video`: the final video model receives a reference video, usually with a subject image.
- Return `unsupported` when precise multi-image state control is required. Do not silently downgrade it to `single_image`.

## Invariants

Run the established seven-stage workflow:

1. Observe the target video objectively.
2. Identify primary and secondary selling points.
3. Perform one main case retrieval, save the task-level snapshot, and select only the chain type.
4. Design nodes, models, dependencies, and base materials.
5. Obtain or standardize the actual materials.
6. Write node prompts from the actual materials and saved case snapshot.
7. Validate and deliver the production plan and artifacts.

Keep selling points separate from execution-chain choice. Step 3 must not design nodes, choose final model parameters, or write final prompts. Step 4 must not write final prompts. Step 6 must not repeat the main retrieval unless the snapshot has an explicit coverage gap requiring supplemental retrieval.

## Step routing

Read only the prompt specification required for the current step:

1. [Video observation](prompts/vlm-observation.md)
2. [Selling-point analysis](prompts/selling-point.md)
3. [Case retrieval](prompts/case-retrieval.md), then [chain selection](prompts/chain-selection.md)
4. [Chain design](prompts/chain-design.md) and [model capabilities](references/model-capabilities.json)
5. [Material extraction](prompts/material-extraction.md)
6. Read the selected chain template: [single image](prompts/chain-single-image.md), [multi image](prompts/chain-multi-image.md), or [reference video](prompts/chain-reference-video.md)
7. Validate all required inputs, prompts, risks, and deliverables before returning the production plan.

Use [case-schema.md](references/case-schema.md) when reading, writing, or validating RAG cases. Use `scripts/retrieve-cases.py` for the Step 3 main retrieval and `scripts/gen-image.py` only when Step 5 requires deterministic image generation or standardization.

The implementation sequence and MVP acceptance criteria are maintained in [`../../docs/IMPLEMENTATION_PLAN.md`](../../docs/IMPLEMENTATION_PLAN.md).


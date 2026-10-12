"""Stable machine identifiers and designer-facing Chinese labels."""

from __future__ import annotations

from collections.abc import Iterable


SELLING_POINT_TAG_LABELS_ZH: dict[str, str] = {
    "identity_or_character_transformation": "身份或角色转换",
    "pet_anthropomorphism": "宠物拟人化",
    "style_transformation": "风格转换",
    "scene_spectacle": "场景奇观",
    "effect_spectacle": "特效奇观",
    "state_transformation": "状态变化",
    "prop_or_superpower": "道具或超能力",
    "action_performance": "动作表演",
    "physical_interaction": "物理互动",
    "reveal_or_micro_narrative": "揭示或微叙事",
    "text_or_symbol_reveal": "文字或符号揭示",
    "festival_or_ritual": "节日或仪式",
    "camera_or_composition": "镜头或构图",
    "audio_visual_sync": "音画同步",
}


def selling_point_tag_labels_zh(tags: Iterable[str]) -> list[str]:
    """Translate known machine tags while preserving unknown extensions."""

    return [SELLING_POINT_TAG_LABELS_ZH.get(tag, tag) for tag in tags]

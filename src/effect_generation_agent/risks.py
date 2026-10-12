"""Canonical workflow risk ownership and merging."""

from __future__ import annotations

import re
from collections.abc import Iterable


_CHAIN_CHANGE_RE = re.compile(
    r"(?:升级|降级|改用|切换|调整为|转为).*(?:single_image|reference_video|multi_image|单图驱动|参考视频驱动|多图驱动)",
    re.IGNORECASE,
)


def merge_workflow_risks(
    step_3_risks: Iterable[str] | None,
    step_4_risks: Iterable[str] | None,
    coverage_gaps: Iterable[str] | None,
) -> list[str]:
    """Merge risks according to ownership across workflow steps."""

    selected: list[str] = []
    seen: set[str] = set()

    def append_unique(values: Iterable[str] | None) -> None:
        for value in values or []:
            if not isinstance(value, str) or not value.strip():
                continue
            text = value.strip()
            normalized = re.sub(r"[\s，。；、,.!?！？]", "", text).lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            selected.append(text)

    step_3 = [risk for risk in (step_3_risks or []) if isinstance(risk, str)]
    append_unique(step_3)
    step_3_has_chain_change = any(_CHAIN_CHANGE_RE.search(risk) for risk in step_3)
    append_unique(
        risk
        for risk in (step_4_risks or [])
        if isinstance(risk, str)
        and not (step_3_has_chain_change and _CHAIN_CHANGE_RE.search(risk))
    )
    append_unique(coverage_gaps)
    return selected


def canonicalize_risks(risks: Iterable[str] | None) -> list[str]:
    """Normalize a flattened risk list, including historical revisions."""

    selected: list[str] = []
    seen: set[str] = set()
    has_chain_change = False
    for value in risks or []:
        if not isinstance(value, str) or not value.strip():
            continue
        text = value.strip()
        normalized = re.sub(r"[\s，。；、,.!?！？]", "", text).lower()
        if normalized in seen:
            continue
        is_chain_change = bool(_CHAIN_CHANGE_RE.search(text))
        if is_chain_change and has_chain_change:
            continue
        seen.add(normalized)
        has_chain_change = has_chain_change or is_chain_change
        selected.append(text)
    return selected

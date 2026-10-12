from __future__ import annotations

import unittest

from effect_generation_agent.labels import selling_point_tag_labels_zh


class SellingPointLabelTests(unittest.TestCase):
    def test_known_tags_are_translated_for_delivery(self) -> None:
        self.assertEqual(
            selling_point_tag_labels_zh(
                ["physical_interaction", "state_transformation"]
            ),
            ["物理互动", "状态变化"],
        )

    def test_unknown_extension_is_preserved(self) -> None:
        self.assertEqual(selling_point_tag_labels_zh(["future_tag"]), ["future_tag"])

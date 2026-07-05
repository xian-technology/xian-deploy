from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class ThirdPartyImagePinningTest(unittest.TestCase):
    def test_digest_pinning_defaults_are_local_friendly(self) -> None:
        defaults = REPO_ROOT / "roles" / "xian_profile" / "defaults" / "main.yml"
        example = REPO_ROOT / "inventories" / "example" / "group_vars" / "all" / "main.yml"

        for path in (defaults, example):
            source = path.read_text(encoding="utf-8")
            self.assertIn("xian_require_digest_pinned_third_party_images: false", source)

    def test_shared_network_and_strict_mode_require_digest_pinned_images(self) -> None:
        profile_tasks = REPO_ROOT / "roles" / "xian_profile" / "tasks" / "main.yml"
        source = profile_tasks.read_text(encoding="utf-8")

        self.assertIn("xian_operator_profile == 'shared_network'", source)
        self.assertIn("xian_require_digest_pinned_third_party_images | bool", source)
        self.assertIn("xian_digest_pinned_image_ref_pattern", source)

    def test_only_enabled_third_party_services_are_required(self) -> None:
        profile_tasks = REPO_ROOT / "roles" / "xian_profile" / "tasks" / "main.yml"
        source = profile_tasks.read_text(encoding="utf-8")

        self.assertIn("or not (xian_bds_enabled | bool)", source)
        self.assertIn("or not (xian_monitoring_enabled | bool)", source)
        self.assertIn("xian_postgres_image is match", source)
        self.assertIn("xian_prometheus_image is match", source)
        self.assertIn("xian_grafana_image is match", source)


if __name__ == "__main__":
    unittest.main()

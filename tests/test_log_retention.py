import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LogRetentionTest(unittest.TestCase):
    def test_every_rendered_service_selects_bounded_local_logging(self):
        for name in ("docker-compose.yml.j2", "docker-compose.monitoring.yml.j2"):
            source = (ROOT / "roles/xian_runtime/templates" / name).read_text()
            services = source.split("services:\n", 1)[1]
            names = re.findall(r"^  ([a-zA-Z0-9_-]+):$", services, re.M)
            self.assertTrue(names)
            for service in names:
                self.assertIn(f"  {service}:\n    logging: *x-logging", services)
            self.assertIn("driver: local", source)
            self.assertIn("mode: blocking", source)
            self.assertIn('max-size: "{{ xian_docker_log_max_file_mb | int }}m"', source)
            self.assertIn('max-file: "{{ xian_docker_log_max_files | int }}"', source)

    def test_app_file_limits_are_forwarded_from_profile_to_configure(self):
        profile = (ROOT / "roles/xian_profile/tasks/main.yml").read_text()
        wrapper = (ROOT / "roles/xian_runtime/templates/configure-node-wrapper.py.j2").read_text()
        for suffix, default in (("max_file_mb", 50), ("max_total_mb", 250)):
            self.assertIn(f"xian_profile.get('app_log_{suffix}', {default})", profile)
            self.assertIn(f'--app-log-{suffix.replace("_", "-")}', wrapper)

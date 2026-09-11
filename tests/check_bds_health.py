"""Exercise the production health expressions with Ansible's own templater."""

import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


root = Path(__file__).resolve().parents[1]
health = yaml.safe_load((root / "playbooks/health.yml").read_text())[0]
task = next(task for task in health["tasks"] if task["name"] == "Build deployment health report")
report = task["ansible.builtin.set_fact"]["xian_health_report"]
checks = yaml.safe_load((root / "tests/bds-health.yml").read_text())
checks[0]["vars"].update(
    rendered_state=report["state"],
    rendered_bds_ok=report["checks"]["bds"]["ok"],
)
with tempfile.TemporaryDirectory(prefix="xian-health-test-") as directory:
    playbook = Path(directory) / "health-checks.yml"
    playbook.write_text(yaml.safe_dump(checks))
    subprocess.run(
        [sys.executable, "-m", "ansible.cli.playbook", "-i", "localhost,", str(playbook)],
        check=True,
    )

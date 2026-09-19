"""Opt-in, synthetic filesystem probe; never invokes a reviewer or a model.

Run ``python -m tests.reviewer_isolation_probe`` outside the unit-test suite.
An OS probe pass is not proof of instruction loading or production isolation.
Permission profiles: https://developers.openai.com/es-419/docs/permissions
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

PROFILE = "sd-review-synthetic-probe"
READ_EXPECTATIONS = {
    "allowed_payload": "read",
    "allowed_instruction": "read",
    "allowed_skill": "read",
    "forbidden_sibling": "denied",
    "fake_home_auth": "denied",
    "fake_home_config": "denied",
    "symlink_escape": "denied",
}
WRITE_EXPECTATIONS = {
    "write_allowed_payload": "denied",
    "write_forbidden_sibling": "denied",
    "write_fake_home": "denied",
}
Runner = Callable[..., subprocess.CompletedProcess[str]]


def fixtures(root: Path) -> dict[str, Path]:
    """Build only synthetic data below a caller-owned temporary directory."""
    allowed = root / "allowed"
    fake_home = root / "fake-home"
    paths = {
        "allowed_payload": allowed / "review-subject.md",
        "allowed_instruction": allowed / "AGENTS.md",
        "allowed_skill": allowed / ".codex/skills/synthetic/SKILL.md",
        "forbidden_sibling": root / "sibling/canary.txt",
        "fake_home_auth": fake_home / ".codex/auth.json",
        "fake_home_config": fake_home / ".codex/config.toml",
        "symlink_escape": allowed / "escape",
    }
    contents = {
        "allowed_payload": "SYNTHETIC_REVIEW_PAYLOAD\n",
        "allowed_instruction": "SYNTHETIC_INSTRUCTION_CANARY\n",
        "allowed_skill": "SYNTHETIC_SKILL_CANARY\n",
        "forbidden_sibling": "SYNTHETIC_SIBLING_CANARY\n",
        "fake_home_auth": '{"synthetic_credential": "NOT_A_REAL_TOKEN"}\n',
        "fake_home_config": "# SYNTHETIC_CONFIG_CANARY\n",
    }
    for name, content in contents.items():
        paths[name].parent.mkdir(parents=True, exist_ok=True)
        paths[name].write_text(content, encoding="utf-8")
    paths["symlink_escape"].symlink_to(paths["forbidden_sibling"])
    paths.update({
        "write_allowed_payload": paths["allowed_payload"],
        "write_forbidden_sibling": root / "sibling/new.txt",
        "write_fake_home": paths["fake_home_auth"],
    })
    return paths


def sandbox_command(codex: str, root: Path, paths: dict[str, Path]) -> list[str]:
    """Select an explicit read-restricted profile without inherited policy."""
    entries = {":root": "deny", ":minimal": "read", ":tmpdir": "deny",
               ":slash_tmp": "deny", str(root): "deny", str(root / "allowed"): "read"}
    filesystem = "{" + ",".join(f"{json.dumps(k)}={json.dumps(v)}" for k, v in entries.items()) + "}"
    script = []
    for name in READ_EXPECTATIONS:
        script.append(
            f"if /bin/cat {shlex.quote(str(paths[name]))} >/dev/null 2>&1; "
            f"then printf '{name}=read\\n'; else printf '{name}=denied\\n'; fi"
        )
    for name in WRITE_EXPECTATIONS:
        script.append(
            f"if (printf 'SYNTHETIC_WRITE\\n' >{shlex.quote(str(paths[name]))}) 2>/dev/null; "
            f"then printf '{name}=written\\n'; else printf '{name}=denied\\n'; fi"
        )
    return [codex, "sandbox", "-P", PROFILE, "-C", str(root / "allowed"),
            "-c", f"permissions.{PROFILE}.filesystem={filesystem}",
            "-c", f"permissions.{PROFILE}.network.enabled=false", "--", "/bin/sh", "-c", "\n".join(script)]


def baseline_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "blocked",
        "scope": "synthetic_codex_sandbox_only",
        "production_review_isolation": "not_established",
        "os_confinement": {"status": "not_measured", "writes": {}},
        "file_read_access": {"status": "not_measured", "reads": {}},
        "instruction_sources": {
            "status": "not_measured",
            "reason": "No model or instruction loader ran. Argument fixtures prove requested controls only.",
        },
        "blockers": [],
    }


def blocked(report: dict[str, Any], code: str, detail: str) -> dict[str, Any]:
    report["blockers"].append({"code": code, "detail": detail[:2000]})
    report["status"] = "blocked"
    return report


def assess(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    """Require complete positive and negative controls; missing output fails closed."""
    report = baseline_report()
    report["process"] = {"exit_code": result.returncode, "stderr": result.stderr[-2000:]}
    if result.returncode:
        return blocked(report, "sandbox_start_or_execution_failed", result.stderr or "Nonzero sandbox exit")
    lines = result.stdout.splitlines()
    try:
        observations = dict(line.split("=", 1) for line in lines)
    except ValueError:
        return blocked(report, "invalid_probe_output", "Malformed probe output")
    expected = {**READ_EXPECTATIONS, **WRITE_EXPECTATIONS}
    if set(observations) != set(expected) or len(lines) != len(expected):
        return blocked(report, "incomplete_probe_output", "Missing, duplicate, or unknown canary observations")
    reads = {name: observations[name] for name in READ_EXPECTATIONS}
    writes = {name: observations[name] for name in WRITE_EXPECTATIONS}
    read_ok = reads == READ_EXPECTATIONS
    write_ok = writes == WRITE_EXPECTATIONS
    report["file_read_access"] = {"status": "passed" if read_ok else "failed", "reads": reads}
    report["os_confinement"] = {"status": "passed" if read_ok and write_ok else "failed", "writes": writes}
    if not read_ok:
        blocked(report, "read_confinement_failed", "Allowed reads failed or forbidden reads succeeded")
    if not write_ok:
        blocked(report, "write_confinement_failed", "A forbidden write succeeded")
    if read_ok and write_ok:
        report["status"] = "os_probe_passed"
    return report


def run_probe(codex: str | None = None, runner: Runner = subprocess.run) -> dict[str, Any]:
    """Never inherit credentials, user configuration, or a production checkout."""
    executable = codex or shutil.which("codex")
    if not executable:
        return blocked(baseline_report(), "sandbox_runner_missing", "Install Codex before running this opt-in probe")
    with tempfile.TemporaryDirectory(prefix="sd-review-isolation-") as raw:
        root = Path(raw).resolve()
        paths = fixtures(root)
        fake_home = root / "fake-home"
        env = {"PATH": os.defpath, "HOME": str(fake_home), "CODEX_HOME": str(fake_home / ".codex")}
        try:
            result = runner(sandbox_command(executable, root, paths), cwd=root / "allowed",
                            env=env, text=True, capture_output=True, timeout=20, check=False)
        except subprocess.TimeoutExpired:
            return blocked(baseline_report(), "sandbox_probe_timeout", "Sandbox exceeded the 20-second probe limit")
        except OSError as error:
            return blocked(baseline_report(), "sandbox_runner_unavailable", str(error))
        return assess(result)


def main() -> int:
    report = run_probe()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "os_probe_passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())

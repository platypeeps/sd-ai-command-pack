"""What `check-helper-resolution.py` inspects, and what it lets through.

The gate's own run over the authored trees proves today's files are clean; it
cannot prove the gate would notice tomorrow's mistake. These cases are written
against `check_file` directly so a block shape that no authored file currently
has is still covered.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PACK_ROOT / ".github/scripts/check-helper-resolution.py"


def load_gate():
    spec = importlib.util.spec_from_file_location("helper_resolution_gate", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class HelperResolutionGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gate = load_gate()
        cls.bootstrap = cls.gate.read_canonical_bootstrap()

    def findings(self, markdown: str) -> list:
        with tempfile.TemporaryDirectory(dir=PACK_ROOT) as directory:
            path = Path(directory) / "SKILL.md"
            path.write_text(markdown, encoding="utf-8")
            return self.gate.check_file(path, self.bootstrap)

    def block(self, body: str) -> str:
        return f"# skill\n\n```bash\n{body}\n```\n"

    def bootstrapped(self, body: str) -> str:
        return self.block("\n".join(self.bootstrap + [body]))

    def test_a_resolved_invocation_passes(self) -> None:
        self.assertEqual(
            self.findings(
                self.bootstrapped(
                    'bash "$SD_PACK_TOOLCHAIN" run-python -- '
                    "sd-ai-command-pack-status.py --json"
                )
            ),
            [],
        )

    def test_a_use_above_the_bootstrap_is_reported(self) -> None:
        """Present is not reached: the earlier use runs with an empty value."""

        body = "\n".join(['bash "$SD_PACK_TOOLCHAIN" doctor'] + self.bootstrap)
        found = self.findings(self.block(body))

        self.assertEqual([finding.rule for finding in found], ["bootstrap-after-use"])

    def test_a_helper_block_without_the_bootstrap_is_reported(self) -> None:
        found = self.findings(
            self.block(
                'bash "$SD_PACK_TOOLCHAIN" run-python -- '
                "sd-ai-command-pack-status.py --json"
            )
        )

        self.assertEqual([finding.rule for finding in found], ["missing-bootstrap"])

    def test_a_toolchain_subcommand_block_without_the_bootstrap_is_reported(
        self,
    ) -> None:
        """The variable is the trigger; a block need not name a helper at all.

        `run -- gh ...` and `doctor` carry no `sd-ai-command-pack-*` filename,
        so a gate keyed on the helper name alone would skip the block whose
        `$SD_PACK_TOOLCHAIN` nothing defines -- the exact failure the bootstrap
        exists to prevent, in the exact block that would hit it.
        """

        for body in (
            'bash "$SD_PACK_TOOLCHAIN" doctor',
            'bash "$SD_PACK_TOOLCHAIN" run -- gh pr view',
        ):
            with self.subTest(body=body):
                found = self.findings(self.block(body))

                self.assertEqual(
                    [finding.rule for finding in found], ["missing-bootstrap"]
                )

    def test_a_toolchain_subcommand_block_with_the_bootstrap_passes(self) -> None:
        self.assertEqual(
            self.findings(self.bootstrapped('bash "$SD_PACK_TOOLCHAIN" doctor')), []
        )

    def test_a_scripts_prefixed_helper_is_reported(self) -> None:
        found = self.findings(
            self.block("bash scripts/sd-ai-command-pack-toolchain.sh doctor")
        )

        self.assertIn("scripts-prefix", [finding.rule for finding in found])

    def test_a_direct_interpreter_invocation_is_reported(self) -> None:
        found = self.findings(
            self.bootstrapped(
                "node sd-ai-command-pack-review-preflight.mjs pre-archive"
            )
        )

        self.assertIn("direct-invocation", [finding.rule for finding in found])

    def test_run_resolves_only_its_first_operand(self) -> None:
        found = self.findings(
            self.bootstrapped(
                'bash "$SD_PACK_TOOLCHAIN" run -- node '
                "sd-ai-command-pack-review-preflight.mjs"
            )
        )

        self.assertIn("run-interpreter", [finding.rule for finding in found])

    def test_an_exempt_block_is_left_alone(self) -> None:
        markdown = (
            "# skill\n\n<!-- pack-helper-resolution: exempt -- documenting the "
            "old form -->\n```bash\nbash scripts/sd-ai-command-pack-toolchain.sh doctor\n```\n"
        )

        self.assertEqual(self.findings(markdown), [])

    def test_a_text_block_is_not_executable(self) -> None:
        markdown = "# skill\n\n```text\nbash scripts/sd-ai-command-pack-toolchain.sh doctor\n```\n"

        self.assertEqual(self.findings(markdown), [])


if __name__ == "__main__":
    unittest.main()

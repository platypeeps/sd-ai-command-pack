"""Tests for .github/scripts/summarize_shell_coverage.py.

The summarizer is part of the shell-coverage CI lane: it turns kcov's merged
Cobertura report into the single "<covered> <total> <pct>" line the report
step publishes, and its exit status decides whether CI treats the run as a
plumbing failure. It has several branches (basename union across tempdir
copies, marker/.sh filtering, zero-line hard-fail, unreadable report), none of
which were covered — this pins them.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".github/scripts/summarize_shell_coverage.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("summarize_shell_coverage", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_mod = _load_module()


def _cobertura(classes: str) -> str:
    """Wrap <class> fragments in a minimal Cobertura document."""
    return textwrap.dedent(
        f"""\
        <?xml version="1.0" ?>
        <coverage>
          <packages><package><classes>
        {classes}
          </classes></package></packages>
        </coverage>
        """
    )


def _cls(filename: str, lines: list[tuple[int, int]]) -> str:
    line_tags = "".join(f'<line number="{n}" hits="{h}"/>' for n, h in lines)
    return f'<class filename="{filename}"><lines>{line_tags}</lines></class>'


class _CoberturaTempMixin(unittest.TestCase):
    def _report(self, xml: str | None) -> Path:
        """Return a cobertura.xml path in a per-test tempdir (missing if xml is None)."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "cobertura.xml"
        if xml is not None:
            path.write_text(xml, encoding="utf-8")
        return path


class SummarizeHelperTests(_CoberturaTempMixin):
    def test_counts_covered_and_total_for_shipped_shell(self) -> None:
        xml = _cobertura(
            _cls(
                "scripts/sd-ai-command-pack-full-check.sh",
                [(1, 1), (2, 0), (3, 4)],
            )
        )
        covered, total = _mod.summarize(self._report(xml))
        self.assertEqual((covered, total), (2, 3))

    def test_unions_line_numbers_across_basename_copies(self) -> None:
        # Same script, two tempdir copies: line 1 covered in copy A, line 2 in
        # copy B. The union is 2 covered / 2 total, not a per-copy sum of 4.
        xml = _cobertura(
            _cls("/tmp/a/scripts/sd-ai-command-pack-shell-lib.sh", [(1, 1), (2, 0)])
            + _cls("/tmp/b/scripts/sd-ai-command-pack-shell-lib.sh", [(1, 0), (2, 1)])
        )
        covered, total = _mod.summarize(self._report(xml))
        self.assertEqual((covered, total), (2, 2))

    def test_ignores_non_marker_and_non_sh_files(self) -> None:
        xml = _cobertura(
            _cls("scripts/sd-ai-command-pack-full-check.sh", [(1, 1)])
            + _cls("scripts/some-other-tool.sh", [(1, 1), (2, 1)])
            + _cls("scripts/sd-ai-command-pack-review.py", [(1, 1), (2, 1)])
        )
        covered, total = _mod.summarize(self._report(xml))
        self.assertEqual((covered, total), (1, 1))


class SummarizeCliExitStatusTests(_CoberturaTempMixin):
    def _run(self, xml: str | None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(_SCRIPT), str(self._report(xml))],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_exit_0_and_prints_percentage_on_real_measurement(self) -> None:
        xml = _cobertura(
            _cls("scripts/sd-ai-command-pack-full-check.sh", [(1, 1), (2, 0)])
        )
        result = self._run(xml)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "1 2 50.0")

    def test_exit_0_and_zero_percent_when_measured_but_unexercised(self) -> None:
        # covered == 0 but total > 0 is data (0.0%), not a plumbing failure —
        # failing here would be a hidden >0% floor, which R4 forbids.
        xml = _cobertura(
            _cls("scripts/sd-ai-command-pack-full-check.sh", [(1, 0), (2, 0)])
        )
        result = self._run(xml)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "0 2 0.0")

    def test_exit_2_when_no_shipped_shell_lines_measured(self) -> None:
        # No shipped-shell class at all: total == 0 → broken plumbing.
        xml = _cobertura(_cls("scripts/some-other-tool.sh", [(1, 1)]))
        result = self._run(xml)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("zero shipped-shell lines", result.stderr)

    def test_exit_1_when_report_missing(self) -> None:
        result = self._run(None)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("cannot read", result.stderr)


if __name__ == "__main__":
    unittest.main()

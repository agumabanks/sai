"""
Tests for skill loading — verifies all skills load without errors,
missing dependencies are installed, and the skill loader works correctly.

Fulfills: VAL-FOUND-006, VAL-FOUND-007
"""

import sys
import os
from pathlib import Path

import pytest

# Ensure backend is on sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ---------------------------------------------------------------------------
# VAL-FOUND-007: Missing dependencies installed
# ---------------------------------------------------------------------------

class TestDependencyImports:
    """Verify that required packages are installed and importable."""

    def test_duckduckgo_search_importable(self):
        """duckduckgo-search package is installed and importable."""
        import duckduckgo_search  # noqa: F401
        assert hasattr(duckduckgo_search, "DDGS")

    def test_aiomysql_importable(self):
        """aiomysql package is installed and importable."""
        import aiomysql  # noqa: F401
        assert hasattr(aiomysql, "connect")

    def test_beautifulsoup4_importable(self):
        """beautifulsoup4 (bs4) package is installed and importable."""
        from bs4 import BeautifulSoup  # noqa: F401
        # Quick sanity: parse a trivial snippet
        soup = BeautifulSoup("<p>hello</p>", "html.parser")
        assert soup.p.text == "hello"


# ---------------------------------------------------------------------------
# VAL-FOUND-006: All skills load without errors
# ---------------------------------------------------------------------------

class TestSkillDiscovery:
    """Verify skill manifest discovery."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from core.skills.manifest import discover_manifests
        self.skills_dir = os.path.join(BACKEND_DIR, "skills")
        self.manifests = discover_manifests(self.skills_dir)

    def test_discover_finds_skills(self):
        """Skill discovery finds at least 30 skills."""
        assert len(self.manifests) >= 30, (
            f"Expected ≥30 skills, found {len(self.manifests)}"
        )

    def test_each_manifest_has_required_fields(self):
        """Every discovered manifest has name and description."""
        for m in self.manifests:
            assert m.name, f"Manifest at {m.path} has no name"
            assert m.description, f"Skill '{m.name}' has no description"

    def test_each_manifest_has_handler_file(self):
        """Every discovered manifest has a corresponding handler.py file."""
        for m in self.manifests:
            handler = m.handler_path
            assert os.path.exists(handler), (
                f"Skill '{m.name}' missing handler at {handler}"
            )


class TestSkillLoading:
    """Verify all skills load without import errors or scanner rejections."""

    @pytest.fixture(autouse=True)
    async def _load_skills(self):
        from core.skills.loader import SkillLoader
        from core.skills.manifest import discover_manifests

        self.skills_dir = os.path.join(BACKEND_DIR, "skills")
        self.loader = SkillLoader(skills_dir=self.skills_dir)
        self.manifests = discover_manifests(self.skills_dir)
        self.loaded = await self.loader.load_all()

    @pytest.mark.asyncio
    async def test_all_skills_load_successfully(self):
        """Every discovered skill loads without errors."""
        failed = [m.name for m in self.manifests if m.name not in self.loaded]
        assert not failed, (
            f"Skills failed to load: {failed}. "
            f"Loaded {len(self.loaded)}/{len(self.manifests)}"
        )

    @pytest.mark.asyncio
    async def test_loaded_count_matches_discovered(self):
        """Number of loaded skills equals number of discovered manifests."""
        assert len(self.loaded) == len(self.manifests), (
            f"Loaded {len(self.loaded)} but discovered {len(self.manifests)}"
        )

    @pytest.mark.asyncio
    async def test_no_skill_has_error_status(self):
        """No skill has import errors or missing dependencies."""
        # Reload individually to get detailed errors
        for m in self.manifests:
            skill = await self.loader.load(m)
            assert skill is not None, (
                f"Skill '{m.name}' failed to load (returned None)"
            )

    @pytest.mark.asyncio
    async def test_test_dummy_skill_loads(self):
        """The test_dummy skill loads without errors (no undefined references)."""
        assert "test_dummy" in self.loaded, "test_dummy skill not loaded"
        skill = self.loaded["test_dummy"]
        assert skill.name == "test_dummy"

    @pytest.mark.asyncio
    async def test_test_dummy_skill_executes(self):
        """The test_dummy skill can execute its echo action."""
        from core.skills.base import SkillContext
        skill = self.loaded["test_dummy"]
        result = await skill.execute(
            {"action": "echo", "message": "hello"}, SkillContext()
        )
        assert result.success is True
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_previously_broken_skills_now_load(self):
        """Skills that were previously rejected (github, ssl_monitor,
        system_diagnostics, tmux_runner) now load successfully."""
        previously_broken = ["github", "ssl_monitor", "system_diagnostics", "tmux_runner"]
        for name in previously_broken:
            assert name in self.loaded, (
                f"Previously broken skill '{name}' still fails to load"
            )


class TestSecurityScannerPermissions:
    """Verify the scanner respects manifest permissions."""

    def test_scanner_allows_subprocess_with_shell_permission(self):
        """Skills with 'shell' permission can use subprocess.run()."""
        from core.skills.scanner import SkillScanner

        scanner = SkillScanner()
        source = 'result = subprocess.run(["git", "status"], capture_output=True)\n'

        # Without shell permission → critical
        result_no_perm = scanner.scan_source(source, permissions=[])
        has_critical_no_perm = any(
            f.severity == "critical" and f.rule_id == "dangerous-exec"
            for f in result_no_perm.findings
        )
        assert has_critical_no_perm, "Should flag subprocess as critical without shell perm"

        # With shell permission → downgraded to warn
        result_with_perm = scanner.scan_source(source, permissions=["shell"])
        has_critical_with_perm = any(
            f.severity == "critical" and f.rule_id == "dangerous-exec"
            for f in result_with_perm.findings
        )
        assert not has_critical_with_perm, "Should NOT flag subprocess as critical with shell perm"
        assert result_with_perm.passed, "Scan should pass with shell permission"

    def test_scanner_does_not_flag_re_compile(self):
        """re.compile() is not flagged as dynamic code execution."""
        from core.skills.scanner import SkillScanner

        scanner = SkillScanner()
        source = '_PATTERN = re.compile(r"foo")\n'
        result = scanner.scan_source(source)
        dynamic_code_findings = [
            f for f in result.findings if f.rule_id == "dynamic-code"
        ]
        assert not dynamic_code_findings, (
            f"re.compile() incorrectly flagged: {dynamic_code_findings}"
        )
        assert result.passed

    def test_scanner_still_flags_eval(self):
        """eval() is still flagged as dangerous."""
        from core.skills.scanner import SkillScanner

        scanner = SkillScanner()
        source = 'result = eval(user_input)\n'
        result = scanner.scan_source(source)
        assert not result.passed, "eval() should still be flagged as critical"

    def test_scanner_still_flags_exec(self):
        """exec() is still flagged as dangerous."""
        from core.skills.scanner import SkillScanner

        scanner = SkillScanner()
        source = 'exec(code_string)\n'
        result = scanner.scan_source(source)
        assert not result.passed, "exec() should still be flagged as critical"

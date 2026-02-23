"""
Skill Security Scanner — static analysis before loading skills.

Scans Python source code for dangerous patterns:
  - Shell command execution (os.system, subprocess)
  - Dynamic code execution (eval, exec)
  - Credential leaks (hardcoded secrets)
  - Network exfiltration (requests + file reads)
  - Filesystem writes outside allowed paths
  - Import of prohibited modules

Adapted from the IntelligenceScanner's LINE_RULES pattern.
"""

import re
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ScanFinding:
    """A single security finding from source analysis."""

    rule_id: str
    severity: str  # "critical", "warn", "info"
    message: str
    line: int = 0
    evidence: str = ""

    def __repr__(self) -> str:
        return f"<{self.severity.upper()}:{self.rule_id} L{self.line}>"


@dataclass
class ScanResult:
    """Result of scanning a skill's source code."""

    passed: bool
    findings: list[ScanFinding] = field(default_factory=list)
    skill_name: str = ""

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "critical")

    @property
    def warn_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warn")


# Security rules — patterns that indicate dangerous code
SECURITY_RULES = [
    {
        "id": "dangerous-exec",
        "severity": "critical",
        "message": "Shell command execution detected",
        "pattern": r"\b(os\.system|os\.popen|subprocess\.(Popen|run|call|check_call|check_output)|shutil\.rmtree)\s*\(",
    },
    {
        "id": "dynamic-code",
        "severity": "critical",
        "message": "Dynamic code execution (eval/exec/compile)",
        "pattern": r"\beval\s*\(|\bexec\s*\(|\bcompile\s*\(",
    },
    {
        "id": "import-os-system",
        "severity": "critical",
        "message": "Direct import of dangerous module function",
        "pattern": r"from\s+os\s+import\s+(system|popen)|from\s+subprocess\s+import",
    },
    {
        "id": "credential-leak",
        "severity": "warn",
        "message": "Potential hardcoded secret or token",
        "pattern": r"(password|secret|key|token|api_key)\s*=\s*['\"][A-Za-z0-9+/=]{16,}['\"]",
    },
    {
        "id": "network-exfil",
        "severity": "warn",
        "message": "Network access detected (must be declared in permissions)",
        "pattern": r"(requests\.(get|post|put|delete|patch)|urllib\.request|httpx\.(get|post|AsyncClient)|aiohttp\.ClientSession)",
    },
    {
        "id": "file-write",
        "severity": "warn",
        "message": "File write operation detected (must be declared in permissions)",
        "pattern": r"open\s*\([^)]*['\"]w['\"]|\.write\s*\(|shutil\.(copy|move)",
    },
    {
        "id": "pickle-load",
        "severity": "critical",
        "message": "Pickle deserialization is a code execution vector",
        "pattern": r"pickle\.loads?\s*\(|pickle\.Unpickler",
    },
    {
        "id": "ctypes-usage",
        "severity": "critical",
        "message": "ctypes/cffi usage can bypass Python safety",
        "pattern": r"\bctypes\b|\bcffi\b",
    },
    {
        "id": "env-access",
        "severity": "info",
        "message": "Environment variable access (review for credential exposure)",
        "pattern": r"os\.environ|os\.getenv",
    },
]

# Modules that skills should never import
PROHIBITED_IMPORTS = {
    "ctypes", "cffi", "importlib", "code", "codeop",
    "multiprocessing", "signal", "resource",
}


class SkillScanner:
    """Static analysis scanner for skill source code."""

    def __init__(self, extra_rules: list[dict] | None = None):
        self.rules = list(SECURITY_RULES)
        if extra_rules:
            self.rules.extend(extra_rules)

    def scan_source(self, source: str, filename: str = "unknown") -> ScanResult:
        """Scan source code for security risks.

        Args:
            source: Python source code as a string.
            filename: Name of the file being scanned (for reporting).

        Returns:
            ScanResult with pass/fail and detailed findings.
        """
        findings = []
        lines = source.split("\n")

        # Check line-level rules
        for rule in self.rules:
            for i, line in enumerate(lines):
                # Skip comments
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue

                match = re.search(rule["pattern"], line)
                if match:
                    findings.append(
                        ScanFinding(
                            rule_id=rule["id"],
                            severity=rule["severity"],
                            message=rule["message"],
                            line=i + 1,
                            evidence=stripped[:120],
                        )
                    )

        # Check for prohibited imports
        for line_num, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue

            import_match = re.match(r"^(?:from|import)\s+(\S+)", stripped)
            if import_match:
                module = import_match.group(1).split(".")[0]
                if module in PROHIBITED_IMPORTS:
                    findings.append(
                        ScanFinding(
                            rule_id="prohibited-import",
                            severity="critical",
                            message=f"Prohibited import: {module}",
                            line=line_num + 1,
                            evidence=stripped[:120],
                        )
                    )

        # Determine pass/fail: any critical finding = fail
        has_critical = any(f.severity == "critical" for f in findings)

        return ScanResult(
            passed=not has_critical,
            findings=findings,
            skill_name=filename,
        )

    def scan_file(self, filepath: str) -> ScanResult:
        """Scan a Python file for security risks.

        Args:
            filepath: Path to the Python file.

        Returns:
            ScanResult.
        """
        try:
            with open(filepath, "r") as f:
                source = f.read()
            return self.scan_source(source, filename=filepath)
        except FileNotFoundError:
            return ScanResult(
                passed=False,
                findings=[
                    ScanFinding(
                        rule_id="file-not-found",
                        severity="critical",
                        message=f"File not found: {filepath}",
                    )
                ],
                skill_name=filepath,
            )
        except Exception as e:
            return ScanResult(
                passed=False,
                findings=[
                    ScanFinding(
                        rule_id="scan-error",
                        severity="critical",
                        message=f"Scan error: {e}",
                    )
                ],
                skill_name=filepath,
            )

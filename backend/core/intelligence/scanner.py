"""
Intelligence Scanner — autonomous domain knowledge extraction.

Expanded from hardcoded repo list to auto-discovery of:
  - All repos under /var/www/ (production)
  - Cloned repos for learning
  - Deep code analysis: architecture, API endpoints, service dependencies
  - High-value file scanning (README, config files, Dockerfiles, etc.)
"""

import os
import logging
import asyncio
import re
import json
import hashlib
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class SecurityFinding:
    """Represents a security risk found in code."""

    def __init__(
        self,
        rule_id: str,
        severity: str,
        message: str,
        file: str = "",
        line: int = 0,
        evidence: str = "",
    ):
        self.rule_id = rule_id
        self.severity = severity  # critical, warn, info
        self.message = message
        self.file = file
        self.line = line
        self.evidence = evidence
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self):
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "file": self.file,
            "line": self.line,
            "evidence": self.evidence,
            "timestamp": self.timestamp.isoformat(),
        }


class IntelligenceScanner:
    """Autonomous domain knowledge extractor — scans repos for intelligence."""

    # Directories to auto-discover repos
    SCAN_DIRS = ["/var/www"]

    # Directories to explicitly skip
    SKIP_DIRS = {
        "node_modules", ".git", "vendor", "__pycache__", ".next",
        "dist", "build", ".cache", "storage", "logs",
    }

    # High-value files for documentation intelligence
    KNOWLEDGE_FILES = [
        "README.md", "README", "ARCHITECTURE.md", "API.md",
        "DEPLOYMENT_GUIDE.md", "architectural-map.md",
        "docs/overview.md", "system_audit_report.md",
    ]

    # High-value files for tech stack intelligence
    TECH_FILES = [
        "package.json", "composer.json", "requirements.txt", "Pipfile",
        "pyproject.toml", "Gemfile", "Cargo.toml", "go.mod",
        "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
        ".env.example", "ecosystem.config.js",
    ]

    # Security scanning rules (from OpenClaw patterns)
    LINE_RULES = [
        {
            "id": "dangerous-exec",
            "severity": "critical",
            "message": "Shell command execution detected",
            "pattern": r"\b(os\.system|subprocess\.(Popen|run|call|check_call|check_output)|shutil\.rmtree)\s*\(",
        },
        {
            "id": "dynamic-code",
            "severity": "critical",
            "message": "Dynamic code execution (eval/exec)",
            "pattern": r"\beval\s*\(|\bexec\s*\(",
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
            "message": "Network activity combined with file read",
            "pattern": r"(requests\.(get|post|put|delete)|urllib\.request|http\.client)",
            "requires_context": r"(open\(|read\(|readFileSync)",
        },
        {
            "id": "sql-injection",
            "severity": "critical",
            "message": "Potential SQL injection (string concat in query)",
            "pattern": r"(\.execute|\.query|\.raw)\s*\(\s*f['\"]|\.execute\(.*\+\s*(request|params|input)",
        },
        {
            "id": "xss-risk",
            "severity": "warn",
            "message": "Potential XSS (unescaped output)",
            "pattern": r"innerHTML\s*=|v-html|dangerouslySetInnerHTML|\{!!.*!!\}",
        },
        {
            "id": "file-traversal",
            "severity": "critical",
            "message": "Potential path traversal vulnerability",
            "pattern": r"(\.\.\/|\.\.\\\\|path\.join\(.*request|os\.path\.join\(.*input)",
        },
    ]

    def __init__(self, base_dir: str = "/var/www"):
        self.base_dir = base_dir

        # Lazy imports to avoid circular dependencies
        self._brain = None
        self._memory = None

    @property
    def brain(self):
        if self._brain is None:
            from core.brain.engine import Brain
            self._brain = Brain()
        return self._brain

    @property
    def memory(self):
        if self._memory is None:
            from core.intelligence.memory import IntelligenceMemory
            self._memory = IntelligenceMemory()
        return self._memory

    def discover_repos(self) -> List[Dict[str, str]]:
        """Auto-discover all project repos under scan directories.

        Returns:
            List of dicts with 'name' and 'path' keys.
        """
        repos = []
        seen = set()

        for scan_dir in self.SCAN_DIRS:
            if not os.path.isdir(scan_dir):
                continue

            for entry in os.listdir(scan_dir):
                full_path = os.path.join(scan_dir, entry)
                if not os.path.isdir(full_path):
                    continue
                if entry in self.SKIP_DIRS or entry.startswith("."):
                    continue

                # Check if it looks like a project (has package manager files or src)
                is_project = any(
                    os.path.exists(os.path.join(full_path, f))
                    for f in [
                        "package.json", "composer.json", "requirements.txt",
                        "pyproject.toml", "Dockerfile", "manage.py",
                        "artisan", "Makefile", ".git",
                    ]
                )

                if is_project and entry not in seen:
                    repos.append({"name": entry, "path": full_path})
                    seen.add(entry)

        logger.info(f"Discovered {len(repos)} repos: {[r['name'] for r in repos]}")
        return repos

    def scan_source(self, source: str, filename: str = "unknown") -> List[SecurityFinding]:
        """Scan source code string for security risks."""
        findings = []
        lines = source.split("\n")

        for rule in self.LINE_RULES:
            if "requires_context" in rule and not re.search(
                rule["requires_context"], source
            ):
                continue

            for i, line in enumerate(lines):
                match = re.search(rule["pattern"], line)
                if match:
                    findings.append(
                        SecurityFinding(
                            rule_id=rule["id"],
                            severity=rule["severity"],
                            message=rule["message"],
                            file=filename,
                            line=i + 1,
                            evidence=line.strip()[:100],
                        )
                    )
                    break  # One finding per rule per file

        return findings

    async def scan_all(self):
        """Discover and scan all repos for domain intelligence + security."""
        logger.info("Starting autonomous intelligence scan...")

        repos = self.discover_repos()
        results = []

        for repo in repos:
            try:
                result = await self.scan_repo(repo["name"], repo["path"])
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to scan {repo['name']}: {e}")
                results.append({"name": repo["name"], "error": str(e)})

        logger.info(f"Intelligence scan complete — {len(results)} repos processed")
        return results

    async def scan_repo(self, name: str, path: str) -> Dict[str, Any]:
        """Analyze a repository for business intelligence and security risks.

        Returns dict with keys: name, tech_stack, security_findings, intelligence.
        """
        logger.info(f"Scanning repository: {name}")
        result = {"name": name, "path": path, "security_findings": [], "tech_stack": {}}

        # 1. Extract tech stack from config files
        result["tech_stack"] = self._extract_tech_stack(path)

        # 2. Security scan on source files
        security_findings = await self._scan_repo_security(path)
        result["security_findings"] = [f.to_dict() for f in security_findings]

        # 3. Extract documentation intelligence via LLM
        content = self._gather_knowledge_content(path)
        if content:
            intelligence = await self._analyze_with_llm(name, content)
            if intelligence:
                await self.memory.save_repo_context(name, intelligence)
                result["intelligence"] = intelligence

        return result

    def _extract_tech_stack(self, path: str) -> Dict[str, Any]:
        """Extract tech stack information from project config files."""
        stack = {
            "languages": [],
            "frameworks": [],
            "databases": [],
            "services": [],
        }

        # Check for key indicators
        indicators = {
            "package.json": ("Node.js", "javascript"),
            "composer.json": ("PHP", "php"),
            "requirements.txt": ("Python", "python"),
            "pyproject.toml": ("Python", "python"),
            "Gemfile": ("Ruby", "ruby"),
            "go.mod": ("Go", "go"),
            "Cargo.toml": ("Rust", "rust"),
        }

        for filename, (framework, lang) in indicators.items():
            if os.path.exists(os.path.join(path, filename)):
                if lang not in stack["languages"]:
                    stack["languages"].append(lang)
                stack["frameworks"].append(framework)

        # Check for frameworks in package.json
        pkg_path = os.path.join(path, "package.json")
        if os.path.exists(pkg_path):
            try:
                with open(pkg_path, "r") as f:
                    pkg = json.load(f)
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                if "next" in deps:
                    stack["frameworks"].append("Next.js")
                if "react" in deps:
                    stack["frameworks"].append("React")
                if "vue" in deps:
                    stack["frameworks"].append("Vue.js")
                if "express" in deps:
                    stack["frameworks"].append("Express")
                if "nuxt" in deps:
                    stack["frameworks"].append("Nuxt")
            except Exception:
                pass

        # Check for Laravel
        if os.path.exists(os.path.join(path, "artisan")):
            stack["frameworks"].append("Laravel")

        # Check for Docker
        if os.path.exists(os.path.join(path, "Dockerfile")):
            stack["services"].append("Docker")
        if os.path.exists(os.path.join(path, "docker-compose.yml")):
            stack["services"].append("Docker Compose")

        return stack

    async def _scan_repo_security(self, path: str) -> List[SecurityFinding]:
        """Recursively scan source files for security risks."""
        all_findings = []
        extensions = {".py", ".js", ".ts", ".php", ".rb", ".go", ".rs"}
        max_files = 100

        scanned = 0
        for root, dirs, files in os.walk(path):
            # Skip irrelevant directories
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]

            for fname in files:
                ext = os.path.splitext(fname)[1]
                if ext not in extensions:
                    continue

                filepath = os.path.join(root, fname)
                try:
                    with open(filepath, "r", errors="ignore") as f:
                        source = f.read(10000)  # First 10KB
                    findings = self.scan_source(source, filepath)
                    all_findings.extend(findings)
                except Exception:
                    continue

                scanned += 1
                if scanned >= max_files:
                    break
            if scanned >= max_files:
                break

        return all_findings

    def _gather_knowledge_content(self, path: str) -> str:
        """Gather high-value documentation content from a repo."""
        content = ""

        for filename in self.KNOWLEDGE_FILES + self.TECH_FILES:
            filepath = os.path.join(path, filename)
            if os.path.exists(filepath):
                try:
                    with open(filepath, "r", errors="ignore") as f:
                        file_content = f.read(5000)
                    content += f"\n--- {filename} ---\n{file_content}\n"
                except Exception:
                    continue

        return content

    async def _analyze_with_llm(
        self, name: str, content: str
    ) -> Dict[str, Any] | None:
        """Use the Brain to extract intelligence from repo documentation."""
        prompt = f"""Analyze the following documentation from the '{name}' repository.
Extract the core business purpose, key domain terminology, and strategic importance.

DOCUMENTATION:
{content[:4000]}

Return a JSON object with:
{{
    "summary": "2-3 sentences of business purpose",
    "key_terms": ["list", "of", "domain", "keywords"],
    "strategic_priority": "high/medium/low",
    "impact_areas": ["e.g., payments, logistics"],
    "tech_stack": ["languages and frameworks detected"]
}}
"""
        try:
            response = await self.brain.think(prompt, complexity="medium")
            match = re.search(r"\{[\s\S]*\}", response)
            if match:
                return json.loads(match.group())
        except Exception as e:
            logger.error(f"LLM analysis failed for {name}: {e}")

        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scanner = IntelligenceScanner()
    asyncio.run(scanner.scan_all())

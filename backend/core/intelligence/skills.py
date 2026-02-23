import os
import json
import logging
from typing import List, Dict, Any
from core.intelligence.memory import IntelligenceMemory
from core.intelligence.scanner import IntelligenceScanner

logger = logging.getLogger(__name__)

class AutonomousSkillMapper:
    """Manages autonomous tool discovery and installation."""
    def __init__(self, skills_dir: str = "/var/www/ai.sanaa.co/core/skills"):
        self.skills_dir = skills_dir
        self.memory = IntelligenceMemory()
        self.scanner = IntelligenceScanner()
        os.makedirs(self.skills_dir, exist_ok=True)

    async def discover_skills(self, repo_name: str, repo_path: str):
        """Scans a repo for potential tools that can be adapted as Sanaa skills."""
        logger.info(f"Mapping potential skills in {repo_name}...")
        
        # Look for scripts or specific utility folders
        skill_candidates = []
        for root, dirs, files in os.walk(repo_path):
            if "node_modules" in dirs: dirs.remove("node_modules")
            if ".git" in dirs: dirs.remove(".git")
            
            for file in files:
                if file.endswith(".py") or file.endswith(".sh"):
                    skill_candidates.append(os.path.join(root, file))
        
        # In a real scenario, we'd use the Brain to filter these.
        # For now, we'll just log discoveries to Strategic Signals.
        if skill_candidates:
            self.memory.add_strategic_signal({
                "category": "discovery",
                "title": f"Skill Candidates in {repo_name}",
                "summary": f"Found {len(skill_candidates)} potential tools for Sanaa integration.",
                "score": 3,
                "tags": ["skill_mapping", repo_name]
            })

    async def install_skill(self, name: str, source_code: str):
        """Audits and installs a new skill."""
        findings = self.scanner.scan_source(source_code, name)
        
        critical_findings = [f for f in findings if f.severity == "critical"]
        if critical_findings:
            logger.error(f"Cannot install skill '{name}': Critical security risks detected.")
            return False, critical_findings

        skill_path = os.path.join(self.skills_dir, f"{name}.py")
        with open(skill_path, "w") as f:
            f.write(source_code)
            
        logger.info(f"Successfully installed skill: {name}")
        return True, findings

"""
Intelligence Memory — persistent domain knowledge store.

Migrated from flat-file JSON to PostgreSQL (system_knowledge + agent_memory tables).
Backward-compatible: imports existing JSON data on first run.
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Legacy JSON path for backward-compatible import
LEGACY_JSON = "/var/www/ai.sanaa.co/data/intelligence/domain_context.json"


class IntelligenceMemory:
    """Persistent domain memory backed by PostgreSQL.

    Data model:
      - Repo context → system_knowledge table (domain="repos", key=repo_name)
      - Strategic signals → agent_memory table (category="strategic_signal")
      - Global terms → system_knowledge table (domain="intelligence", key="global_terms")
    """

    def __init__(self):
        self._migrated = False

    async def _ensure_migrated(self):
        """One-time migration of legacy JSON data to database."""
        if self._migrated:
            return
        self._migrated = True

        if not os.path.exists(LEGACY_JSON):
            return

        try:
            with open(LEGACY_JSON, "r") as f:
                legacy = json.load(f)

            from core.database import SystemKnowledge

            # Migrate repos
            for repo_name, data in legacy.get("repos", {}).items():
                try:
                    await SystemKnowledge.upsert(
                        domain="repos",
                        key=repo_name,
                        value=json.dumps(data),
                        value_type="json",
                        source="intelligence_scanner",
                    )
                except Exception:
                    pass  # Skip duplicates

            logger.info(f"Migrated {len(legacy.get('repos', {}))} repos from legacy JSON")
        except Exception as e:
            logger.warning(f"Legacy migration skipped: {e}")

    async def save_repo_context(self, repo_name: str, data: Dict[str, Any]):
        """Persist repo intelligence to system_knowledge table."""
        await self._ensure_migrated()
        try:
            from core.database import SystemKnowledge

            await SystemKnowledge.upsert(
                domain="repos",
                key=repo_name,
                value=json.dumps(data),
                value_type="json",
                source="intelligence_scanner",
            )
        except Exception as e:
            logger.error(f"Failed to save repo context for {repo_name}: {e}")
            # Fallback: save to legacy JSON
            self._persist_legacy(repo_name, data)

    async def add_strategic_signal(self, signal: Dict[str, Any]):
        """Store a strategic signal in the database."""
        try:
            from core.database import StrategicSignal

            await StrategicSignal.create(
                title=signal.get("title", "Untitled Signal"),
                classification=signal.get("classification", "general"),
                summary=signal.get("summary", ""),
                score=signal.get("score", 50),
                source=signal.get("source", "intelligence_scanner"),
                business_impact=signal.get("business_impact"),
                tags=signal.get("tags"),
                link=signal.get("link"),
            )
        except Exception as e:
            logger.error(f"Failed to save strategic signal: {e}")

    async def get_all_context(self, category: str = None) -> str:
        """Build LLM context string from all stored domain knowledge."""
        await self._ensure_migrated()
        summary = "DOMAIN KNOWLEDGE & CONTEXT:\n"

        try:
            from core.database import SystemKnowledge, StrategicSignal

            # Fetch repo knowledge
            repos = await SystemKnowledge.get_by_domain("repos")
            if repos:
                for entry in repos:
                    try:
                        data = json.loads(entry.value)
                        summary += f"- {entry.key.upper()}: {data.get('summary', 'No summary')}\n"
                        if data.get("key_terms"):
                            summary += f"  Keywords: {', '.join(data['key_terms'])}\n"
                    except json.JSONDecodeError:
                        summary += f"- {entry.key.upper()}: {entry.value[:200]}\n"

            # Fetch recent strategic signals
            signals = await StrategicSignal.get_recent(limit=10)
            if signals:
                summary += "\nRECENT STRATEGIC SIGNALS:\n"
                for sig in signals:
                    cat = getattr(sig, "classification", None) or "General"
                    title = sig.title or "Untitled"
                    text = (sig.summary or "")[:200]
                    summary += f"- [{cat}] {title}: {text}...\n"

        except Exception as e:
            logger.warning(f"DB context fetch failed, returning minimal: {e}")
            return "No specific domain context loaded."

        if summary == "DOMAIN KNOWLEDGE & CONTEXT:\n":
            return "No specific domain context loaded."

        return summary

    def _persist_legacy(self, repo_name: str, data: Dict[str, Any]):
        """Fallback: persist to legacy JSON file."""
        try:
            context = {}
            if os.path.exists(LEGACY_JSON):
                with open(LEGACY_JSON, "r") as f:
                    context = json.load(f)

            context.setdefault("repos", {})[repo_name] = data

            os.makedirs(os.path.dirname(LEGACY_JSON), exist_ok=True)
            with open(LEGACY_JSON, "w") as f:
                json.dump(context, f, indent=2)
        except Exception as e:
            logger.error(f"Legacy persist failed: {e}")

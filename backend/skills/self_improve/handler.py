"""
Self-Improve Skill — OpenClaw-inspired self-improving agent pattern.

Implements three actions:
  1. analyze_errors: Scan recent failed skill executions from skill_runs table,
     create ERRORS entries in the learning log system.
  2. learn_patterns: Detect recurring themes across learning log entries,
     create LEARNINGS entries for identified patterns.
  3. suggest_improvements: Use Brain/LLM to generate actionable improvement
     recommendations based on error data and learning patterns.

All actions log their results to the structured learning system for
continuous self-improvement.
"""

import logging
import re
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from core.skills.base import BaseSkill, SkillResult
from core.database import AsyncSessionLocal, SkillRun
from core.memory.learning_logs import LearningLogManager
from sqlalchemy import select, desc, and_

logger = logging.getLogger(__name__)


class SelfImproveSkill(BaseSkill):
    """Self-improving agent that analyzes errors, learns patterns, and suggests improvements."""

    name = "self_improve"

    async def execute(self, params: Dict[str, Any], context: Any) -> SkillResult:
        action = params.get("action")

        if not action:
            return SkillResult(success=False, error="Missing required parameter: action")

        if action == "analyze_errors":
            return await self._analyze_errors(params, context)
        elif action == "learn_patterns":
            return await self._learn_patterns(params, context)
        elif action == "suggest_improvements":
            return await self._suggest_improvements(params, context)

        return SkillResult(success=False, error=f"Unknown action: {action}")

    # ------------------------------------------------------------------
    # Action 1: analyze_errors
    # ------------------------------------------------------------------

    async def _analyze_errors(self, params: dict, context: Any) -> SkillResult:
        """Scan recent failed skill runs and create ERRORS entries in learning logs."""
        limit = int(params.get("limit", 50))
        days = int(params.get("days", 7))
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        try:
            # Fetch recent failed skill runs
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(SkillRun)
                    .where(
                        and_(
                            SkillRun.status == "failed",
                            SkillRun.started_at >= cutoff,
                        )
                    )
                    .order_by(desc(SkillRun.started_at))
                    .limit(limit)
                )
                failed_runs = result.scalars().all()

            if not failed_runs:
                return SkillResult(
                    success=True,
                    output=f"No recent failed skill runs in the last {days} days.",
                    data={"errors_found": 0, "entries_created": 0},
                )

            # Group failures by skill name for summary
            failures_by_skill: dict[str, list] = defaultdict(list)
            for run in failed_runs:
                failures_by_skill[run.skill_name].append({
                    "action": run.action or "unknown",
                    "error": run.error_message or "No error message",
                    "timestamp": run.started_at.isoformat() if run.started_at else "unknown",
                    "input_data": run.input_data,
                })

            # Create ERRORS entries in learning logs
            llm = LearningLogManager()
            entries_created = 0

            for skill_name, failures in failures_by_skill.items():
                error_summary = "; ".join(
                    f"[{f['action']}] {f['error'][:100]}" for f in failures[:5]
                )
                content = (
                    f"Skill '{skill_name}' had {len(failures)} failure(s) in the last "
                    f"{days} days. Errors: {error_summary}"
                )

                try:
                    await llm.add_entry(
                        log_type="ERRORS",
                        source="error",
                        content=content,
                        category="skill_failure",
                        confidence=min(0.9, 0.5 + len(failures) * 0.1),
                    )
                    entries_created += 1
                except Exception as e:
                    logger.warning(f"Failed to create learning entry for {skill_name}: {e}")

            # Build summary output
            lines = [f"## Error Analysis (last {days} days)\n"]
            lines.append(f"Found **{len(failed_runs)}** failed skill runs across "
                         f"**{len(failures_by_skill)}** skills.\n")

            for skill_name, failures in sorted(
                failures_by_skill.items(), key=lambda x: -len(x[1])
            ):
                lines.append(f"- **{skill_name}**: {len(failures)} failures")
                for f in failures[:3]:
                    lines.append(f"  - [{f['action']}] {f['error'][:80]}")

            lines.append(f"\nCreated {entries_created} ERRORS entries in learning logs.")

            return SkillResult(
                success=True,
                output="\n".join(lines),
                data={
                    "errors_found": len(failed_runs),
                    "skills_affected": len(failures_by_skill),
                    "entries_created": entries_created,
                    "by_skill": {
                        name: len(fails) for name, fails in failures_by_skill.items()
                    },
                },
            )

        except Exception as e:
            logger.error(f"analyze_errors failed: {e}", exc_info=True)
            return SkillResult(success=False, error=f"Error analyzing failures: {e}")

    # ------------------------------------------------------------------
    # Action 2: learn_patterns
    # ------------------------------------------------------------------

    async def _learn_patterns(self, params: dict, context: Any) -> SkillResult:
        """Detect recurring themes in learning log entries and create LEARNINGS entries."""
        limit = int(params.get("limit", 50))

        try:
            llm = LearningLogManager()
            entries = await llm.get_entries(limit=limit)

            if not entries:
                return SkillResult(
                    success=True,
                    output="No learning log entries found. Nothing to analyze.",
                    data={"patterns_detected": [], "entries_analyzed": 0},
                )

            # Group entries by category and detect recurring themes
            patterns = self._detect_patterns(entries)

            # Create LEARNINGS entries for each detected pattern
            created = 0
            pattern_summaries = []

            for pattern in patterns:
                try:
                    await llm.add_entry(
                        log_type="LEARNINGS",
                        source="reflection",
                        content=pattern["description"],
                        category="pattern_detection",
                        confidence=min(1.0, 0.5 + pattern["count"] * 0.1),
                    )
                    created += 1
                    pattern_summaries.append(pattern)
                except Exception as e:
                    logger.warning(f"Failed to create pattern entry: {e}")

            # Build output
            lines = [f"## Pattern Analysis\n"]
            lines.append(f"Analyzed **{len(entries)}** learning log entries.\n")

            if patterns:
                lines.append(f"Detected **{len(patterns)}** recurring patterns:\n")
                for p in patterns:
                    lines.append(
                        f"- **{p['theme']}** ({p['count']} occurrences, "
                        f"categories: {', '.join(p['categories'])})"
                    )
                    lines.append(f"  {p['description'][:120]}")
            else:
                lines.append("No recurring patterns detected.")

            lines.append(f"\nCreated {created} LEARNINGS entries.")

            return SkillResult(
                success=True,
                output="\n".join(lines),
                data={
                    "patterns_detected": pattern_summaries,
                    "entries_analyzed": len(entries),
                    "learnings_created": created,
                },
            )

        except Exception as e:
            logger.error(f"learn_patterns failed: {e}", exc_info=True)
            return SkillResult(success=False, error=f"Error learning patterns: {e}")

    def _detect_patterns(self, entries: list[dict]) -> list[dict]:
        """Detect recurring themes by grouping entries with similar content.

        Uses keyword extraction and frequency analysis to find patterns
        that appear multiple times across entries.
        """
        # Extract keywords from each entry's content
        keyword_entries: dict[str, list[dict]] = defaultdict(list)

        for entry in entries:
            content = entry.get("content", "")
            keywords = self._extract_keywords(content)
            for kw in keywords:
                keyword_entries[kw].append(entry)

        # Find keywords that appear in multiple entries (threshold: 2+)
        patterns = []
        seen_groups = set()

        for keyword, group_entries in sorted(
            keyword_entries.items(), key=lambda x: -len(x[1])
        ):
            if len(group_entries) < 2:
                continue

            # Avoid overlapping patterns
            entry_ids = frozenset(e.get("id", i) for i, e in enumerate(group_entries))
            if entry_ids in seen_groups:
                continue
            seen_groups.add(entry_ids)

            categories = list(set(e.get("category", "unknown") for e in group_entries))
            log_types = list(set(e.get("log_type", "unknown") for e in group_entries))

            sample_content = group_entries[0].get("content", "")[:200]
            patterns.append({
                "theme": keyword,
                "count": len(group_entries),
                "categories": categories,
                "log_types": log_types,
                "description": (
                    f"Recurring pattern '{keyword}' detected {len(group_entries)} times "
                    f"across {', '.join(log_types)} entries. "
                    f"Example: {sample_content}"
                ),
            })

            # Limit to top 10 patterns
            if len(patterns) >= 10:
                break

        return patterns

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """Extract meaningful keywords from text for pattern matching.

        Strips common stop words and returns multi-word phrases and
        significant single words.
        """
        if not text:
            return []

        stop_words = {
            "the", "a", "an", "is", "was", "were", "are", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "shall", "can",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "as", "into", "through", "during", "before", "after", "above",
            "below", "it", "its", "this", "that", "these", "those", "and",
            "but", "or", "nor", "not", "no", "so", "if", "then", "than",
            "too", "very", "just", "about", "up", "out", "all", "also",
        }

        # Clean and tokenize
        cleaned = re.sub(r"[^a-zA-Z0-9_\s-]", " ", text.lower())
        words = [w for w in cleaned.split() if len(w) > 2 and w not in stop_words]

        # Build bigrams for more specific patterns
        keywords = []
        for i in range(len(words) - 1):
            bigram = f"{words[i]} {words[i + 1]}"
            keywords.append(bigram)

        # Also include significant single words (5+ chars)
        keywords.extend(w for w in words if len(w) >= 5)

        return keywords[:20]  # Limit to prevent explosion

    # ------------------------------------------------------------------
    # Action 3: suggest_improvements
    # ------------------------------------------------------------------

    async def _suggest_improvements(self, params: dict, context: Any) -> SkillResult:
        """Generate actionable improvement recommendations via LLM."""
        limit = int(params.get("limit", 50))
        days = int(params.get("days", 7))

        # Verify Brain is available
        if not context or not getattr(context, "brain", None):
            return SkillResult(
                success=False,
                error="Brain/LLM not available. Cannot generate improvement suggestions.",
            )

        try:
            # Gather error data
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            error_summary = await self._gather_error_summary(cutoff, limit)

            # Gather learning log data
            llm = LearningLogManager()
            recent_entries = await llm.get_entries(limit=limit)

            learning_summary = self._summarize_learnings(recent_entries)

            # Build LLM prompt
            prompt = self._build_improvement_prompt(error_summary, learning_summary, days)

            # Get LLM recommendations
            recommendations = await context.brain.think(
                prompt, complexity="balanced", session_id=getattr(context, "session_id", None)
            )

            # Log the recommendation to learning system
            try:
                await llm.add_entry(
                    log_type="LEARNINGS",
                    source="reflection",
                    content=f"Self-improvement analysis generated recommendations: {recommendations[:500]}",
                    category="improvement_suggestion",
                    confidence=0.7,
                )
            except Exception as e:
                logger.warning(f"Failed to log improvement suggestion: {e}")

            return SkillResult(
                success=True,
                output=recommendations,
                data={
                    "errors_analyzed": error_summary.get("total_errors", 0),
                    "learnings_analyzed": len(recent_entries),
                    "recommendation_length": len(recommendations),
                },
            )

        except Exception as e:
            logger.error(f"suggest_improvements failed: {e}", exc_info=True)
            return SkillResult(success=False, error=f"Error generating suggestions: {e}")

    async def _gather_error_summary(self, cutoff: datetime, limit: int) -> dict:
        """Gather error summary from skill_runs for the LLM prompt."""
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(SkillRun)
                    .where(
                        and_(
                            SkillRun.status == "failed",
                            SkillRun.started_at >= cutoff,
                        )
                    )
                    .order_by(desc(SkillRun.started_at))
                    .limit(limit)
                )
                failed_runs = result.scalars().all()
        except Exception:
            failed_runs = []

        if not failed_runs:
            return {"total_errors": 0, "summary": "No recent errors found."}

        by_skill: dict[str, list[str]] = defaultdict(list)
        for run in failed_runs:
            by_skill[run.skill_name].append(run.error_message or "unknown error")

        lines = []
        for skill_name, errors in sorted(by_skill.items(), key=lambda x: -len(x[1])):
            unique_errors = list(set(errors))[:3]
            lines.append(f"- {skill_name} ({len(errors)} failures): {'; '.join(e[:80] for e in unique_errors)}")

        return {
            "total_errors": len(failed_runs),
            "skills_affected": len(by_skill),
            "summary": "\n".join(lines),
        }

    @staticmethod
    def _summarize_learnings(entries: list[dict]) -> str:
        """Summarize learning entries for the LLM prompt."""
        if not entries:
            return "No recent learning entries."

        by_type: dict[str, int] = defaultdict(int)
        samples = []
        for entry in entries[:20]:
            by_type[entry.get("log_type", "UNKNOWN")] += 1
            if len(samples) < 5:
                samples.append(
                    f"  [{entry.get('log_type', '?')}] {entry.get('content', '')[:100]}"
                )

        type_summary = ", ".join(f"{t}: {c}" for t, c in sorted(by_type.items()))
        return (
            f"Total entries: {len(entries)} ({type_summary})\n"
            f"Recent samples:\n" + "\n".join(samples)
        )

    @staticmethod
    def _build_improvement_prompt(error_summary: dict, learning_summary: str, days: int) -> str:
        """Build the LLM prompt for generating improvement recommendations."""
        return (
            f"You are the Sanaa AI Self-Improvement Analyst. Analyze the following data "
            f"from the last {days} days and provide actionable improvement recommendations.\n\n"
            f"## Recent Skill Errors ({error_summary.get('total_errors', 0)} total)\n"
            f"{error_summary.get('summary', 'None')}\n\n"
            f"## Learning Log Summary\n"
            f"{learning_summary}\n\n"
            f"## Instructions\n"
            f"Based on the above data, provide:\n"
            f"1. **Root Cause Analysis**: What are the most common failure patterns?\n"
            f"2. **Priority Fixes**: What should be fixed first (highest impact)?\n"
            f"3. **System Improvements**: Broader recommendations to prevent future issues.\n"
            f"4. **Learning Opportunities**: What should the system learn from these patterns?\n\n"
            f"Be specific and actionable. Reference specific skills and error patterns."
        )


# Register entry point
handler = SelfImproveSkill

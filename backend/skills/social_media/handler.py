"""
Social Media Skill — content creation, scheduling, and analytics.

Actions:
  - create_content: Generate platform-specific content for Twitter/X, LinkedIn, Facebook.
  - schedule_post: Create a scheduled post entry stored in the database.
  - analytics_summary: Summarize engagement metrics from configured social accounts.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import text, select, desc

from core.skills.base import BaseSkill, SkillContext, SkillResult
from core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# Platform-specific constraints and prompt templates
PLATFORM_CONFIG = {
    "twitter": {
        "max_chars": 280,
        "tone": "concise, engaging, with hashtags",
        "template": (
            "Write a tweet about the following topic. Must be under 280 characters "
            "including spaces. Use a concise, engaging tone. Include 1-3 relevant "
            "hashtags. Do NOT use markdown. Only output the tweet text.\n\n"
            "Topic: {topic}"
        ),
    },
    "linkedin": {
        "max_chars": 3000,
        "tone": "professional, insightful, thought-leadership",
        "template": (
            "Write a LinkedIn post about the following topic. Use a professional, "
            "insightful tone suitable for a business audience. Include a compelling "
            "hook in the first line. Keep it under 1300 characters for optimal "
            "engagement. Do NOT use markdown. Only output the post text.\n\n"
            "Topic: {topic}"
        ),
    },
    "facebook": {
        "max_chars": 5000,
        "tone": "casual, conversational, community-oriented",
        "template": (
            "Write a Facebook post about the following topic. Use a casual, "
            "conversational tone. Make it engaging and encourage comments. "
            "Include an emoji or two where appropriate. Keep it under 500 "
            "characters for optimal engagement. Do NOT use markdown. Only "
            "output the post text.\n\n"
            "Topic: {topic}"
        ),
    },
}

VALID_PLATFORMS = list(PLATFORM_CONFIG.keys())


class SocialMediaSkill(BaseSkill):
    """Social media content management skill."""

    name = "social_media"
    description = (
        "Social media content management: generate platform-specific content, "
        "schedule posts, and summarize engagement analytics."
    )
    version = "1.0.0"
    permissions = ["network"]
    tags = ["social-media", "marketing", "content", "scheduling", "analytics"]

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action")

        if action == "create_content":
            return await self._create_content(args, context)
        elif action == "schedule_post":
            return await self._schedule_post(args, context)
        elif action == "analytics_summary":
            return await self._analytics_summary(args, context)

        return SkillResult(
            success=False,
            error=f"Unknown action: {action}. Valid actions: create_content, schedule_post, analytics_summary",
        )

    # ------------------------------------------------------------------
    # create_content
    # ------------------------------------------------------------------
    async def _create_content(self, args: dict, context: SkillContext) -> SkillResult:
        topic = args.get("topic")
        platform = args.get("platform", "").lower()

        if not topic:
            return SkillResult(success=False, error="Parameter 'topic' is required for create_content.")

        if platform not in VALID_PLATFORMS:
            return SkillResult(
                success=False,
                error=(
                    f"Invalid platform: '{platform}'. "
                    f"Supported platforms: {', '.join(VALID_PLATFORMS)}"
                ),
            )

        config = PLATFORM_CONFIG[platform]
        prompt = config["template"].format(topic=topic)

        # Use Brain/LLM for content generation
        if not context.brain:
            return SkillResult(
                success=False,
                error="Brain engine not available for content generation.",
            )

        try:
            generated = await context.brain.think(
                prompt,
                complexity="fast",
                channel="social_media",
            )
        except Exception as e:
            logger.error(f"[SocialMedia] LLM generation failed: {e}")
            return SkillResult(success=False, error=f"Content generation failed: {e}")

        if not generated:
            return SkillResult(success=False, error="LLM returned empty content.")

        # Clean up the generated content
        generated = generated.strip().strip('"').strip("'")

        # Enforce character limit for Twitter
        if platform == "twitter" and len(generated) > config["max_chars"]:
            # Truncate at the last space before the limit and add ellipsis
            truncated = generated[: config["max_chars"] - 1]
            last_space = truncated.rfind(" ")
            if last_space > 0:
                truncated = truncated[:last_space]
            generated = truncated + "…"

        return SkillResult(
            success=True,
            output=generated,
            data={
                "platform": platform,
                "content": generated,
                "character_count": len(generated),
                "max_chars": config["max_chars"],
                "tone": config["tone"],
            },
        )

    # ------------------------------------------------------------------
    # schedule_post
    # ------------------------------------------------------------------
    async def _schedule_post(self, args: dict, context: SkillContext) -> SkillResult:
        platform = args.get("platform", "").lower()
        content = args.get("content")
        scheduled_time_str = args.get("scheduled_time")

        if not platform:
            return SkillResult(success=False, error="Parameter 'platform' is required for schedule_post.")

        if platform not in VALID_PLATFORMS:
            return SkillResult(
                success=False,
                error=(
                    f"Invalid platform: '{platform}'. "
                    f"Supported platforms: {', '.join(VALID_PLATFORMS)}"
                ),
            )

        if not content:
            return SkillResult(success=False, error="Parameter 'content' is required for schedule_post.")

        if not scheduled_time_str:
            return SkillResult(success=False, error="Parameter 'scheduled_time' is required for schedule_post.")

        # Parse the scheduled time
        try:
            scheduled_time = datetime.fromisoformat(scheduled_time_str)
            if scheduled_time.tzinfo is None:
                scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError) as e:
            return SkillResult(
                success=False,
                error=f"Invalid scheduled_time format. Use ISO 8601 (e.g. 2026-03-15T10:00:00Z): {e}",
            )

        # Store the scheduled post in the database
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    text(
                        """INSERT INTO scheduled_posts
                           (platform, content, scheduled_time, status, created_at)
                           VALUES (:platform, :content, :scheduled_time, :status, :created_at)"""
                    ),
                    {
                        "platform": platform,
                        "content": content,
                        "scheduled_time": scheduled_time,
                        "status": "scheduled",
                        "created_at": datetime.now(timezone.utc),
                    },
                )
                await session.commit()
        except Exception as e:
            logger.error(f"[SocialMedia] Failed to store scheduled post: {e}")
            return SkillResult(success=False, error=f"Failed to schedule post: {e}")

        return SkillResult(
            success=True,
            output=(
                f"Post scheduled for {platform} at {scheduled_time.isoformat()}.\n"
                f"Content: {content[:100]}{'...' if len(content) > 100 else ''}"
            ),
            data={
                "platform": platform,
                "content": content,
                "scheduled_time": scheduled_time.isoformat(),
                "status": "scheduled",
            },
        )

    # ------------------------------------------------------------------
    # analytics_summary
    # ------------------------------------------------------------------
    async def _analytics_summary(self, args: dict, context: SkillContext) -> SkillResult:
        """Summarize engagement metrics from scheduled/published posts."""
        try:
            async with AsyncSessionLocal() as session:
                # Get post counts by platform and status
                result = await session.execute(
                    text(
                        """SELECT platform, status, COUNT(*) as count
                           FROM scheduled_posts
                           GROUP BY platform, status
                           ORDER BY platform, status"""
                    )
                )
                rows = result.mappings().all()

                # Get recent posts
                recent = await session.execute(
                    text(
                        """SELECT platform, content, scheduled_time, status, created_at
                           FROM scheduled_posts
                           ORDER BY created_at DESC
                           LIMIT 10"""
                    )
                )
                recent_rows = recent.mappings().all()

            if not rows and not recent_rows:
                return SkillResult(
                    success=True,
                    output="No social media posts found. Use 'create_content' and 'schedule_post' to get started.",
                    data={"total_posts": 0, "platforms": {}},
                )

            # Build summary
            platforms: Dict[str, Dict[str, int]] = {}
            total = 0
            for row in rows:
                p = row["platform"]
                s = row["status"]
                c = row["count"]
                if p not in platforms:
                    platforms[p] = {}
                platforms[p][s] = c
                total += c

            output_lines = [f"📊 Social Media Analytics Summary", f"Total posts: {total}", ""]
            for p, statuses in platforms.items():
                status_parts = ", ".join(f"{s}: {c}" for s, c in statuses.items())
                output_lines.append(f"  {p.title()}: {status_parts}")

            if recent_rows:
                output_lines.append("")
                output_lines.append("Recent posts:")
                for row in recent_rows[:5]:
                    content_preview = row["content"][:60] + ("..." if len(row["content"]) > 60 else "")
                    output_lines.append(
                        f"  - [{row['platform']}] {content_preview} ({row['status']})"
                    )

            return SkillResult(
                success=True,
                output="\n".join(output_lines),
                data={
                    "total_posts": total,
                    "platforms": platforms,
                    "recent_posts": [
                        {
                            "platform": r["platform"],
                            "content": r["content"][:200],
                            "scheduled_time": str(r["scheduled_time"]),
                            "status": r["status"],
                        }
                        for r in recent_rows
                    ],
                },
            )

        except Exception as e:
            logger.error(f"[SocialMedia] Analytics query failed: {e}")
            return SkillResult(success=False, error=f"Analytics query failed: {e}")


# Register entry point
handler = SocialMediaSkill

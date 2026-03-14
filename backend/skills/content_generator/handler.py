"""
Content Generator Skill — brand-aware content production.

Actions:
  - blog_post: Generate SEO-optimized blog post with title, introduction, body, conclusion.
  - social_copy: Generate social media copy batch for multiple platforms at once.
  - email_copy: Generate email marketing copy with subject line A/B variants.
  - brand_voice: Configure brand voice parameters (tone, vocabulary, style guide).
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, text

from core.skills.base import BaseSkill, SkillContext, SkillResult
from core.database import AsyncSessionLocal, SystemKnowledge

logger = logging.getLogger(__name__)

# Brand voice storage domain in system_knowledge
BRAND_VOICE_DOMAIN = "brand_voice"

# Default platforms for social_copy
ALL_SOCIAL_PLATFORMS = ["twitter", "linkedin", "facebook", "instagram"]

# Length configuration for blog posts (approximate word counts)
LENGTH_CONFIG = {
    "short": {"words": 500, "label": "~500 words"},
    "medium": {"words": 1000, "label": "~1000 words"},
    "long": {"words": 2000, "label": "~2000 words"},
}

# Platform-specific social copy constraints
SOCIAL_PLATFORM_CONFIG = {
    "twitter": {
        "max_chars": 280,
        "style": "concise, punchy, with hashtags",
        "guidance": "Under 280 characters including hashtags. Engaging, concise.",
    },
    "linkedin": {
        "max_chars": 3000,
        "style": "professional, thought-leadership",
        "guidance": "Professional tone. 150-300 words. Include a hook and call-to-action.",
    },
    "facebook": {
        "max_chars": 5000,
        "style": "casual, conversational, community-oriented",
        "guidance": "Conversational tone. 100-250 words. Encourage engagement and comments.",
    },
    "instagram": {
        "max_chars": 2200,
        "style": "visual, storytelling, with emojis and hashtags",
        "guidance": "Storytelling tone. 100-200 words. Include emojis and 5-10 hashtags at the end.",
    },
}


async def _load_brand_voice(brand_name: Optional[str] = None) -> Optional[Dict]:
    """Load brand voice configuration from system_knowledge.

    If brand_name is specified, looks for that brand; otherwise returns
    the default brand voice if one exists.
    """
    try:
        async with AsyncSessionLocal() as session:
            if brand_name:
                result = await session.execute(
                    select(SystemKnowledge).where(
                        SystemKnowledge.domain == BRAND_VOICE_DOMAIN,
                        SystemKnowledge.key == brand_name,
                    )
                )
            else:
                # Look for default brand voice
                result = await session.execute(
                    select(SystemKnowledge).where(
                        SystemKnowledge.domain == BRAND_VOICE_DOMAIN,
                    ).order_by(SystemKnowledge.updated_at.desc()).limit(1)
                )

            row = result.scalars().first()
            if row and row.value:
                try:
                    return json.loads(row.value)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(f"[ContentGen] Invalid brand voice JSON for '{row.key}'")
                    return None
    except Exception as e:
        logger.warning(f"[ContentGen] Failed to load brand voice: {e}")
    return None


def _build_brand_voice_context(voice: Optional[Dict]) -> str:
    """Build a prompt context section from brand voice parameters."""
    if not voice:
        return ""

    parts = []
    if voice.get("tone"):
        parts.append(f"Tone: {voice['tone']}")
    if voice.get("vocabulary"):
        parts.append(f"Vocabulary style: {voice['vocabulary']}")
    if voice.get("style_guide"):
        parts.append(f"Style guide: {voice['style_guide']}")
    if voice.get("values"):
        parts.append(f"Brand values: {voice['values']}")
    if voice.get("audience"):
        parts.append(f"Target audience: {voice['audience']}")

    if not parts:
        return ""

    return (
        "\n\nBrand Voice Guidelines (MUST follow):\n"
        + "\n".join(f"- {p}" for p in parts)
    )


class ContentGeneratorSkill(BaseSkill):
    """Brand-aware content generation skill."""

    name = "content_generator"
    description = (
        "Brand-aware content generation: SEO-optimized blog posts, social media "
        "copy batches, email marketing copy with A/B subject lines, and brand "
        "voice configuration for consistent identity."
    )
    version = "1.0.0"
    permissions = ["network"]
    tags = ["content", "marketing", "brand-voice", "blog", "social", "email", "seo"]

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action")

        if action == "blog_post":
            return await self._blog_post(args, context)
        elif action == "social_copy":
            return await self._social_copy(args, context)
        elif action == "email_copy":
            return await self._email_copy(args, context)
        elif action == "brand_voice":
            return await self._brand_voice(args, context)

        return SkillResult(
            success=False,
            error=(
                f"Unknown action: {action}. "
                "Valid actions: blog_post, social_copy, email_copy, brand_voice"
            ),
        )

    # ------------------------------------------------------------------
    # blog_post
    # ------------------------------------------------------------------
    async def _blog_post(self, args: dict, context: SkillContext) -> SkillResult:
        topic = args.get("topic")
        length = args.get("length", "medium")
        tone = args.get("tone")
        keywords = args.get("keywords", [])

        if not topic:
            return SkillResult(
                success=False,
                error="Parameter 'topic' is required for blog_post.",
            )

        if length not in LENGTH_CONFIG:
            return SkillResult(
                success=False,
                error=f"Invalid length: '{length}'. Must be one of: short, medium, long",
            )

        if not context.brain:
            return SkillResult(
                success=False,
                error="Brain engine not available for content generation.",
            )

        # Load brand voice
        brand_voice = await _load_brand_voice()
        brand_ctx = _build_brand_voice_context(brand_voice)

        # Override tone if explicitly provided
        tone_directive = ""
        if tone:
            tone_directive = f"\nTone: {tone}"
        elif brand_voice and brand_voice.get("tone"):
            tone_directive = f"\nTone: {brand_voice['tone']}"

        length_cfg = LENGTH_CONFIG[length]
        keywords_section = ""
        if keywords:
            keywords_section = (
                f"\nSEO Keywords (naturally incorporate these): "
                f"{', '.join(keywords)}"
            )

        prompt = (
            f"Write a comprehensive, SEO-optimized blog post about: {topic}\n\n"
            f"Target length: {length_cfg['label']} ({length_cfg['words']} words).\n"
            f"Structure the post with these clearly labeled sections:\n"
            f"1. TITLE: A compelling, SEO-friendly title\n"
            f"2. INTRODUCTION: A hook that draws readers in (2-3 paragraphs)\n"
            f"3. BODY: The main content with subheadings (use ## for subheadings)\n"
            f"4. CONCLUSION: Summary with call-to-action\n"
            f"{tone_directive}"
            f"{keywords_section}"
            f"{brand_ctx}\n\n"
            f"Output the full blog post with sections clearly marked."
        )

        try:
            generated = await context.brain.think(
                prompt,
                complexity="complex",
                channel="content_generator",
            )
        except Exception as e:
            logger.error(f"[ContentGen] Blog post generation failed: {e}")
            return SkillResult(
                success=False,
                error=f"Blog post generation failed: {e}",
            )

        if not generated:
            return SkillResult(
                success=False,
                error="LLM returned empty content.",
            )

        generated = generated.strip()

        # Parse sections from the generated content
        sections = self._parse_blog_sections(generated)

        return SkillResult(
            success=True,
            output=generated,
            data={
                "topic": topic,
                "length": length,
                "target_words": length_cfg["words"],
                "actual_words": len(generated.split()),
                "title": sections.get("title", ""),
                "introduction": sections.get("introduction", ""),
                "body": sections.get("body", ""),
                "conclusion": sections.get("conclusion", ""),
                "keywords": keywords,
                "brand_voice_applied": brand_voice is not None,
            },
        )

    def _parse_blog_sections(self, content: str) -> Dict[str, str]:
        """Parse blog post content into sections by looking for labels."""
        sections: Dict[str, str] = {
            "title": "",
            "introduction": "",
            "body": "",
            "conclusion": "",
        }

        lines = content.split("\n")
        current_section = "title"
        section_content: Dict[str, List[str]] = {
            "title": [],
            "introduction": [],
            "body": [],
            "conclusion": [],
        }

        for line in lines:
            lower = line.lower().strip()

            if lower.startswith("title:") or lower.startswith("# "):
                current_section = "title"
                # Extract title text after prefix
                title_text = line.split(":", 1)[-1].strip() if ":" in line else line.lstrip("# ").strip()
                if title_text:
                    section_content["title"].append(title_text)
                continue
            elif "introduction" in lower and (lower.startswith("##") or lower.startswith("introduction")):
                current_section = "introduction"
                continue
            elif "conclusion" in lower and (lower.startswith("##") or lower.startswith("conclusion")):
                current_section = "conclusion"
                continue
            elif (lower.startswith("## ") or lower.startswith("body")) and current_section in ("title", "introduction"):
                current_section = "body"
                if lower.startswith("body"):
                    continue

            section_content[current_section].append(line)

        for key in sections:
            sections[key] = "\n".join(section_content[key]).strip()

        # If no explicit sections found, put everything in body with first line as title
        if not sections["title"] and not sections["body"]:
            if lines:
                sections["title"] = lines[0].strip().lstrip("# ")
                sections["body"] = "\n".join(lines[1:]).strip()

        return sections

    # ------------------------------------------------------------------
    # social_copy
    # ------------------------------------------------------------------
    async def _social_copy(self, args: dict, context: SkillContext) -> SkillResult:
        topic = args.get("topic")
        platforms = args.get("platforms", ALL_SOCIAL_PLATFORMS)
        tone = args.get("tone")

        if not topic:
            return SkillResult(
                success=False,
                error="Parameter 'topic' is required for social_copy.",
            )

        if not context.brain:
            return SkillResult(
                success=False,
                error="Brain engine not available for content generation.",
            )

        # Validate platforms
        if not isinstance(platforms, list) or not platforms:
            platforms = ALL_SOCIAL_PLATFORMS

        invalid = [p for p in platforms if p not in SOCIAL_PLATFORM_CONFIG]
        if invalid:
            return SkillResult(
                success=False,
                error=(
                    f"Invalid platform(s): {', '.join(invalid)}. "
                    f"Supported: {', '.join(SOCIAL_PLATFORM_CONFIG.keys())}"
                ),
            )

        # Load brand voice
        brand_voice = await _load_brand_voice()
        brand_ctx = _build_brand_voice_context(brand_voice)

        tone_directive = ""
        if tone:
            tone_directive = f"\nOverall tone: {tone}"
        elif brand_voice and brand_voice.get("tone"):
            tone_directive = f"\nOverall tone: {brand_voice['tone']}"

        # Build multi-platform prompt
        platform_specs = []
        for p in platforms:
            cfg = SOCIAL_PLATFORM_CONFIG[p]
            platform_specs.append(
                f"- {p.upper()}: {cfg['guidance']} Max {cfg['max_chars']} chars."
            )

        prompt = (
            f"Generate social media copy for the following topic across multiple platforms.\n"
            f"Topic: {topic}\n\n"
            f"Create one post for EACH of these platforms:\n"
            f"{chr(10).join(platform_specs)}\n"
            f"{tone_directive}"
            f"{brand_ctx}\n\n"
            f"Format your response as follows (use exact labels):\n"
            + "\n".join(f"[{p.upper()}]\n<post content here>\n" for p in platforms)
            + "\nOnly output the posts with their platform labels. No other commentary."
        )

        try:
            generated = await context.brain.think(
                prompt,
                complexity="fast",
                channel="content_generator",
            )
        except Exception as e:
            logger.error(f"[ContentGen] Social copy generation failed: {e}")
            return SkillResult(
                success=False,
                error=f"Social copy generation failed: {e}",
            )

        if not generated:
            return SkillResult(
                success=False,
                error="LLM returned empty content.",
            )

        generated = generated.strip()

        # Parse platform-specific content
        platform_content = self._parse_social_platforms(generated, platforms)

        # Build output summary
        output_lines = [f"📱 Social Media Copy — {topic}", ""]
        for p in platforms:
            content = platform_content.get(p, "")
            char_count = len(content)
            max_chars = SOCIAL_PLATFORM_CONFIG[p]["max_chars"]
            status = "✅" if char_count <= max_chars else "⚠️ Over limit"
            output_lines.append(f"[{p.upper()}] ({char_count}/{max_chars} chars) {status}")
            output_lines.append(content)
            output_lines.append("")

        return SkillResult(
            success=True,
            output="\n".join(output_lines),
            data={
                "topic": topic,
                "platforms": platforms,
                "content": platform_content,
                "platform_details": {
                    p: {
                        "content": platform_content.get(p, ""),
                        "character_count": len(platform_content.get(p, "")),
                        "max_chars": SOCIAL_PLATFORM_CONFIG[p]["max_chars"],
                        "within_limit": len(platform_content.get(p, "")) <= SOCIAL_PLATFORM_CONFIG[p]["max_chars"],
                    }
                    for p in platforms
                },
                "brand_voice_applied": brand_voice is not None,
            },
        )

    def _parse_social_platforms(
        self, content: str, platforms: List[str]
    ) -> Dict[str, str]:
        """Parse LLM output into platform-keyed dictionary."""
        result: Dict[str, str] = {}
        current_platform: Optional[str] = None
        current_lines: List[str] = []

        for line in content.split("\n"):
            stripped = line.strip()
            # Check if this line is a platform header
            matched_platform = None
            for p in platforms:
                if stripped.upper().startswith(f"[{p.upper()}]"):
                    matched_platform = p
                    break

            if matched_platform is not None:
                # Save previous platform's content
                if current_platform is not None:
                    result[current_platform] = "\n".join(current_lines).strip()
                current_platform = matched_platform
                current_lines = []
                # Check if there's content after the label on the same line
                after_label = stripped[len(f"[{matched_platform.upper()}]"):].strip()
                if after_label:
                    current_lines.append(after_label)
            elif current_platform is not None:
                current_lines.append(line)

        # Save the last platform
        if current_platform is not None:
            result[current_platform] = "\n".join(current_lines).strip()

        return result

    # ------------------------------------------------------------------
    # email_copy
    # ------------------------------------------------------------------
    async def _email_copy(self, args: dict, context: SkillContext) -> SkillResult:
        topic = args.get("topic")
        tone = args.get("tone")
        subject_variants = args.get("subject_variants", 3)

        if not topic:
            return SkillResult(
                success=False,
                error="Parameter 'topic' is required for email_copy.",
            )

        if not context.brain:
            return SkillResult(
                success=False,
                error="Brain engine not available for content generation.",
            )

        # Clamp subject variants
        try:
            subject_variants = int(subject_variants)
        except (ValueError, TypeError):
            subject_variants = 3
        subject_variants = max(1, min(subject_variants, 5))

        # Load brand voice
        brand_voice = await _load_brand_voice()
        brand_ctx = _build_brand_voice_context(brand_voice)

        tone_directive = ""
        if tone:
            tone_directive = f"\nTone: {tone}"
        elif brand_voice and brand_voice.get("tone"):
            tone_directive = f"\nTone: {brand_voice['tone']}"

        prompt = (
            f"Generate email marketing copy for the following topic.\n"
            f"Topic: {topic}\n\n"
            f"Provide:\n"
            f"1. SUBJECT LINES: Generate exactly {subject_variants} A/B test subject line variants. "
            f"Label them SUBJECT_1, SUBJECT_2, etc. Each on its own line.\n"
            f"2. EMAIL BODY: Write the email body text. Use {{{{name}}}} placeholder for "
            f"recipient name. Include a clear call-to-action.\n"
            f"{tone_directive}"
            f"{brand_ctx}\n\n"
            f"Format:\n"
            f"SUBJECT_1: <subject line 1>\n"
            f"SUBJECT_2: <subject line 2>\n"
            + (f"SUBJECT_3: <subject line 3>\n" if subject_variants >= 3 else "")
            + (f"SUBJECT_4: <subject line 4>\n" if subject_variants >= 4 else "")
            + (f"SUBJECT_5: <subject line 5>\n" if subject_variants >= 5 else "")
            + f"\nEMAIL_BODY:\n<email body text>\n\n"
            f"Only output the formatted content, no other commentary."
        )

        try:
            generated = await context.brain.think(
                prompt,
                complexity="fast",
                channel="content_generator",
            )
        except Exception as e:
            logger.error(f"[ContentGen] Email copy generation failed: {e}")
            return SkillResult(
                success=False,
                error=f"Email copy generation failed: {e}",
            )

        if not generated:
            return SkillResult(
                success=False,
                error="LLM returned empty content.",
            )

        generated = generated.strip()

        # Parse subject lines and body
        subjects, body = self._parse_email_content(generated, subject_variants)

        # Build output
        output_lines = [f"📧 Email Marketing Copy — {topic}", ""]
        output_lines.append("Subject Line Variants:")
        for i, subj in enumerate(subjects, 1):
            output_lines.append(f"  {i}. {subj}")
        output_lines.append("")
        output_lines.append("Email Body:")
        output_lines.append(body)

        return SkillResult(
            success=True,
            output="\n".join(output_lines),
            data={
                "topic": topic,
                "subject_lines": subjects,
                "body": body,
                "subject_variant_count": len(subjects),
                "brand_voice_applied": brand_voice is not None,
            },
        )

    def _parse_email_content(
        self, content: str, expected_variants: int
    ) -> tuple[List[str], str]:
        """Parse email content into subject lines and body."""
        subjects: List[str] = []
        body_lines: List[str] = []
        in_body = False

        for line in content.split("\n"):
            stripped = line.strip()
            upper = stripped.upper()

            # Check for subject lines
            if upper.startswith("SUBJECT_") and ":" in stripped:
                subject_text = stripped.split(":", 1)[1].strip()
                if subject_text:
                    subjects.append(subject_text)
                continue

            # Check for body section marker
            if upper.startswith("EMAIL_BODY") or upper.startswith("EMAIL BODY"):
                in_body = True
                # Check for content after the colon
                if ":" in stripped:
                    after = stripped.split(":", 1)[1].strip()
                    if after:
                        body_lines.append(after)
                continue

            if in_body:
                body_lines.append(line)

        body = "\n".join(body_lines).strip()

        # Fallback: if no structured parsing worked, split content
        if not subjects and not body:
            lines = content.split("\n")
            # Try to find any subject-like lines at the top
            for line in lines:
                stripped = line.strip()
                if stripped and not subjects and len(stripped) < 150:
                    subjects.append(stripped)
                    if len(subjects) >= expected_variants:
                        break
            body = content

        return subjects, body

    # ------------------------------------------------------------------
    # brand_voice
    # ------------------------------------------------------------------
    async def _brand_voice(self, args: dict, context: SkillContext) -> SkillResult:
        brand_name = args.get("brand_name")
        voice_params = args.get("voice_params")

        if not brand_name:
            return SkillResult(
                success=False,
                error="Parameter 'brand_name' is required for brand_voice.",
            )

        if not voice_params:
            return SkillResult(
                success=False,
                error="Parameter 'voice_params' is required for brand_voice.",
            )

        if not isinstance(voice_params, dict):
            return SkillResult(
                success=False,
                error="Parameter 'voice_params' must be an object with keys: tone, vocabulary, style_guide, values, audience.",
            )

        # Validate that at least one voice parameter is provided
        valid_keys = {"tone", "vocabulary", "style_guide", "values", "audience"}
        provided_keys = set(voice_params.keys()) & valid_keys
        if not provided_keys:
            return SkillResult(
                success=False,
                error=(
                    "voice_params must include at least one of: "
                    "tone, vocabulary, style_guide, values, audience"
                ),
            )

        # Store in system_knowledge
        voice_data = {
            "brand_name": brand_name,
            "tone": voice_params.get("tone", ""),
            "vocabulary": voice_params.get("vocabulary", ""),
            "style_guide": voice_params.get("style_guide", ""),
            "values": voice_params.get("values", ""),
            "audience": voice_params.get("audience", ""),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            await SystemKnowledge.upsert(
                domain=BRAND_VOICE_DOMAIN,
                key=brand_name,
                value=json.dumps(voice_data),
                value_type="json",
                source="content_generator",
            )
        except Exception as e:
            logger.error(f"[ContentGen] Failed to store brand voice: {e}")
            return SkillResult(
                success=False,
                error=f"Failed to store brand voice: {e}",
            )

        # Build readable summary
        summary_parts = []
        for key in ["tone", "vocabulary", "style_guide", "values", "audience"]:
            val = voice_params.get(key)
            if val:
                summary_parts.append(f"  {key}: {val}")

        return SkillResult(
            success=True,
            output=(
                f"🎨 Brand voice configured for '{brand_name}':\n"
                + "\n".join(summary_parts)
                + "\n\nBrand voice will be applied to all future content generation."
            ),
            data={
                "brand_name": brand_name,
                "voice_params": voice_data,
                "stored_in": "system_knowledge",
                "domain": BRAND_VOICE_DOMAIN,
            },
        )


# Register entry point
handler = ContentGeneratorSkill

"""
Email Marketing Skill — campaign creation, audience segmentation, and email delivery.

Actions:
  - create_campaign: Create a new email campaign with subject, body template, and segment.
  - send_campaign: Queue campaign emails for async delivery via existing SMTP config.
  - list_campaigns: List campaigns filtered by status (draft/sending/sent/failed).
  - audience_segment: Define reusable audience segments by criteria.
"""

import logging
import re
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

from sqlalchemy import select, text, desc

from core.skills.base import BaseSkill, SkillContext, SkillResult
from core.database import AsyncSessionLocal, EmailCampaign, AudienceSegment

logger = logging.getLogger(__name__)

# Template variable pattern: {{variable_name}}
TEMPLATE_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def render_template(template: str, variables: dict) -> str:
    """Render template by replacing {{var}} placeholders with values.

    Unknown variables are left as-is (e.g. {{unknown}} stays in output).
    """
    def _replace(match):
        key = match.group(1)
        return str(variables.get(key, match.group(0)))

    return TEMPLATE_VAR_PATTERN.sub(_replace, template)


class EmailMarketingSkill(BaseSkill):
    """Email marketing campaign management skill."""

    name = "email_marketing"
    description = (
        "Email marketing campaign management: create campaigns with subject and "
        "body template, queue emails for SMTP delivery, list campaigns, and "
        "define reusable audience segments."
    )
    version = "1.0.0"
    permissions = ["network"]
    tags = ["email", "marketing", "campaigns", "newsletters", "audience"]

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action")

        if action == "create_campaign":
            return await self._create_campaign(args, context)
        elif action == "send_campaign":
            return await self._send_campaign(args, context)
        elif action == "list_campaigns":
            return await self._list_campaigns(args, context)
        elif action == "audience_segment":
            return await self._audience_segment(args, context)

        return SkillResult(
            success=False,
            error=f"Unknown action: {action}. Valid actions: create_campaign, send_campaign, list_campaigns, audience_segment",
        )

    # ------------------------------------------------------------------
    # create_campaign
    # ------------------------------------------------------------------
    async def _create_campaign(self, args: dict, context: SkillContext) -> SkillResult:
        name = args.get("name")
        subject = args.get("subject")
        body_template = args.get("body_template")
        topic = args.get("topic")
        segment_name = args.get("segment")

        if not name:
            return SkillResult(success=False, error="Parameter 'name' is required for create_campaign.")

        if not subject:
            return SkillResult(success=False, error="Parameter 'subject' is required for create_campaign.")

        # If no body_template but topic is provided, use LLM to generate email copy
        if not body_template:
            if topic:
                if not context.brain:
                    return SkillResult(
                        success=False,
                        error="Brain engine not available for email copy generation.",
                    )
                try:
                    prompt = (
                        "Write a professional marketing email body for the following topic. "
                        "Use template variables {{name}} for recipient name and {{company}} "
                        "for company name where appropriate. Keep it concise, engaging, and "
                        "include a clear call to action. Do NOT include the subject line. "
                        "Only output the email body text.\n\n"
                        f"Topic: {topic}\n"
                        f"Subject line: {subject}"
                    )
                    body_template = await context.brain.think(
                        prompt,
                        complexity="fast",
                        channel="email_marketing",
                    )
                    if not body_template:
                        return SkillResult(success=False, error="LLM returned empty email copy.")
                    body_template = body_template.strip()
                except Exception as e:
                    logger.error(f"[EmailMarketing] LLM generation failed: {e}")
                    return SkillResult(success=False, error=f"Email copy generation failed: {e}")
            else:
                return SkillResult(
                    success=False,
                    error="Either 'body_template' or 'topic' is required for create_campaign.",
                )

        # Resolve segment ID if provided
        segment_id = None
        if segment_name:
            try:
                async with AsyncSessionLocal() as session:
                    result = await session.execute(
                        select(AudienceSegment).where(AudienceSegment.name == segment_name)
                    )
                    segment = result.scalars().first()
                    if segment:
                        segment_id = segment.id
                    else:
                        return SkillResult(
                            success=False,
                            error=f"Audience segment '{segment_name}' not found. Create it first with audience_segment action.",
                        )
            except Exception as e:
                logger.error(f"[EmailMarketing] Segment lookup failed: {e}")
                return SkillResult(success=False, error=f"Segment lookup failed: {e}")

        # Store campaign in database
        try:
            async with AsyncSessionLocal() as session:
                campaign = EmailCampaign(
                    name=name,
                    subject=subject,
                    body_template=body_template,
                    segment_id=segment_id,
                    status="draft",
                )
                session.add(campaign)
                await session.commit()
                await session.refresh(campaign)
                campaign_id = campaign.id
        except Exception as e:
            logger.error(f"[EmailMarketing] Failed to create campaign: {e}")
            return SkillResult(success=False, error=f"Failed to create campaign: {e}")

        # Detect template variables
        variables = TEMPLATE_VAR_PATTERN.findall(body_template)

        return SkillResult(
            success=True,
            output=(
                f"Campaign '{name}' created successfully (ID: {campaign_id}).\n"
                f"Subject: {subject}\n"
                f"Status: draft\n"
                f"Segment: {segment_name or 'none'}\n"
                f"Template variables: {', '.join(variables) if variables else 'none'}"
            ),
            data={
                "campaign_id": campaign_id,
                "name": name,
                "subject": subject,
                "body_template": body_template,
                "segment": segment_name,
                "segment_id": segment_id,
                "status": "draft",
                "template_variables": variables,
            },
        )

    # ------------------------------------------------------------------
    # send_campaign
    # ------------------------------------------------------------------
    async def _send_campaign(self, args: dict, context: SkillContext) -> SkillResult:
        campaign_id = args.get("campaign_id")

        if not campaign_id:
            return SkillResult(success=False, error="Parameter 'campaign_id' is required for send_campaign.")

        try:
            campaign_id = int(campaign_id)
        except (ValueError, TypeError):
            return SkillResult(success=False, error="Parameter 'campaign_id' must be an integer.")

        # Fetch campaign from database
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(EmailCampaign).where(EmailCampaign.id == campaign_id)
                )
                campaign = result.scalars().first()

                if not campaign:
                    return SkillResult(
                        success=False,
                        error=f"Campaign with ID {campaign_id} not found.",
                    )

                if campaign.status == "sent":
                    return SkillResult(
                        success=False,
                        error=f"Campaign '{campaign.name}' has already been sent.",
                    )

                if campaign.status == "sending":
                    return SkillResult(
                        success=False,
                        error=f"Campaign '{campaign.name}' is already being sent.",
                    )

                # Queue via Celery for async delivery
                campaign.status = "sending"
                await session.commit()
        except Exception as e:
            logger.error(f"[EmailMarketing] Failed to fetch campaign: {e}")
            return SkillResult(success=False, error=f"Failed to fetch campaign: {e}")

        # Queue the send task via Celery
        try:
            from core.tasks import send_email_campaign
            send_email_campaign.delay(campaign_id)
        except Exception as e:
            logger.warning(f"[EmailMarketing] Celery task queue failed: {e}. Will attempt inline send.")
            # Fallback: attempt direct send if Celery is not available
            try:
                await self._deliver_campaign(campaign_id)
            except Exception as send_err:
                logger.error(f"[EmailMarketing] Inline send also failed: {send_err}")
                # Revert status
                try:
                    async with AsyncSessionLocal() as session:
                        result = await session.execute(
                            select(EmailCampaign).where(EmailCampaign.id == campaign_id)
                        )
                        c = result.scalars().first()
                        if c:
                            c.status = "failed"
                            await session.commit()
                except Exception:
                    pass
                return SkillResult(
                    success=False,
                    error=f"Failed to queue campaign for delivery: {e}",
                )

        return SkillResult(
            success=True,
            output=f"Campaign (ID: {campaign_id}) queued for delivery via SMTP.",
            data={
                "campaign_id": campaign_id,
                "status": "sending",
                "delivery_method": "celery_async",
            },
        )

    async def _deliver_campaign(self, campaign_id: int):
        """Deliver a campaign's emails via SMTP. Called by Celery task or inline fallback."""
        from core.config import get_settings

        settings = get_settings()

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(EmailCampaign).where(EmailCampaign.id == campaign_id)
            )
            campaign = result.scalars().first()
            if not campaign:
                logger.error(f"[EmailMarketing] Campaign {campaign_id} not found for delivery")
                return

            # For now, send to configured alert recipients as the recipient list.
            # In a full implementation, recipients would come from the segment.
            recipients = settings.alert_recipient_list
            if not recipients:
                logger.warning("[EmailMarketing] No recipients configured (ALERT_RECIPIENTS empty)")
                campaign.status = "failed"
                await session.commit()
                return

            smtp_host = settings.smtp_host
            smtp_port = settings.smtp_port
            smtp_user = settings.smtp_user
            smtp_pass = settings.smtp_pass
            from_addr = settings.smtp_from

            if not smtp_host:
                logger.error("[EmailMarketing] SMTP_HOST not configured")
                campaign.status = "failed"
                await session.commit()
                return

            sent_count = 0
            failed_count = 0

            for recipient in recipients:
                recipient = recipient.strip()
                if not recipient:
                    continue

                # Render template with available variables
                variables = {
                    "name": recipient.split("@")[0],
                    "company": "Sanaa",
                    "email": recipient,
                }
                body = render_template(campaign.body_template, variables)
                subject = render_template(campaign.subject, variables)

                try:
                    msg = MIMEMultipart("alternative")
                    msg["Subject"] = subject
                    msg["From"] = from_addr
                    msg["To"] = recipient

                    # Plain text version
                    msg.attach(MIMEText(body, "plain"))

                    # HTML version with Sanaa branding
                    html_body = f"""
                    <html>
                    <body style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 20px; background: #f5f5f5; color: #333;">
                        <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; padding: 24px; border: 1px solid #e0e0e0;">
                            <div style="margin-bottom: 16px;">
                                <h2 style="margin: 0; color: #6366f1;">{subject}</h2>
                            </div>
                            <div style="padding: 16px 0; line-height: 1.6;">
                                {body.replace(chr(10), '<br>')}
                            </div>
                            <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 20px 0;">
                            <p style="color: #999; font-size: 12px;">
                                Sent by Sanaa AI Marketing
                            </p>
                        </div>
                    </body>
                    </html>
                    """
                    msg.attach(MIMEText(html_body, "html"))

                    with smtplib.SMTP(smtp_host, smtp_port) as server:
                        server.starttls()
                        server.login(smtp_user, smtp_pass)
                        server.sendmail(from_addr, [recipient], msg.as_string())

                    sent_count += 1
                except Exception as e:
                    logger.error(f"[EmailMarketing] Failed to send to {recipient}: {e}")
                    failed_count += 1

            # Update campaign status
            campaign.sent_count = sent_count
            campaign.failed_count = failed_count
            campaign.recipients_count = sent_count + failed_count
            campaign.sent_at = datetime.now(timezone.utc)
            campaign.status = "sent" if failed_count == 0 else ("failed" if sent_count == 0 else "sent")
            await session.commit()

            logger.info(
                f"[EmailMarketing] Campaign {campaign_id} delivered: "
                f"{sent_count} sent, {failed_count} failed"
            )

    # ------------------------------------------------------------------
    # list_campaigns
    # ------------------------------------------------------------------
    async def _list_campaigns(self, args: dict, context: SkillContext) -> SkillResult:
        status_filter = args.get("status_filter", "all")

        try:
            async with AsyncSessionLocal() as session:
                query = select(EmailCampaign).order_by(desc(EmailCampaign.created_at))

                if status_filter and status_filter != "all":
                    query = query.where(EmailCampaign.status == status_filter)

                result = await session.execute(query.limit(50))
                campaigns = result.scalars().all()

            if not campaigns:
                return SkillResult(
                    success=True,
                    output=f"No campaigns found{' with status ' + status_filter if status_filter != 'all' else ''}.",
                    data={"campaigns": [], "total": 0},
                )

            # Format output
            output_lines = [f"📧 Email Campaigns ({len(campaigns)} found):"]
            campaign_data = []
            for c in campaigns:
                output_lines.append(
                    f"  [{c.id}] {c.name} — {c.status} "
                    f"(sent: {c.sent_count}/{c.recipients_count}, "
                    f"created: {c.created_at.strftime('%Y-%m-%d') if c.created_at else 'N/A'})"
                )
                campaign_data.append({
                    "id": c.id,
                    "name": c.name,
                    "subject": c.subject,
                    "status": c.status,
                    "recipients_count": c.recipients_count,
                    "sent_count": c.sent_count,
                    "failed_count": c.failed_count,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "sent_at": c.sent_at.isoformat() if c.sent_at else None,
                })

            return SkillResult(
                success=True,
                output="\n".join(output_lines),
                data={"campaigns": campaign_data, "total": len(campaigns)},
            )

        except Exception as e:
            logger.error(f"[EmailMarketing] Failed to list campaigns: {e}")
            return SkillResult(success=False, error=f"Failed to list campaigns: {e}")

    # ------------------------------------------------------------------
    # audience_segment
    # ------------------------------------------------------------------
    async def _audience_segment(self, args: dict, context: SkillContext) -> SkillResult:
        name = args.get("name")
        criteria = args.get("criteria")
        description = args.get("description", "")

        if not name:
            return SkillResult(success=False, error="Parameter 'name' is required for audience_segment.")

        if not criteria:
            return SkillResult(success=False, error="Parameter 'criteria' is required for audience_segment.")

        if not isinstance(criteria, dict):
            return SkillResult(
                success=False,
                error="Parameter 'criteria' must be an object/dict with key-value filters.",
            )

        try:
            async with AsyncSessionLocal() as session:
                # Check if segment already exists
                result = await session.execute(
                    select(AudienceSegment).where(AudienceSegment.name == name)
                )
                existing = result.scalars().first()

                if existing:
                    # Update existing segment
                    existing.criteria = criteria
                    existing.description = description or existing.description
                    existing.updated_at = datetime.now(timezone.utc)
                    await session.commit()
                    await session.refresh(existing)
                    segment_id = existing.id
                    action_taken = "updated"
                else:
                    # Create new segment
                    segment = AudienceSegment(
                        name=name,
                        description=description,
                        criteria=criteria,
                    )
                    session.add(segment)
                    await session.commit()
                    await session.refresh(segment)
                    segment_id = segment.id
                    action_taken = "created"

        except Exception as e:
            logger.error(f"[EmailMarketing] Failed to save audience segment: {e}")
            return SkillResult(success=False, error=f"Failed to save audience segment: {e}")

        criteria_summary = ", ".join(f"{k}={v}" for k, v in criteria.items())

        return SkillResult(
            success=True,
            output=(
                f"Audience segment '{name}' {action_taken} (ID: {segment_id}).\n"
                f"Criteria: {criteria_summary}\n"
                f"Description: {description or 'N/A'}"
            ),
            data={
                "segment_id": segment_id,
                "name": name,
                "criteria": criteria,
                "description": description,
                "action": action_taken,
            },
        )


# Register entry point
handler = EmailMarketingSkill

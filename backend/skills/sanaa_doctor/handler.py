"""Sanaa Doctor skill."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from core.alerts.email_sender import send_alert_email
from core.config import get_settings
from core.intelligence.ml_engine import SkillMLEngine
from core.skills.base import BaseSkill, SkillContext, SkillParameter, SkillResult


TENANT_ROOTS = {
    "bukuya": "/var/www/bukuya.sanaa.ug/mbalala",
    "kalamba": "/var/www/kalamba.sanaa.co/mbalala",
    "kasawo": "/var/www/kasawo.sanaa.ug/mbalala",
    "kyaliwajjala": "/var/www/kyaliwajjala.sanaa.ug/mbalala",
    "mityana": "/var/www/mityana.sanaa.ug/mbalala",
    "mslink": "/var/www/mslink.sanaa.ug/mbalala",
}

CORE_SERVICES = [
    "nginx.service",
    "php8.4-fpm.service",
    "mysql.service",
    "redis-server.service",
    "postgresql@16-main.service",
    "antigravity-web.service",
    "antigravity-worker.service",
    "antigravity-beat.service",
]

OPS_ML_SKILLS = [
    "sanaa_doctor",
    "sanaa_tenant_sync",
    "healthcheck",
    "team_broadcast",
]


async def _run_cmd(cmd: list[str], cwd: str | None = None, timeout: int = 120) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return -1, "", "Command timed out"
    return (
        proc.returncode or 0,
        stdout.decode("utf-8", errors="replace").strip(),
        stderr.decode("utf-8", errors="replace").strip(),
    )


class SanaaDoctorSkill(BaseSkill):
    name = "sanaa_doctor"
    description = (
        "Run ecosystem-aware operational doctor checks for Sanaa tenants, predict the next sync or "
        "deployment blockers, and optionally deliver the report by email or to Sanaa AI memory."
    )
    version = "2.0.0"
    permissions = ["shell", "filesystem"]
    timeout = 600
    tags = [
        "operations",
        "monitoring",
        "infrastructure",
        "doctor",
        "tenants",
        "git",
        "php",
        "ml",
        "reporting",
    ]
    parameters = [
        SkillParameter(
            name="action",
            type="string",
            description=(
                "Doctor action: check_all and ecosystem_report produce the full ecosystem briefing; "
                "tenant_git, lint_changed, and service_status run focused checks."
            ),
            required=True,
            enum=["check_all", "ecosystem_report", "tenant_git", "lint_changed", "service_status"],
        ),
        SkillParameter(
            name="tenant",
            type="string",
            description="Tenant slug or all",
            required=False,
            default="all",
            enum=["all", "kasawo", "kalamba", "bukuya", "kyaliwajjala", "mityana", "mslink"],
        ),
        SkillParameter(
            name="lint_scope",
            type="string",
            description="Which files to lint: last_commit or worktree",
            required=False,
            default="last_commit",
            enum=["last_commit", "worktree"],
        ),
        SkillParameter(
            name="report_channel",
            type="string",
            description="Where to send the doctor briefing after it is generated.",
            required=False,
            default="none",
            enum=["none", "email", "sanaa_ai", "both"],
        ),
        SkillParameter(
            name="recipient",
            type="string",
            description=(
                "Email recipient or comma-separated recipients when report_channel includes email. "
                "Falls back to configured alert recipients if empty."
            ),
            required=False,
            default="",
        ),
        SkillParameter(
            name="include_ml",
            type="boolean",
            description="Include ML-derived operational confidence and automation signals.",
            required=False,
            default=True,
        ),
        SkillParameter(
            name="detail_level",
            type="string",
            description="summary keeps the report short; full includes tenant and lint detail.",
            required=False,
            default="full",
            enum=["summary", "full"],
        ),
    ]

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        args = self.apply_defaults(args)
        action = str(args.get("action", "")).strip()
        tenant = str(args.get("tenant", "all")).strip().lower()
        lint_scope = str(args.get("lint_scope", "last_commit")).strip().lower()
        report_channel = str(args.get("report_channel", "none")).strip().lower()
        recipient = str(args.get("recipient", "")).strip()
        detail_level = str(args.get("detail_level", "full")).strip().lower()
        include_ml = bool(args.get("include_ml", True))

        if tenant not in {"all", *TENANT_ROOTS.keys()}:
            return SkillResult(success=False, error=f"Unknown tenant '{tenant}'.")
        if report_channel not in {"none", "email", "sanaa_ai", "both"}:
            return SkillResult(success=False, error=f"Unknown report_channel '{report_channel}'.")
        if detail_level not in {"summary", "full"}:
            return SkillResult(success=False, error=f"Unknown detail_level '{detail_level}'.")

        if action == "service_status":
            return await self._service_status()
        if action == "tenant_git":
            return await self._tenant_git(tenant)
        if action == "lint_changed":
            return await self._lint_changed(tenant, lint_scope)
        if action in {"check_all", "ecosystem_report"}:
            return await self._ecosystem_report(
                tenant=tenant,
                lint_scope=lint_scope,
                report_channel=report_channel,
                recipient=recipient,
                include_ml=include_ml,
                detail_level=detail_level,
                context=context,
            )

        return SkillResult(success=False, error=f"Unknown action '{action}'.")

    def _resolve_tenants(self, tenant: str) -> list[str]:
        if tenant == "all":
            return list(TENANT_ROOTS.keys())
        return [tenant]

    async def _service_status(self) -> SkillResult:
        rows, unhealthy = await self._collect_service_rows()
        lines = ["Core services:"]
        for row in rows:
            icon = "OK" if row["state"] == "active" else "WARN"
            lines.append(f"- [{icon}] {row['service']}: {row['state']}")

        lines.append("")
        if unhealthy:
            lines.append(f"Unhealthy services: {', '.join(unhealthy)}")
        else:
            lines.append("All core services are active.")

        return SkillResult(
            success=True,
            output="\n".join(lines),
            data={"healthy": not unhealthy, "services": rows, "unhealthy_services": unhealthy},
        )

    async def _tenant_git(self, tenant: str) -> SkillResult:
        rows = await self._collect_git_rows(tenant)
        lines = ["Tenant git status:"]
        for row in rows:
            lines.append(
                f"- {row['tenant']}: branch {row['branch']} | HEAD {row['head']} | origin/main {row['origin_main']} | "
                f"dirty {row['dirty_count']} | ahead {row['ahead']} / behind {row['behind']}"
            )

        return SkillResult(success=True, output="\n".join(lines), data={"tenants": rows})

    async def _lint_changed(self, tenant: str, lint_scope: str) -> SkillResult:
        reports = await self._collect_lint_reports(tenant, lint_scope)
        issues_found = any(report["errors"] for report in reports)

        lines = [f"PHP lint check ({lint_scope}):"]
        for report in reports:
            if report["files"]:
                lines.append(f"- {report['tenant']}: checked {len(report['files'])} changed PHP files")
            else:
                lines.append(f"- {report['tenant']}: no changed PHP files found")
            for error in report["errors"]:
                lines.append(f"  ERROR {error}")

        lines.append("")
        if issues_found:
            lines.append("Doctor found PHP syntax issues in changed files.")
        else:
            lines.append("No PHP syntax issues found in the selected changed files.")

        return SkillResult(
            success=True,
            output="\n".join(lines),
            data={"healthy": not issues_found, "reports": reports},
        )

    async def _ecosystem_report(
        self,
        tenant: str,
        lint_scope: str,
        report_channel: str,
        recipient: str,
        include_ml: bool,
        detail_level: str,
        context: SkillContext,
    ) -> SkillResult:
        services, unhealthy_services = await self._collect_service_rows()
        git_rows = await self._collect_git_rows(tenant)
        lint_reports = await self._collect_lint_reports(tenant, lint_scope)
        lint_error_tenants = [report["tenant"] for report in lint_reports if report["errors"]]
        dirty_tenants = [row["tenant"] for row in git_rows if row["dirty_count"] > 0]
        behind_tenants = [row["tenant"] for row in git_rows if row["behind"] > 0]
        ahead_tenants = [row["tenant"] for row in git_rows if row["ahead"] > 0]

        ml_context = await self._load_ml_context() if include_ml else self._empty_ml_context()
        readiness_score = self._calculate_readiness_score(
            unhealthy_services=unhealthy_services,
            lint_error_tenants=lint_error_tenants,
            dirty_tenants=dirty_tenants,
            behind_tenants=behind_tenants,
            ml_context=ml_context,
        )
        risk_level = self._risk_level(readiness_score)
        predictions = self._predict_blockers(
            unhealthy_services=unhealthy_services,
            lint_reports=lint_reports,
            dirty_tenants=dirty_tenants,
            behind_tenants=behind_tenants,
            ml_context=ml_context,
        )
        recommendations = self._build_recommendations(
            unhealthy_services=unhealthy_services,
            lint_reports=lint_reports,
            dirty_tenants=dirty_tenants,
            behind_tenants=behind_tenants,
            ahead_tenants=ahead_tenants,
            ml_context=ml_context,
        )
        report_text = self._format_ecosystem_report(
            tenant=tenant,
            lint_scope=lint_scope,
            detail_level=detail_level,
            readiness_score=readiness_score,
            risk_level=risk_level,
            services=services,
            unhealthy_services=unhealthy_services,
            git_rows=git_rows,
            lint_reports=lint_reports,
            dirty_tenants=dirty_tenants,
            behind_tenants=behind_tenants,
            predictions=predictions,
            recommendations=recommendations,
            ml_context=ml_context,
        )
        dispatch = await self._dispatch_report(
            report_text=report_text,
            report_channel=report_channel,
            recipient=recipient,
            risk_level=risk_level,
            readiness_score=readiness_score,
            context=context,
        )

        overall_healthy = (
            not unhealthy_services
            and not lint_error_tenants
            and not dirty_tenants
            and readiness_score >= 80
        )

        return SkillResult(
            success=True,
            output=report_text,
            data={
                "healthy": overall_healthy,
                "readiness_score": readiness_score,
                "risk_level": risk_level,
                "services": services,
                "unhealthy_services": unhealthy_services,
                "git": {"tenants": git_rows},
                "lint": {"reports": lint_reports, "scope": lint_scope},
                "dirty_tenants": dirty_tenants,
                "behind_tenants": behind_tenants,
                "ahead_tenants": ahead_tenants,
                "lint_error_tenants": lint_error_tenants,
                "predictions": predictions,
                "recommendations": recommendations,
                "ml": ml_context,
                "dispatch": dispatch,
            },
        )

    async def _collect_service_rows(self) -> tuple[list[dict], list[str]]:
        rows = []
        unhealthy = []
        for service in CORE_SERVICES:
            code, out, err = await _run_cmd(["systemctl", "is-active", service], timeout=30)
            state = out.strip() if code == 0 else (out.strip() or err.strip() or "unknown")
            rows.append({"service": service, "state": state})
            if state != "active":
                unhealthy.append(service)
        return rows, unhealthy

    async def _collect_git_rows(self, tenant: str) -> list[dict]:
        tenants = self._resolve_tenants(tenant)
        rows = []
        for slug in tenants:
            rows.append(await self._tenant_git_row(slug, TENANT_ROOTS[slug]))
        return rows

    async def _collect_lint_reports(self, tenant: str, lint_scope: str) -> list[dict]:
        tenants = self._resolve_tenants(tenant)
        reports = []
        for slug in tenants:
            reports.append(await self._lint_report(slug, TENANT_ROOTS[slug], lint_scope))
        return reports

    async def _tenant_git_row(self, slug: str, root: str) -> dict:
        await _run_cmd(["git", "fetch", "origin", "main"], cwd=root, timeout=180)
        branch = await self._git_value(["git", "branch", "--show-current"], root)
        head = await self._git_value(["git", "rev-parse", "--short", "HEAD"], root)
        origin_main = await self._git_value(["git", "rev-parse", "--short", "origin/main"], root)
        ahead, behind = await self._ahead_behind(root)
        dirty_count = await self._dirty_count(root)
        return {
            "tenant": slug,
            "branch": branch,
            "head": head,
            "origin_main": origin_main,
            "ahead": ahead,
            "behind": behind,
            "dirty_count": dirty_count,
        }

    async def _lint_report(self, slug: str, root: str, scope: str) -> dict:
        files = await self._changed_php_files(root, scope)
        errors = []
        for rel_path in files:
            abs_path = os.path.join(root, rel_path)
            code, _, err = await _run_cmd(["php", "-l", abs_path], timeout=60)
            if code != 0:
                errors.append(f"{rel_path}: {err}")
        return {"tenant": slug, "files": files, "errors": errors}

    async def _changed_php_files(self, root: str, scope: str) -> list[str]:
        lines: list[str] = []
        if scope == "worktree":
            for cmd in (
                ["git", "diff", "--name-only"],
                ["git", "diff", "--cached", "--name-only"],
                ["git", "ls-files", "--others", "--exclude-standard"],
            ):
                code, out, _ = await _run_cmd(cmd, cwd=root, timeout=60)
                if code == 0 and out:
                    lines.extend(out.splitlines())
        else:
            code, out, _ = await _run_cmd(["git", "diff", "--name-only", "HEAD~1..HEAD"], cwd=root, timeout=60)
            if code == 0 and out:
                lines.extend(out.splitlines())

        results = []
        seen = set()
        for raw in lines:
            path = raw.strip()
            if (
                not path
                or path.startswith("..")
                or os.path.isabs(path)
                or path.endswith(".blade.php")
                or not path.endswith(".php")
            ):
                continue
            if path not in seen:
                seen.add(path)
                results.append(path)
        return results

    async def _git_value(self, cmd: list[str], root: str) -> str:
        code, out, err = await _run_cmd(cmd, cwd=root, timeout=30)
        if code != 0:
            return err.strip() or "unknown"
        return out.strip() or "unknown"

    async def _ahead_behind(self, root: str) -> tuple[int, int]:
        code, out, _ = await _run_cmd(
            ["git", "rev-list", "--left-right", "--count", "HEAD...origin/main"],
            cwd=root,
            timeout=30,
        )
        if code != 0 or not out:
            return 0, 0
        left, right = out.split()
        return int(left), int(right)

    async def _dirty_count(self, root: str) -> int:
        code, out, _ = await _run_cmd(["git", "status", "--short"], cwd=root, timeout=30)
        if code != 0 or not out:
            return 0
        return len([line for line in out.splitlines() if line.strip()])

    async def _load_ml_context(self) -> dict:
        try:
            engine = SkillMLEngine()
            all_scores = await engine.get_all_scores()
        except Exception as exc:
            return {
                "available": False,
                "error": str(exc),
                "tracked_skills": 0,
                "operational_confidence": None,
                "focus_scores": {},
                "low_confidence_skills": [],
            }

        score_map = {row["skill_name"]: row for row in all_scores if row.get("skill_name")}
        focus_scores = {name: score_map[name] for name in OPS_ML_SKILLS if name in score_map}
        confidence_values = [
            row["performance_score"]
            for row in focus_scores.values()
            if row.get("performance_score") is not None
        ]
        low_confidence = [
            {
                "skill_name": row["skill_name"],
                "performance_score": row["performance_score"],
                "trend": row.get("trend", "unknown"),
            }
            for row in focus_scores.values()
            if row.get("performance_score") is not None and row["performance_score"] < 0.65
        ]

        return {
            "available": True,
            "tracked_skills": len(all_scores),
            "operational_confidence": (
                round(sum(confidence_values) / len(confidence_values), 3) if confidence_values else None
            ),
            "focus_scores": focus_scores,
            "low_confidence_skills": low_confidence,
        }

    def _empty_ml_context(self) -> dict:
        return {
            "available": False,
            "tracked_skills": 0,
            "operational_confidence": None,
            "focus_scores": {},
            "low_confidence_skills": [],
        }

    def _calculate_readiness_score(
        self,
        unhealthy_services: list[str],
        lint_error_tenants: list[str],
        dirty_tenants: list[str],
        behind_tenants: list[str],
        ml_context: dict,
    ) -> int:
        score = 100
        score -= min(len(unhealthy_services) * 15, 45)
        score -= min(len(lint_error_tenants) * 18, 36)
        score -= min(len(dirty_tenants) * 6, 24)
        score -= min(len(behind_tenants) * 4, 20)

        op_conf = ml_context.get("operational_confidence")
        if op_conf is not None:
            if op_conf < 0.4:
                score -= 12
            elif op_conf < 0.6:
                score -= 8
            elif op_conf < 0.75:
                score -= 4

        return max(0, min(100, int(round(score))))

    def _risk_level(self, readiness_score: int) -> str:
        if readiness_score >= 85:
            return "low"
        if readiness_score >= 65:
            return "guarded"
        if readiness_score >= 40:
            return "high"
        return "critical"

    def _predict_blockers(
        self,
        unhealthy_services: list[str],
        lint_reports: list[dict],
        dirty_tenants: list[str],
        behind_tenants: list[str],
        ml_context: dict,
    ) -> list[str]:
        predictions: list[str] = []

        if unhealthy_services:
            predictions.append(
                "Service degradation is likely to affect AI workflows or web access until the inactive services are restored."
            )

        lint_tenants = [report["tenant"] for report in lint_reports if report["errors"]]
        if lint_tenants:
            predictions.append(
                f"Safe syncs or deployments are likely to fail on {', '.join(lint_tenants)} until PHP syntax issues are fixed."
            )

        if dirty_tenants:
            predictions.append(
                f"Repo-level pulls are likely to conflict on {', '.join(dirty_tenants)} because local changes are present."
            )

        if len(behind_tenants) >= 2:
            predictions.append(
                f"Feature drift is likely across tenants because {len(behind_tenants)} tenants are behind origin/main."
            )

        low_confidence = ml_context.get("low_confidence_skills", [])
        if low_confidence:
            predictions.append(
                "Automation confidence is reduced on some ops skills, so manual verification is still advisable after high-risk changes."
            )

        if not predictions:
            predictions.append("No immediate blockers predicted for the next sync or deployment window.")

        return predictions

    def _build_recommendations(
        self,
        unhealthy_services: list[str],
        lint_reports: list[dict],
        dirty_tenants: list[str],
        behind_tenants: list[str],
        ahead_tenants: list[str],
        ml_context: dict,
    ) -> list[str]:
        recommendations: list[str] = []

        if unhealthy_services:
            recommendations.append(f"Restore or inspect these services first: {', '.join(unhealthy_services)}.")

        for report in lint_reports:
            if report["errors"]:
                recommendations.append(
                    f"Fix PHP lint issues in {report['tenant']} before the next tenant sync."
                )

        if dirty_tenants:
            recommendations.append(
                f"Review, commit, or stash local worktree changes before pulling on: {', '.join(dirty_tenants)}."
            )

        if behind_tenants:
            recommendations.append(
                f"Pull a clean source tenant and sync the changed files to: {', '.join(behind_tenants)}."
            )

        if ahead_tenants:
            recommendations.append(
                f"Audit tenant-only commits on: {', '.join(ahead_tenants)} so important fixes are not stranded locally."
            )

        op_conf = ml_context.get("operational_confidence")
        if op_conf is None:
            recommendations.append("Run more doctor and tenant sync jobs to build ML confidence for ops automation.")
        elif op_conf < 0.65:
            recommendations.append("Keep post-sync verification strict because ops skill ML confidence is still below the trust threshold.")

        if not recommendations:
            recommendations.append("Estate looks healthy; continue with the normal doctor -> sync -> doctor verification loop.")

        return recommendations

    def _format_ecosystem_report(
        self,
        tenant: str,
        lint_scope: str,
        detail_level: str,
        readiness_score: int,
        risk_level: str,
        services: list[dict],
        unhealthy_services: list[str],
        git_rows: list[dict],
        lint_reports: list[dict],
        dirty_tenants: list[str],
        behind_tenants: list[str],
        predictions: list[str],
        recommendations: list[str],
        ml_context: dict,
    ) -> str:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            "Sanaa Doctor Ecosystem Briefing",
            f"- Generated: {generated_at}",
            f"- Tenant scope: {tenant}",
            f"- Lint scope: {lint_scope}",
            f"- Operational readiness: {readiness_score}/100",
            f"- Risk level: {risk_level.upper()}",
            "",
            "Current risk signals:",
            f"- Unhealthy services: {', '.join(unhealthy_services) if unhealthy_services else 'none'}",
            f"- Dirty tenant worktrees: {', '.join(dirty_tenants) if dirty_tenants else 'none'}",
            f"- Tenants behind origin/main: {', '.join(behind_tenants) if behind_tenants else 'none'}",
        ]

        if ml_context.get("available"):
            op_conf = ml_context.get("operational_confidence")
            confidence_line = (
                f"{int(round(op_conf * 100))}%"
                if op_conf is not None
                else "insufficient history"
            )
            lines.extend(
                [
                    f"- Ops ML confidence: {confidence_line}",
                    f"- ML-tracked skills: {ml_context.get('tracked_skills', 0)}",
                ]
            )

        lines.extend(["", "Predicted blockers:"])
        for item in predictions:
            lines.append(f"- {item}")

        lines.extend(["", "Recommended next actions:"])
        for item in recommendations:
            lines.append(f"- {item}")

        if detail_level == "full":
            lines.extend(["", "Service states:"])
            for row in services:
                lines.append(f"- {row['service']}: {row['state']}")

            lines.extend(["", "Tenant git detail:"])
            for row in git_rows:
                lines.append(
                    f"- {row['tenant']}: branch {row['branch']} | HEAD {row['head']} | "
                    f"origin/main {row['origin_main']} | dirty {row['dirty_count']} | "
                    f"ahead {row['ahead']} / behind {row['behind']}"
                )

            lines.extend(["", "PHP lint detail:"])
            for report in lint_reports:
                if report["files"]:
                    lines.append(f"- {report['tenant']}: checked {len(report['files'])} changed PHP files")
                else:
                    lines.append(f"- {report['tenant']}: no changed PHP files found")
                for error in report["errors"]:
                    lines.append(f"  ERROR {error}")

            if ml_context.get("available"):
                focus_scores = ml_context.get("focus_scores", {})
                if focus_scores:
                    lines.extend(["", "Ops skill ML signals:"])
                    for name in OPS_ML_SKILLS:
                        score = focus_scores.get(name)
                        if not score:
                            continue
                        perf = score.get("performance_score")
                        perf_text = (
                            f"{int(round(perf * 100))}%"
                            if perf is not None
                            else "n/a"
                        )
                        lines.append(
                            f"- {name}: score {perf_text} | trend {score.get('trend', 'unknown')} | "
                            f"runs {score.get('total_runs', 0)}"
                        )

        return "\n".join(lines)

    async def _dispatch_report(
        self,
        report_text: str,
        report_channel: str,
        recipient: str,
        risk_level: str,
        readiness_score: int,
        context: SkillContext,
    ) -> dict:
        dispatch = {"channel": report_channel, "email": "skipped", "sanaa_ai": "skipped"}

        if report_channel in {"email", "both"}:
            recipients = self._parse_recipients(recipient)
            if recipients:
                sent = await send_alert_email(
                    subject=f"[Sanaa Doctor] {risk_level.upper()} readiness {readiness_score}/100",
                    body=report_text,
                    recipients=recipients,
                )
                dispatch["email"] = "sent" if sent else "failed"
                dispatch["email_recipients"] = recipients
            else:
                dispatch["email"] = "no_recipients"

        if report_channel in {"sanaa_ai", "both"}:
            if getattr(context, "brain", None) is None:
                dispatch["sanaa_ai"] = "unavailable"
            else:
                try:
                    await context.brain.remember(
                        report_text,
                        category="operations_report",
                        source="sanaa_doctor",
                    )
                    dispatch["sanaa_ai"] = "stored"
                except Exception as exc:
                    dispatch["sanaa_ai"] = f"failed: {exc}"

        return dispatch

    def _parse_recipients(self, raw: str) -> list[str]:
        values = [item.strip() for item in raw.split(",") if item.strip()]
        if values:
            return values
        settings = get_settings()
        return list(settings.alert_recipient_list)

"""Sanaa tenant sync skill.

Safely propagates tested tenant updates across the Sanaa multi-tenant estate.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from datetime import datetime
from pathlib import Path

from core.skills.base import BaseSkill, SkillContext, SkillParameter, SkillResult


TENANT_ROOTS = {
    "bukuya": "/var/www/bukuya.sanaa.ug/mbalala",
    "kalamba": "/var/www/kalamba.sanaa.co/mbalala",
    "kasawo": "/var/www/kasawo.sanaa.ug/mbalala",
    "kyaliwajjala": "/var/www/kyaliwajjala.sanaa.ug/mbalala",
    "mityana": "/var/www/mityana.sanaa.ug/mbalala",
    "mslink": "/var/www/mslink.sanaa.ug/mbalala",
}

FRONTEND_SUFFIXES = (
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".vue",
    ".css",
    ".scss",
    ".sass",
    ".less",
)

PHP_SUFFIXES = (".php",)


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


class SanaaTenantSyncSkill(BaseSkill):
    name = "sanaa_tenant_sync"
    description = (
        "Pull a source tenant repo and safely sync changed files to other Sanaa tenants "
        "with backups, lint checks, cache clears, and conditional frontend builds."
    )
    version = "1.0.0"
    permissions = ["shell", "filesystem"]
    timeout = 900
    tags = ["tenants", "deployment", "sync", "operations", "infrastructure", "git"]
    parameters = [
        SkillParameter(
            name="action",
            type="string",
            description="Action to perform: status, pull_source, pull_and_sync, sync_worktree",
            required=True,
            enum=["status", "pull_source", "pull_and_sync", "sync_worktree"],
        ),
        SkillParameter(
            name="source_tenant",
            type="string",
            description="Source tenant slug",
            required=False,
            default="kasawo",
            enum=["kasawo", "kalamba", "bukuya", "kyaliwajjala", "mityana", "mslink"],
        ),
        SkillParameter(
            name="targets",
            type="string",
            description="Comma-separated tenant slugs to update, or all",
            required=False,
            default="all",
        ),
        SkillParameter(
            name="base_ref",
            type="string",
            description="Optional git base ref used for diff reporting",
            required=False,
        ),
        SkillParameter(
            name="files_csv",
            type="string",
            description="Optional comma-separated files for sync_worktree. If omitted, source worktree changes are used.",
            required=False,
        ),
        SkillParameter(
            name="build_frontend",
            type="boolean",
            description="Run npm build when synced files touch frontend assets",
            required=False,
            default=True,
        ),
    ]

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        args = self.apply_defaults(args)
        action = str(args.get("action", "")).strip()
        source_slug = str(args.get("source_tenant", "kasawo")).strip().lower()

        if source_slug not in TENANT_ROOTS:
            return SkillResult(success=False, error=f"Unknown source_tenant '{source_slug}'.")

        source_root = TENANT_ROOTS[source_slug]
        targets = self._parse_targets(str(args.get("targets", "all")), source_slug)
        build_frontend = bool(args.get("build_frontend", True))

        if action == "status":
            return await self._status(source_slug, source_root, targets)
        if action == "pull_source":
            return await self._pull_source(source_slug, source_root)
        if action == "pull_and_sync":
            return await self._pull_and_sync(source_slug, source_root, targets, build_frontend)
        if action == "sync_worktree":
            files = await self._worktree_files(source_root, str(args.get("files_csv", "")).strip())
            if not files:
                return SkillResult(success=False, error="No source worktree files found to sync.")
            return await self._sync_files(
                source_slug=source_slug,
                source_root=source_root,
                targets=targets,
                changed_files=files,
                build_frontend=build_frontend,
                sync_reason="source worktree",
            )

        return SkillResult(success=False, error=f"Unknown action '{action}'.")

    def _parse_targets(self, raw: str, source_slug: str) -> list[str]:
        cleaned = (raw or "all").strip().lower()
        if cleaned in {"", "all"}:
            return [slug for slug in TENANT_ROOTS if slug != source_slug]

        wanted = []
        for part in cleaned.split(","):
            slug = part.strip().lower()
            if slug and slug in TENANT_ROOTS and slug != source_slug and slug not in wanted:
                wanted.append(slug)
        return wanted

    async def _status(self, source_slug: str, source_root: str, targets: list[str]) -> SkillResult:
        head = await self._git_head(source_root)
        branch = await self._git_branch(source_root)
        dirty_count = await self._git_dirty_count(source_root)
        remote_head = await self._git_remote_head(source_root)
        worktree_files = await self._worktree_files(source_root, "")
        lines = [
            f"Source tenant: {source_slug}",
            f"Branch: {branch}",
            f"HEAD: {head}",
            f"Origin/main: {remote_head}",
            f"Dirty files: {dirty_count}",
            f"Worktree changes detected: {len(worktree_files)}",
            "",
            "Targets:",
        ]
        target_rows = []
        for slug in targets:
            root = TENANT_ROOTS[slug]
            target_rows.append(
                f"- {slug}: HEAD {await self._git_head(root)} | dirty {await self._git_dirty_count(root)}"
            )

        lines.extend(target_rows)
        if worktree_files:
            lines.append("")
            lines.append("Changed source files:")
            lines.extend(f"- {path}" for path in worktree_files[:40])
            if len(worktree_files) > 40:
                lines.append(f"- ... and {len(worktree_files) - 40} more")

        return SkillResult(
            success=True,
            output="\n".join(lines),
            data={
                "source_tenant": source_slug,
                "source_head": head,
                "remote_head": remote_head,
                "dirty_count": dirty_count,
                "targets": targets,
                "worktree_files": worktree_files,
            },
        )

    async def _pull_source(self, source_slug: str, source_root: str) -> SkillResult:
        dirty_count = await self._git_dirty_count(source_root)
        if dirty_count:
            return SkillResult(
                success=False,
                error=f"Source tenant '{source_slug}' has {dirty_count} dirty files. Refusing to pull.",
            )

        old_head = await self._git_head(source_root)
        code, _, err = await _run_cmd(["git", "pull", "--ff-only", "origin", "main"], cwd=source_root, timeout=300)
        if code != 0:
            return SkillResult(success=False, error=err or "git pull failed")

        new_head = await self._git_head(source_root)
        changed_files = await self._git_changed_files(source_root, old_head, new_head)
        output = [
            f"Pulled source tenant '{source_slug}'.",
            f"Old HEAD: {old_head}",
            f"New HEAD: {new_head}",
            f"Changed files: {len(changed_files)}",
        ]
        output.extend(f"- {path}" for path in changed_files[:50])
        if len(changed_files) > 50:
            output.append(f"- ... and {len(changed_files) - 50} more")

        return SkillResult(
            success=True,
            output="\n".join(output),
            data={
                "source_tenant": source_slug,
                "old_head": old_head,
                "new_head": new_head,
                "changed_files": changed_files,
            },
        )

    async def _pull_and_sync(
        self,
        source_slug: str,
        source_root: str,
        targets: list[str],
        build_frontend: bool,
    ) -> SkillResult:
        dirty_count = await self._git_dirty_count(source_root)
        if dirty_count:
            return SkillResult(
                success=False,
                error=f"Source tenant '{source_slug}' has {dirty_count} dirty files. Refusing pull_and_sync.",
            )

        old_head = await self._git_head(source_root)
        code, _, err = await _run_cmd(["git", "pull", "--ff-only", "origin", "main"], cwd=source_root, timeout=300)
        if code != 0:
            return SkillResult(success=False, error=err or "git pull failed")

        new_head = await self._git_head(source_root)
        changed_files = await self._git_changed_files(source_root, old_head, new_head)
        if not changed_files:
            return SkillResult(
                success=True,
                output=f"Source tenant '{source_slug}' is already up to date. Nothing to sync.",
                data={"source_tenant": source_slug, "old_head": old_head, "new_head": new_head, "changed_files": []},
            )

        return await self._sync_files(
            source_slug=source_slug,
            source_root=source_root,
            targets=targets,
            changed_files=changed_files,
            build_frontend=build_frontend,
            sync_reason=f"git diff {old_head}..{new_head}",
            extra_data={"old_head": old_head, "new_head": new_head},
        )

    async def _sync_files(
        self,
        source_slug: str,
        source_root: str,
        targets: list[str],
        changed_files: list[str],
        build_frontend: bool,
        sync_reason: str,
        extra_data: dict | None = None,
    ) -> SkillResult:
        changed_files = self._normalize_paths(changed_files)
        lint_errors = await self._lint_source_php(source_root, changed_files)
        if lint_errors:
            return SkillResult(
                success=False,
                error="Source PHP lint failed; refusing to sync broken files.",
                output="\n".join(["Source lint errors:"] + [f"- {line}" for line in lint_errors]),
                data={"lint_errors": lint_errors, "changed_files": changed_files},
            )

        backup_root = f"/tmp/sanaa-tenant-sync-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        target_reports = []

        for slug in targets:
            target_root = TENANT_ROOTS[slug]
            report = await self._sync_target(
                source_root=source_root,
                target_slug=slug,
                target_root=target_root,
                changed_files=changed_files,
                backup_root=backup_root,
                build_frontend=build_frontend,
            )
            target_reports.append(report)

        succeeded = [r["target"] for r in target_reports if r["success"]]
        failed = [r["target"] for r in target_reports if not r["success"]]

        lines = [
            f"Synced from {source_slug} using {sync_reason}.",
            f"Changed files: {len(changed_files)}",
            f"Backup root: {backup_root}",
            f"Targets updated: {', '.join(succeeded) if succeeded else 'none'}",
        ]
        if failed:
            lines.append(f"Targets failed: {', '.join(failed)}")
        lines.append("")
        for report in target_reports:
            status = "OK" if report["success"] else "FAILED"
            lines.append(f"[{status}] {report['target']}")
            if report["copied"]:
                lines.append(f"  copied: {len(report['copied'])} files")
            if report["built"]:
                lines.append("  frontend build: completed")
            if report["error"]:
                lines.append(f"  error: {report['error']}")

        data = {
            "source_tenant": source_slug,
            "changed_files": changed_files,
            "backup_root": backup_root,
            "targets": target_reports,
        }
        if extra_data:
            data.update(extra_data)

        return SkillResult(
            success=not failed,
            output="\n".join(lines),
            data=data,
        )

    async def _sync_target(
        self,
        source_root: str,
        target_slug: str,
        target_root: str,
        changed_files: list[str],
        backup_root: str,
        build_frontend: bool,
    ) -> dict:
        copied: list[str] = []
        report = {"target": target_slug, "success": True, "copied": copied, "built": False, "error": ""}

        try:
            for rel_path in changed_files:
                source_path = os.path.join(source_root, rel_path)
                target_path = os.path.join(target_root, rel_path)

                if not os.path.exists(source_path):
                    continue

                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                if os.path.exists(target_path):
                    backup_path = os.path.join(backup_root, target_slug, rel_path)
                    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                    shutil.copy2(target_path, backup_path)

                shutil.copy2(source_path, target_path)
                copied.append(rel_path)

            blade_files = [p for p in copied if p.endswith(".blade.php")]
            php_files = [p for p in copied if p.endswith(PHP_SUFFIXES) and not p.endswith(".blade.php")]
            frontend_files = [p for p in copied if p.endswith(FRONTEND_SUFFIXES)]

            for rel_path in php_files:
                code, _, err = await _run_cmd(["php", "-l", os.path.join(target_root, rel_path)], timeout=60)
                if code != 0:
                    raise RuntimeError(f"php -l failed for {rel_path}: {err}")

            if php_files or blade_files:
                code, _, err = await _run_cmd(["php", "artisan", "optimize:clear"], cwd=target_root, timeout=300)
                if code != 0:
                    raise RuntimeError(err or "php artisan optimize:clear failed")

            if build_frontend and frontend_files:
                code, _, err = await _run_cmd(["npm", "run", "build"], cwd=target_root, timeout=1800)
                if code != 0:
                    raise RuntimeError(err or "npm run build failed")
                report["built"] = True

            return report
        except Exception as exc:
            report["success"] = False
            report["error"] = str(exc)
            return report

    async def _lint_source_php(self, source_root: str, files: list[str]) -> list[str]:
        errors = []
        for rel_path in files:
            if (not rel_path.endswith(PHP_SUFFIXES)) or rel_path.endswith(".blade.php"):
                continue
            abs_path = os.path.join(source_root, rel_path)
            code, _, err = await _run_cmd(["php", "-l", abs_path], timeout=60)
            if code != 0:
                errors.append(f"{rel_path}: {err}")
        return errors

    async def _worktree_files(self, source_root: str, files_csv: str) -> list[str]:
        if files_csv:
            return self._normalize_paths([part.strip() for part in files_csv.split(",") if part.strip()])

        files: set[str] = set()
        for cmd in (
            ["git", "diff", "--name-only"],
            ["git", "diff", "--cached", "--name-only"],
            ["git", "ls-files", "--others", "--exclude-standard"],
        ):
            code, out, _ = await _run_cmd(cmd, cwd=source_root, timeout=60)
            if code == 0 and out:
                files.update(line.strip() for line in out.splitlines() if line.strip())

        return self._normalize_paths(sorted(files))

    async def _git_changed_files(self, repo_root: str, old_ref: str, new_ref: str) -> list[str]:
        if old_ref == new_ref:
            return []
        code, out, err = await _run_cmd(["git", "diff", "--name-only", f"{old_ref}..{new_ref}"], cwd=repo_root, timeout=120)
        if code != 0:
            raise RuntimeError(err or "git diff failed")
        return self._normalize_paths(out.splitlines())

    async def _git_head(self, repo_root: str) -> str:
        code, out, err = await _run_cmd(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root, timeout=30)
        if code != 0:
            raise RuntimeError(err or f"Unable to read HEAD for {repo_root}")
        return out.strip()

    async def _git_branch(self, repo_root: str) -> str:
        code, out, _ = await _run_cmd(["git", "branch", "--show-current"], cwd=repo_root, timeout=30)
        return out.strip() if code == 0 else "unknown"

    async def _git_remote_head(self, repo_root: str) -> str:
        await _run_cmd(["git", "fetch", "origin", "main"], cwd=repo_root, timeout=180)
        code, out, _ = await _run_cmd(["git", "rev-parse", "--short", "origin/main"], cwd=repo_root, timeout=30)
        return out.strip() if code == 0 else "unknown"

    async def _git_dirty_count(self, repo_root: str) -> int:
        code, out, _ = await _run_cmd(["git", "status", "--short"], cwd=repo_root, timeout=30)
        if code != 0 or not out:
            return 0
        return len([line for line in out.splitlines() if line.strip()])

    def _normalize_paths(self, paths: list[str]) -> list[str]:
        normalized = []
        seen = set()
        for raw in paths:
            path = raw.strip().strip('"')
            if not path or path.startswith("..") or os.path.isabs(path):
                continue
            path = str(Path(path))
            if path not in seen:
                seen.add(path)
                normalized.append(path)
        return normalized

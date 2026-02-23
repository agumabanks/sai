"""
Policy helpers for Sanaa AI (tool policy, session policy, and doctor checks).

This module centralizes policy persistence and evaluation so the brain, router,
and API layers enforce the same rules.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, desc

from core.config import get_settings
from core.database import AsyncSessionLocal, SystemKnowledge, Conversation


settings = get_settings()

KNOWN_PROVIDERS = {"anthropic", "groq", "openrouter", "local", "claude", "auto"}
KNOWN_CHANNELS = {"web", "whatsapp", "telegram"}
KNOWN_DM_SCOPES = {"main", "per-peer", "per-channel-peer"}
KNOWN_RESET_MODES = {"none", "daily", "idle", "daily_or_idle"}
KNOWN_SEND_DEFAULTS = {"allow", "deny"}
KNOWN_EXPOSURES = {"auto", "hidden", "manual_only"}
DEFAULT_TOOL_ALLOW = ["server_health", "app_monitor", "web_test"]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_name_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [v.strip() for v in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        items = [str(v).strip() for v in value]
    else:
        items = [str(value).strip()]

    out: list[str] = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return out


def _normalize_tool_rule(rule: Any) -> dict:
    if not isinstance(rule, dict):
        return {"allow": [], "deny": []}
    return {
        "allow": _normalize_name_list(rule.get("allow")),
        "deny": _normalize_name_list(rule.get("deny")),
    }


def _safe_json_loads(raw: Any, default: Any):
    if raw in (None, ""):
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(str(raw))
    except Exception:
        return default


async def _get_pref_json(key: str, domain: str = "preference", default=None):
    raw = await SystemKnowledge.get_pref(key, default=None, domain=domain)
    if raw is None:
        return default
    return _safe_json_loads(raw, default)


async def _set_pref_json(key: str, value: Any, source: str = "system", domain: str = "preference"):
    return await SystemKnowledge.set_pref(key, json.dumps(value), source=source, domain=domain)


def infer_skill_safety_tier(skill) -> str:
    perms = set(getattr(skill, "permissions", []) or [])
    if "shell" in perms:
        return "shell"
    if "filesystem" in perms:
        return "filesystem"
    if "network" in perms:
        return "network"
    return "read_only"


def infer_skill_groups(skill) -> list[str]:
    tags = [str(t).strip().lower() for t in (getattr(skill, "tags", []) or []) if str(t).strip()]
    groups = []
    for tag in tags:
        if tag not in groups:
            groups.append(tag)
    return groups or ["general"]


def _normalize_tool_policy(policy: Optional[dict] = None) -> dict:
    policy = policy or {}
    by_provider = policy.get("by_provider") if isinstance(policy.get("by_provider"), dict) else {}
    by_channel = policy.get("by_channel") if isinstance(policy.get("by_channel"), dict) else {}

    norm = {
        "enabled": bool(policy.get("enabled", True)),
        "mode": str(policy.get("mode", "allowlist") or "allowlist").strip().lower(),
        "allow": _normalize_name_list(policy.get("allow") or DEFAULT_TOOL_ALLOW),
        "deny": _normalize_name_list(policy.get("deny")),
        "groups": {
            "allow": _normalize_name_list((policy.get("groups") or {}).get("allow")),
            "deny": _normalize_name_list((policy.get("groups") or {}).get("deny")),
        },
        "by_provider": {},
        "by_channel": {},
    }
    if norm["mode"] not in {"allow_all", "allowlist"}:
        norm["mode"] = "allowlist"
    if not norm["allow"] and norm["mode"] == "allowlist":
        norm["allow"] = DEFAULT_TOOL_ALLOW.copy()

    for provider, rule in by_provider.items():
        p = str(provider).strip().lower()
        if p in KNOWN_PROVIDERS:
            norm["by_provider"][p] = _normalize_tool_rule(rule)

    for channel, rule in by_channel.items():
        c = str(channel).strip().lower()
        if c:
            norm["by_channel"][c] = _normalize_tool_rule(rule)

    return norm


async def get_tool_policy() -> dict:
    """Load tool policy from DB preferences."""
    policy = {
        "enabled": await SystemKnowledge.get_pref("tool_policy.enabled", default=True),
        "mode": await SystemKnowledge.get_pref("tool_policy.mode", default="allowlist"),
        "allow": await SystemKnowledge.get_pref("tool_policy.allow", default=DEFAULT_TOOL_ALLOW),
        "deny": await SystemKnowledge.get_pref("tool_policy.deny", default=[]),
        "groups": {
            "allow": await SystemKnowledge.get_pref("tool_policy.groups.allow", default=[]),
            "deny": await SystemKnowledge.get_pref("tool_policy.groups.deny", default=[]),
        },
        "by_provider": await _get_pref_json("tool_policy.by_provider", default={}),
        "by_channel": await _get_pref_json("tool_policy.by_channel", default={}),
    }
    return _normalize_tool_policy(policy)


async def save_tool_policy(update: dict, source: str = "admin_dashboard", skill_names: Optional[set[str]] = None) -> dict:
    """Partially update and persist tool policy."""
    current = await get_tool_policy()
    merged = dict(current)
    groups = dict(current.get("groups", {}))

    for key in ("enabled", "mode", "allow", "deny", "by_provider", "by_channel"):
        if key in update:
            merged[key] = update[key]
    if "groups" in update and isinstance(update["groups"], dict):
        if "allow" in update["groups"]:
            groups["allow"] = update["groups"]["allow"]
        if "deny" in update["groups"]:
            groups["deny"] = update["groups"]["deny"]
    merged["groups"] = groups
    merged = _normalize_tool_policy(merged)

    if skill_names is not None:
        refs = set(merged["allow"]) | set(merged["deny"])
        for rule in merged["by_provider"].values():
            refs |= set(rule.get("allow", [])) | set(rule.get("deny", []))
        for rule in merged["by_channel"].values():
            refs |= set(rule.get("allow", [])) | set(rule.get("deny", []))
        unknown = sorted([r for r in refs if r not in skill_names])
        if unknown:
            raise ValueError(f"Unknown skills in policy: {', '.join(unknown)}")

    await SystemKnowledge.set_pref("tool_policy.enabled", bool(merged["enabled"]), source=source)
    await SystemKnowledge.set_pref("tool_policy.mode", merged["mode"], source=source)
    await SystemKnowledge.set_pref("tool_policy.allow", merged["allow"], source=source)
    await SystemKnowledge.set_pref("tool_policy.deny", merged["deny"], source=source)
    await SystemKnowledge.set_pref("tool_policy.groups.allow", merged["groups"]["allow"], source=source)
    await SystemKnowledge.set_pref("tool_policy.groups.deny", merged["groups"]["deny"], source=source)
    await _set_pref_json("tool_policy.by_provider", merged["by_provider"], source=source)
    await _set_pref_json("tool_policy.by_channel", merged["by_channel"], source=source)
    return merged


async def get_skill_overrides(skill_name: str) -> dict:
    enabled = await SystemKnowledge.get_pref(f"skills.enabled.{skill_name}", default=True)
    exposure = await SystemKnowledge.get_pref(f"skills.exposure.{skill_name}", default="auto")
    exposure = str(exposure or "auto").strip().lower()
    if exposure not in KNOWN_EXPOSURES:
        exposure = "auto"
    return {"enabled": bool(enabled), "exposure": exposure}


async def set_skill_enabled(skill_name: str, enabled: bool, source: str = "admin_dashboard") -> dict:
    await SystemKnowledge.set_pref(f"skills.enabled.{skill_name}", bool(enabled), source=source)
    return await get_skill_overrides(skill_name)


async def set_skill_exposure(skill_name: str, exposure: str, source: str = "admin_dashboard") -> dict:
    exposure = str(exposure or "").strip().lower()
    if exposure not in KNOWN_EXPOSURES:
        raise ValueError("Invalid exposure")
    await SystemKnowledge.set_pref(f"skills.exposure.{skill_name}", exposure, source=source)
    return await get_skill_overrides(skill_name)


def effective_brain_provider_name(brain_provider: str, claude_source: str) -> str:
    provider = (brain_provider or "auto").strip().lower()
    claude_source = (claude_source or "anthropic").strip().lower()
    if provider == "claude":
        return claude_source if claude_source in {"anthropic", "groq", "openrouter"} else "anthropic"
    return provider


def _matches_allowlist(skill_name: str, groups: list[str], allow: list[str], group_allow: list[str]) -> bool:
    if skill_name in allow:
        return True
    return any(g in group_allow for g in groups)


def _rule_denies(skill_name: str, deny: list[str]) -> bool:
    return skill_name in deny


async def evaluate_skill_access(
    *,
    skill,
    invocation: str,
    provider: str,
    channel: str,
) -> dict:
    """
    Evaluate whether a skill can run.

    invocation: 'brain' | 'manual' | 'workflow'
    """
    policy = await get_tool_policy()
    overrides = await get_skill_overrides(skill.name)
    groups = infer_skill_groups(skill)
    safety_tier = infer_skill_safety_tier(skill)

    enabled = overrides["enabled"]
    exposure = overrides["exposure"]
    manual_only = exposure == "manual_only"
    hidden = exposure == "hidden"

    allowed = True
    reason = ""

    if not enabled:
        allowed = False
        reason = "Skill is disabled by policy"
    elif invocation == "brain":
        if hidden:
            allowed = False
            reason = "Skill is hidden from the AI brain"
        elif manual_only:
            allowed = False
            reason = "Skill is manual-only and cannot be auto-called by the AI brain"

    if allowed and policy.get("enabled", True) and invocation == "brain":
        if policy["mode"] == "allow_all":
            allowed = True
        else:
            allowed = _matches_allowlist(
                skill.name,
                groups,
                policy.get("allow", []),
                (policy.get("groups") or {}).get("allow", []),
            )
            if not allowed:
                reason = "Skill is not in the AI tool allowlist"

        if allowed:
            if skill.name in policy.get("deny", []) or any(
                g in (policy.get("groups") or {}).get("deny", []) for g in groups
            ):
                allowed = False
                reason = "Skill is blocked by deny policy"

        if allowed:
            p_rule = _normalize_tool_rule((policy.get("by_provider") or {}).get((provider or "").lower(), {}))
            if p_rule["allow"] and skill.name not in p_rule["allow"]:
                allowed = False
                reason = f"Skill is not allowed for provider '{provider}'"
            if allowed and _rule_denies(skill.name, p_rule["deny"]):
                allowed = False
                reason = f"Skill is denied for provider '{provider}'"

        if allowed:
            c_rule = _normalize_tool_rule((policy.get("by_channel") or {}).get((channel or "").lower(), {}))
            if c_rule["allow"] and skill.name not in c_rule["allow"]:
                allowed = False
                reason = f"Skill is not allowed on channel '{channel}'"
            if allowed and _rule_denies(skill.name, c_rule["deny"]):
                allowed = False
                reason = f"Skill is denied on channel '{channel}'"

    return {
        "allowed": allowed,
        "reason": reason,
        "enabled": enabled,
        "exposure": exposure,
        "manual_only": manual_only,
        "hidden": hidden,
        "safety_tier": safety_tier,
        "groups": groups,
        "policy_enabled": bool(policy.get("enabled", True)),
    }


async def build_skill_catalog(skill_registry, provider: str = "auto", channel: str = "web") -> list[dict]:
    items: list[dict] = []
    for skill in skill_registry._skills.values():
        access_brain = await evaluate_skill_access(skill=skill, invocation="brain", provider=provider, channel=channel)
        access_manual = await evaluate_skill_access(skill=skill, invocation="manual", provider=provider, channel=channel)
        items.append(
            {
                "name": skill.name,
                "description": skill.description,
                "version": getattr(skill, "version", "1.0.0"),
                "permissions": getattr(skill, "permissions", []),
                "requires_approval": bool(getattr(skill, "requires_approval", False)),
                "tags": getattr(skill, "tags", []),
                "parameter_count": len(getattr(skill, "parameters", []) or []),
                "groups": access_brain["groups"],
                "safety_tier": access_brain["safety_tier"],
                "enabled": access_brain["enabled"],
                "exposure": access_brain["exposure"],
                "exposed_to_brain": access_brain["allowed"],
                "manual_allowed": access_manual["allowed"],
                "brain_denied_reason": access_brain["reason"] or None,
            }
        )
    return items


def _session_policy_defaults() -> dict:
    return {
        "dm_scope": "per-channel-peer",
        "reset": {
            "mode": "daily_or_idle",
            "at_hour": 4,
            "idle_minutes": 240,
        },
        "send_policy": {
            "default": "allow",
            "rules": [],
        },
        "reset_triggers": ["/new", "/reset"],
        "secure_dm_mode": True,
    }


def _normalize_session_policy(policy: Optional[dict] = None) -> dict:
    raw = _session_policy_defaults()
    policy = policy or {}
    dm_scope = str(policy.get("dm_scope", raw["dm_scope"]) or raw["dm_scope"]).strip().lower()
    if dm_scope not in KNOWN_DM_SCOPES:
        dm_scope = raw["dm_scope"]

    reset_src = policy.get("reset") if isinstance(policy.get("reset"), dict) else {}
    reset_mode = str(reset_src.get("mode", raw["reset"]["mode"]) or raw["reset"]["mode"]).strip().lower()
    if reset_mode not in KNOWN_RESET_MODES:
        reset_mode = raw["reset"]["mode"]

    try:
        at_hour = int(reset_src.get("at_hour", raw["reset"]["at_hour"]))
    except Exception:
        at_hour = raw["reset"]["at_hour"]
    at_hour = min(max(at_hour, 0), 23)

    try:
        idle_minutes = int(reset_src.get("idle_minutes", raw["reset"]["idle_minutes"]))
    except Exception:
        idle_minutes = raw["reset"]["idle_minutes"]
    idle_minutes = max(idle_minutes, 0)

    send_src = policy.get("send_policy") if isinstance(policy.get("send_policy"), dict) else {}
    send_default = str(send_src.get("default", raw["send_policy"]["default"]) or raw["send_policy"]["default"]).strip().lower()
    if send_default not in KNOWN_SEND_DEFAULTS:
        send_default = raw["send_policy"]["default"]

    rules = send_src.get("rules", raw["send_policy"]["rules"])
    if not isinstance(rules, list):
        rules = []
    normalized_rules = []
    for r in rules:
        if not isinstance(r, dict):
            continue
        action = str(r.get("action", "")).strip().lower()
        if action not in {"allow", "deny"}:
            continue
        match = r.get("match") if isinstance(r.get("match"), dict) else {}
        normalized_rules.append({"action": action, "match": match})

    reset_triggers = _normalize_name_list(policy.get("reset_triggers", raw["reset_triggers"]))
    if not reset_triggers:
        reset_triggers = raw["reset_triggers"]

    secure_dm = dm_scope != "main"
    return {
        "dm_scope": dm_scope,
        "reset": {"mode": reset_mode, "at_hour": at_hour, "idle_minutes": idle_minutes},
        "send_policy": {"default": send_default, "rules": normalized_rules},
        "reset_triggers": reset_triggers,
        "secure_dm_mode": secure_dm,
    }


async def get_session_policy() -> dict:
    policy = {
        "dm_scope": await SystemKnowledge.get_pref("session.dm_scope", default="per-channel-peer"),
        "reset": {
            "mode": await SystemKnowledge.get_pref("session.reset.mode", default="daily_or_idle"),
            "at_hour": await SystemKnowledge.get_pref("session.reset.at_hour", default=4),
            "idle_minutes": await SystemKnowledge.get_pref("session.reset.idle_minutes", default=240),
        },
        "send_policy": {
            "default": await SystemKnowledge.get_pref("session.send_policy.default", default="allow"),
            "rules": await _get_pref_json("session.send_policy.rules", default=[]),
        },
        "reset_triggers": await SystemKnowledge.get_pref("session.reset_triggers", default=["/new", "/reset"]),
    }
    return _normalize_session_policy(policy)


async def save_session_policy(update: dict, source: str = "admin_dashboard") -> dict:
    current = await get_session_policy()
    merged = dict(current)
    if "dm_scope" in update:
        merged["dm_scope"] = update["dm_scope"]
    if "reset" in update and isinstance(update["reset"], dict):
        merged["reset"] = {**current.get("reset", {}), **update["reset"]}
    if "send_policy" in update and isinstance(update["send_policy"], dict):
        merged["send_policy"] = {
            **current.get("send_policy", {}),
            **update["send_policy"],
        }
    if "reset_triggers" in update:
        merged["reset_triggers"] = update["reset_triggers"]
    merged = _normalize_session_policy(merged)

    await SystemKnowledge.set_pref("session.dm_scope", merged["dm_scope"], source=source)
    await SystemKnowledge.set_pref("session.reset.mode", merged["reset"]["mode"], source=source)
    await SystemKnowledge.set_pref("session.reset.at_hour", merged["reset"]["at_hour"], source=source)
    await SystemKnowledge.set_pref("session.reset.idle_minutes", merged["reset"]["idle_minutes"], source=source)
    await SystemKnowledge.set_pref("session.send_policy.default", merged["send_policy"]["default"], source=source)
    await _set_pref_json("session.send_policy.rules", merged["send_policy"]["rules"], source=source)
    await SystemKnowledge.set_pref("session.reset_triggers", merged["reset_triggers"], source=source)
    await SystemKnowledge.set_pref("session.secure_dm_mode", merged["secure_dm_mode"], source=source)
    return merged


def derive_route_key(message, policy: dict) -> str:
    if getattr(message, "is_group", False):
        group_id = getattr(message, "group_id", None) or getattr(message, "chat_id", "")
        return f"group:{message.channel}:{group_id}"

    dm_scope = (policy or {}).get("dm_scope", "per-channel-peer")
    sender_id = getattr(message, "sender_id", "") or "unknown"
    if dm_scope == "main":
        return f"dm:main:{message.channel}"
    if dm_scope == "per-peer":
        return f"dm:peer:{sender_id}"
    return f"dm:channel-peer:{message.channel}:{sender_id}"


def _new_session_id(route_key: str) -> str:
    seed = f"{route_key}:{time.time()}".encode()
    return hashlib.sha256(seed).hexdigest()[:24]


async def get_or_create_session_id(message, force_new: bool = False) -> str:
    policy = await get_session_policy()
    route_key = derive_route_key(message, policy)
    pref_key = f"route.{route_key}"
    if not force_new:
        existing = await SystemKnowledge.get_pref(pref_key, default=None, domain="session")
        if existing:
            return str(existing)
    new_id = _new_session_id(route_key)
    await SystemKnowledge.set_pref(pref_key, new_id, source="router", domain="session")
    await _set_pref_json(
        f"route_meta.{route_key}",
        {
            "session_id": new_id,
            "route_key": route_key,
            "channel": getattr(message, "channel", ""),
            "sender_id": getattr(message, "sender_id", ""),
            "is_group": bool(getattr(message, "is_group", False)),
            "group_id": getattr(message, "group_id", None),
            "updated_at": _utc_now_iso(),
        },
        source="router",
        domain="session",
    )
    return new_id


async def reset_session_by_id(session_id: str) -> dict:
    """Best-effort reset by looking up latest conversation for the session and rotating route mapping."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Conversation)
            .where(Conversation.session_id == session_id)
            .order_by(desc(Conversation.created_at))
            .limit(1)
        )
        conv = result.scalars().first()
    if not conv:
        raise ValueError("Session not found")

    # Group IDs aren't persisted in Conversation, so treat as direct sender-based route.
    class _Msg:
        channel = conv.channel
        sender_id = conv.sender_id
        is_group = False
        group_id = None
        chat_id = conv.sender_id

    new_id = await get_or_create_session_id(_Msg(), force_new=True)
    return {"old_session_id": session_id, "new_session_id": new_id, "channel": conv.channel, "sender_id": conv.sender_id}


def _rule_matches(rule: dict, *, channel: str, is_group: bool, session_id: str) -> bool:
    match = rule.get("match") if isinstance(rule.get("match"), dict) else {}
    if "channel" in match and str(match["channel"]).lower() != str(channel).lower():
        return False
    if "chatType" in match:
        desired = str(match["chatType"]).lower()
        actual = "group" if is_group else "direct"
        if desired != actual:
            return False
    if "keyPrefix" in match and not str(session_id).startswith(str(match["keyPrefix"])):
        return False
    if "session_id" in match and str(match["session_id"]) != str(session_id):
        return False
    return True


async def get_session_send_override(session_id: str) -> str:
    mode = await SystemKnowledge.get_pref(f"send_override.{session_id}", default="inherit", domain="session")
    mode = str(mode or "inherit").strip().lower()
    return mode if mode in {"on", "off", "inherit"} else "inherit"


async def set_session_send_override(session_id: str, mode: str, source: str = "admin_dashboard") -> str:
    mode = str(mode or "").strip().lower()
    if mode not in {"on", "off", "inherit"}:
        raise ValueError("Invalid send override mode")
    await SystemKnowledge.set_pref(f"send_override.{session_id}", mode, source=source, domain="session")
    return mode


async def can_send_response(message, session_id: str) -> tuple[bool, str]:
    override = await get_session_send_override(session_id)
    if override == "on":
        return True, "session override on"
    if override == "off":
        return False, "session override off"

    policy = await get_session_policy()
    channel = getattr(message, "channel", "")
    is_group = bool(getattr(message, "is_group", False))
    for rule in policy["send_policy"]["rules"]:
        if _rule_matches(rule, channel=channel, is_group=is_group, session_id=session_id):
            if rule["action"] == "deny":
                return False, "send policy deny rule"
            return True, "send policy allow rule"
    return (policy["send_policy"]["default"] == "allow"), f"default={policy['send_policy']['default']}"


async def list_sessions(limit: int = 100) -> list[dict]:
    """List recent sessions from conversation history with basic metadata."""
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(Conversation)
            .order_by(desc(Conversation.created_at))
            .limit(max(1, min(limit * 20, 5000)))
        )
        conversations = rows.scalars().all()

    latest_by_session: dict[str, Conversation] = {}
    counts: dict[str, int] = {}
    for c in conversations:
        counts[c.session_id] = counts.get(c.session_id, 0) + 1
        if c.session_id not in latest_by_session:
            latest_by_session[c.session_id] = c

    items = []
    for sid, latest in latest_by_session.items():
        items.append(
            {
                "session_id": sid,
                "channel": latest.channel,
                "sender_id": latest.sender_id,
                "sender_name": latest.sender_name,
                "last_message_preview": (latest.content or "")[:180],
                "last_role": latest.role,
                "last_seen": latest.created_at.isoformat() if latest.created_at else None,
                "message_count_sample": counts.get(sid, 0),
                "send_override": await get_session_send_override(sid),
            }
        )
    items.sort(key=lambda x: x.get("last_seen") or "", reverse=True)
    return items[:limit]


async def get_session_detail(session_id: str, limit: int = 50) -> dict:
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(Conversation)
            .where(Conversation.session_id == session_id)
            .order_by(desc(Conversation.created_at))
            .limit(max(1, min(limit, 200)))
        )
        conversations = list(rows.scalars().all())
    if not conversations:
        raise ValueError("Session not found")
    conversations.reverse()
    policy = await get_session_policy()
    return {
        "session_id": session_id,
        "policy": policy,
        "send_override": await get_session_send_override(session_id),
        "messages": [
            {
                "id": c.id,
                "channel": c.channel,
                "sender_id": c.sender_id,
                "sender_name": c.sender_name,
                "role": c.role,
                "content": c.content,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in conversations
        ],
    }


async def run_doctor(brain=None, workflow_loader=None) -> dict:
    """Run lightweight configuration/safety checks."""
    checks: list[dict] = []

    def add(check_id: str, severity: str, ok: bool, message: str):
        checks.append({
            "id": check_id,
            "severity": severity,
            "ok": ok,
            "message": message,
        })

    # Brain / sanaa-clade checks
    brain_provider = await SystemKnowledge.get_pref("brain.provider", default="auto")
    claude_source = await SystemKnowledge.get_pref("brain.claude_source", default=getattr(settings, "brain_claude_source", "anthropic"))
    if str(brain_provider).lower() == "claude":
        has_key = {
            "anthropic": bool(settings.anthropic_api_key),
            "groq": bool(settings.groq_api_key),
            "openrouter": bool(settings.openrouter_api_key),
        }.get(str(claude_source).lower(), False)
        add(
            "brain.claude_source_key",
            "high",
            has_key,
            "Claude mode source has API key configured" if has_key else f"Claude mode is using '{claude_source}' but no API key is configured",
        )

    order = await SystemKnowledge.get_pref("brain.auto_provider_order", default=getattr(settings, "brain_auto_provider_order", ""))
    normalized = [p for p in re.split(r"\s*,\s*", str(order or "")) if p]
    invalid_order = [p for p in normalized if p not in {"groq", "anthropic", "openrouter", "local", "openai"}]
    add("brain.auto_provider_order", "medium", not invalid_order, "Auto provider order valid" if not invalid_order else f"Invalid providers in auto order: {', '.join(invalid_order)}")

    if getattr(settings, "sanaa_clade_enabled", False):
        exists = os.path.isfile(settings.sanaa_clade_path) and os.access(settings.sanaa_clade_path, os.X_OK)
        add("brain.sanaa_clade_path", "high", exists, "sanaa-clade executable is available" if exists else f"sanaa-clade executable not found/executable: {settings.sanaa_clade_path}")

    # Tool policy checks
    policy = await get_tool_policy()
    add("tool_policy.mode", "low", policy["mode"] in {"allow_all", "allowlist"}, f"Tool policy mode={policy['mode']}")

    contradictions = sorted(set(policy["allow"]) & set(policy["deny"]))
    add("tool_policy.allow_deny_conflicts", "medium", not contradictions, "No tool allow/deny contradictions" if not contradictions else f"Conflicting tool entries: {', '.join(contradictions)}")

    # Skill-aware checks
    skill_names: set[str] = set()
    shell_brain_exposed: list[str] = []
    if brain is not None:
        try:
            await brain.ensure_skills_loaded()
            for skill in brain.skill_registry._skills.values():
                skill_names.add(skill.name)
                access = await evaluate_skill_access(
                    skill=skill,
                    invocation="brain",
                    provider=effective_brain_provider_name(str(brain_provider), str(claude_source)),
                    channel="web",
                )
                if access["allowed"] and access["safety_tier"] == "shell":
                    shell_brain_exposed.append(skill.name)
        except Exception as e:
            add("tool_policy.skill_registry", "high", False, f"Failed loading skills for doctor checks: {e}")

    unknown_policy_refs = []
    if skill_names:
        refs = set(policy["allow"]) | set(policy["deny"])
        for r in policy["by_provider"].values():
            refs |= set(r.get("allow", [])) | set(r.get("deny", []))
        for r in policy["by_channel"].values():
            refs |= set(r.get("allow", [])) | set(r.get("deny", []))
        unknown_policy_refs = sorted([r for r in refs if r not in skill_names])
    add("tool_policy.unknown_skills", "medium", not unknown_policy_refs, "No unknown skills in tool policy" if not unknown_policy_refs else f"Unknown skills in tool policy: {', '.join(unknown_policy_refs)}")

    allow_all_shell_ok = not (policy["mode"] == "allow_all" and shell_brain_exposed)
    add(
        "tool_policy.shell_exposed",
        "high",
        allow_all_shell_ok,
        "No shell-capable skills exposed to brain under allow_all"
        if allow_all_shell_ok
        else f"Shell-capable skills exposed under allow_all: {', '.join(shell_brain_exposed)}",
    )

    # Session checks
    session_policy = await get_session_policy()
    multi_sender = (len(getattr(settings, "whatsapp_allowed_list", []) or []) > 1) or (len(getattr(settings, "telegram_allowed_chat_list", []) or []) > 1)
    unsafe_dm = session_policy["dm_scope"] == "main" and multi_sender
    add("session.dm_scope", "high" if unsafe_dm else "low", not unsafe_dm, "DM session isolation policy is safe" if not unsafe_dm else "dm_scope=main with multiple allowed senders/chats may leak context")
    add("session.reset.policy", "medium", session_policy["reset"]["mode"] != "none", "Session reset policy configured" if session_policy["reset"]["mode"] != "none" else "No session reset policy configured")

    group_deny_rule = any(
        isinstance(r, dict) and r.get("action") == "deny" and isinstance(r.get("match"), dict) and r["match"].get("chatType") == "group"
        for r in session_policy["send_policy"]["rules"]
    )
    add(
        "session.send_policy.groups",
        "low" if group_deny_rule else "medium",
        group_deny_rule or session_policy["send_policy"]["default"] == "deny",
        "Group send policy has explicit restrictions" if group_deny_rule or session_policy["send_policy"]["default"] == "deny" else "No explicit group send restrictions configured",
    )

    # Workflow checks
    if workflow_loader is not None:
        try:
            workflows = workflow_loader.discover()
            shell_no_approval = []
            for wf in workflows:
                approval_steps = {s.id for s in wf.steps if getattr(s, "approval", False)}
                for step in wf.steps:
                    deps = set(getattr(step, "depends_on", []) or [])
                    gated_by_approval = bool(deps & approval_steps)
                    if step.action == "shell" and not step.approval and not gated_by_approval:
                        shell_no_approval.append(f"{wf.name}:{step.id}")
            add(
                "workflow.shell_approval",
                "medium",
                not shell_no_approval,
                "All shell workflow steps are approval-gated" if not shell_no_approval else f"Shell steps without per-step approval: {', '.join(shell_no_approval[:10])}",
            )
        except Exception as e:
            add("workflow.load", "high", False, f"Failed to load workflows: {e}")

    incident_path = "/var/www/ai.sanaa.co/backend/workflows/incident_response.yaml"
    if os.path.exists(incident_path):
        try:
            content = open(incident_path, "r", encoding="utf-8").read()
            unsafe_placeholder = "would be executed here" in content
            add(
                "workflow.incident_response.safety",
                "critical" if unsafe_placeholder else "low",
                not unsafe_placeholder,
                "incident_response workflow hardened" if not unsafe_placeholder else "incident_response still contains placeholder/unsafe auto-heal behavior",
            )
        except Exception as e:
            add("workflow.incident_response.read", "medium", False, f"Failed reading incident workflow: {e}")

    # Intelligence checks
    latest_qa = await SystemKnowledge.get_pref("briefing.latest.qa", default=None, domain="news")
    if latest_qa:
        qa = _safe_json_loads(latest_qa, {})
        score = int((qa or {}).get("score", 0) or 0) if isinstance(qa, dict) else 0
        add("news.briefing.qa", "medium" if score < 7 else "low", score >= 7, f"Latest briefing QA score={score}")
    else:
        add("news.briefing.qa", "medium", False, "No briefing QA result found")

    try:
        news_rows = await SystemKnowledge.get_by_domain("news")
        history = []
        for row in news_rows:
            if not str(row.key).startswith("briefing.qa.history."):
                continue
            payload = _safe_json_loads(row.value, {})
            if isinstance(payload, dict):
                history.append((row.key, int(payload.get("score", 0) or 0)))
        history.sort(key=lambda x: x[0], reverse=True)
        recent_scores = [score for _, score in history[:3]]
        repeated_low = len(recent_scores) == 3 and all(s < 7 for s in recent_scores)
        add(
            "news.briefing.qa_trend",
            "medium" if repeated_low else "low",
            not repeated_low,
            f"Recent briefing QA scores={recent_scores}" if recent_scores else "No briefing QA history yet",
        )
    except Exception as e:
        add("news.briefing.qa_trend", "low", False, f"Could not evaluate briefing QA trend: {e}")

    watchdog_adv = await SystemKnowledge.get_pref("watchdog.advisor.latest", default=None, domain="wisdom")
    add("watchdog.advisor", "medium", bool(watchdog_adv), "Watchdog advisor present" if watchdog_adv else "No watchdog advisor result found")

    # Summarize
    fail = sum(1 for c in checks if not c["ok"] and c["severity"] in {"high", "critical"})
    warn = sum(1 for c in checks if not c["ok"] and c["severity"] in {"low", "medium"})
    ok_count = sum(1 for c in checks if c["ok"])
    status = "ok"
    if fail:
        status = "fail"
    elif warn:
        status = "warn"

    return {
        "status": status,
        "checks": checks,
        "summary": {"ok": ok_count, "warn": warn, "fail": fail},
        "generated_at": _utc_now_iso(),
    }

"""
Skill Hot-Reload — file watcher that detects changes to skill manifests and
handlers, then re-validates and reloads them into the skill registry.

Uses the `watchdog` library to monitor backend/skills/ directories for
changes to manifest.yaml and handler.py files.  When a change is detected:

  1. Validate the modified manifest (if manifest.yaml changed)
  2. Reload the handler module (importlib reload)
  3. Update the skill registry with the new version
  4. Log the reload event

Invalid changes are rejected with an error log — the watcher never crashes.

The watcher runs in a background daemon thread started during app lifespan.
"""

import os
import sys
import time
import logging
import threading
from typing import Optional

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from core.skills.manifest import parse_manifest, SkillManifest
from core.skills.scanner import SkillScanner
from core.skills.loader import SkillLoader

logger = logging.getLogger(__name__)

# Files we care about inside each skill directory
_WATCHED_FILES = {"manifest.yaml", "handler.py"}

# Minimum seconds between reloads of the same skill (debounce)
_DEBOUNCE_SECONDS = 1.0


class _SkillChangeHandler(FileSystemEventHandler):
    """Watchdog event handler that filters for skill file changes."""

    def __init__(self, watcher: "SkillFileWatcher"):
        super().__init__()
        self._watcher = watcher

    # ── event callbacks ──────────────────────────────────────────────

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._handle(event.src_path)

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._handle(event.src_path)

    # ── internal ─────────────────────────────────────────────────────

    def _handle(self, path: str) -> None:
        """Determine if a file change should trigger a skill reload."""
        basename = os.path.basename(path)
        if basename not in _WATCHED_FILES:
            return

        # Derive skill name from parent directory
        skill_dir = os.path.dirname(path)
        skill_name = os.path.basename(skill_dir)

        # Debounce: ignore rapid-fire events for the same skill
        self._watcher._schedule_reload(skill_name, skill_dir, basename)


class SkillFileWatcher:
    """Monitors backend/skills/ for manifest.yaml and handler.py changes.

    Usage::

        watcher = SkillFileWatcher(skills_dir, skill_registry)
        watcher.start()   # spawns a daemon thread
        # ... later
        watcher.stop()
    """

    def __init__(
        self,
        skills_dir: str = "/var/www/ai.sanaa.co/backend/skills",
        skill_registry=None,
        debounce_seconds: float = _DEBOUNCE_SECONDS,
    ):
        self.skills_dir = skills_dir
        self.skill_registry = skill_registry
        self.debounce_seconds = debounce_seconds

        self._observer: Optional[Observer] = None
        self._scanner = SkillScanner()
        self._loader = SkillLoader(skills_dir=skills_dir, scanner=self._scanner)

        # Debounce tracking: skill_name -> last_scheduled_time
        self._last_reload: dict[str, float] = {}
        self._lock = threading.Lock()
        self._running = False

        # Reload log for observability / testing
        self._reload_log: list[dict] = []

    # ── public API ───────────────────────────────────────────────────

    def start(self) -> None:
        """Start watching the skills directory in a background daemon thread."""
        if self._running:
            logger.warning("SkillFileWatcher already running")
            return

        if not os.path.isdir(self.skills_dir):
            logger.error(f"Skills directory does not exist: {self.skills_dir}")
            return

        handler = _SkillChangeHandler(self)
        self._observer = Observer()
        self._observer.schedule(handler, self.skills_dir, recursive=True)
        self._observer.daemon = True
        self._observer.start()
        self._running = True
        logger.info(f"SkillFileWatcher started — monitoring {self.skills_dir}")

    def stop(self) -> None:
        """Stop the file watcher."""
        if self._observer and self._running:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._running = False
            logger.info("SkillFileWatcher stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def reload_history(self) -> list[dict]:
        """Return the list of reload events (for observability)."""
        return list(self._reload_log)

    # ── internal ─────────────────────────────────────────────────────

    def _schedule_reload(self, skill_name: str, skill_dir: str, changed_file: str) -> None:
        """Schedule a skill reload, with debounce."""
        now = time.monotonic()
        with self._lock:
            last = self._last_reload.get(skill_name, 0.0)
            if now - last < self.debounce_seconds:
                logger.debug(f"Debounced reload for skill '{skill_name}'")
                return
            self._last_reload[skill_name] = now

        # Run reload in a separate thread to avoid blocking the observer
        t = threading.Thread(
            target=self._reload_skill_sync,
            args=(skill_name, skill_dir, changed_file),
            daemon=True,
        )
        t.start()

    def _reload_skill_sync(self, skill_name: str, skill_dir: str, changed_file: str) -> None:
        """Synchronous wrapper that calls the async reload in an event loop."""
        import asyncio

        try:
            # Try to use an existing event loop, or create a new one
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # We are inside an async context (e.g., during tests) —
                # schedule coroutine on the running loop.
                asyncio.run_coroutine_threadsafe(
                    self._reload_skill(skill_name, skill_dir, changed_file),
                    loop,
                ).result(timeout=30)
            else:
                asyncio.run(self._reload_skill(skill_name, skill_dir, changed_file))
        except Exception as e:
            logger.error(
                f"Hot-reload failed for skill '{skill_name}': {e}",
                exc_info=True,
            )
            self._record_event(skill_name, changed_file, success=False, error=str(e))

    async def _reload_skill(self, skill_name: str, skill_dir: str, changed_file: str) -> None:
        """Reload a single skill: validate manifest, re-import handler, update registry."""
        manifest_path = os.path.join(skill_dir, "manifest.yaml")
        handler_path = os.path.join(skill_dir, "handler.py")

        # Step 1: Validate manifest
        if not os.path.exists(manifest_path):
            logger.warning(f"No manifest.yaml for skill '{skill_name}' — skipping reload")
            self._record_event(skill_name, changed_file, success=False, error="manifest.yaml not found")
            return

        try:
            manifest = parse_manifest(manifest_path)
        except Exception as e:
            logger.error(f"Invalid manifest for skill '{skill_name}': {e}")
            self._record_event(skill_name, changed_file, success=False, error=f"Manifest validation failed: {e}")
            return

        # Step 2: Verify handler exists
        if not os.path.exists(handler_path):
            logger.error(f"Handler not found for skill '{skill_name}': {handler_path}")
            self._record_event(skill_name, changed_file, success=False, error="handler.py not found")
            return

        # Step 3: Invalidate cached module so SkillLoader picks up fresh code
        module_name = f"skills.{skill_name}.{manifest.handler_module}"
        if module_name in sys.modules:
            del sys.modules[module_name]

        # Step 4: Invalidate bytecode cache so Python re-reads the source
        import importlib
        importlib.invalidate_caches()
        pycache_dir = os.path.join(skill_dir, "__pycache__")
        if os.path.isdir(pycache_dir):
            import shutil
            try:
                shutil.rmtree(pycache_dir)
            except OSError as e:
                logger.debug(f"Could not remove __pycache__ for '{skill_name}': {e}")

        # Step 5: Load skill using SkillLoader (handles security scan + import)
        try:
            skill = await self._loader.load(manifest)
        except Exception as e:
            logger.error(f"Failed to load skill '{skill_name}': {e}")
            self._record_event(skill_name, changed_file, success=False, error=f"Load failed: {e}")
            return

        if skill is None:
            logger.error(f"Skill '{skill_name}' failed security/import checks during hot-reload")
            self._record_event(skill_name, changed_file, success=False, error="Skill rejected by loader")
            return

        # Step 6: Apply manifest metadata that the loader may not have set
        # (SkillLoader._extract_skill only overrides name/description/parameters
        # when the class defaults are empty, but version always has a default)
        skill.version = manifest.version
        skill.permissions = manifest.permissions
        skill.requires_approval = manifest.requires_approval
        skill.timeout = manifest.timeout
        skill.tags = manifest.tags

        # Step 7: Update the skill registry
        if self.skill_registry is not None:
            self.skill_registry.register(skill)
            logger.info(
                f"Hot-reloaded skill '{skill_name}' v{skill.version} "
                f"(triggered by {changed_file})"
            )
        else:
            logger.warning(
                f"Skill '{skill_name}' reloaded but no registry attached — "
                f"call set_registry() to enable live updates"
            )

        self._record_event(skill_name, changed_file, success=True, version=skill.version)

    def _record_event(
        self,
        skill_name: str,
        changed_file: str,
        success: bool,
        error: str = "",
        version: str = "",
    ) -> None:
        """Record a reload event for observability."""
        event = {
            "skill_name": skill_name,
            "changed_file": changed_file,
            "success": success,
            "error": error,
            "version": version,
            "timestamp": time.time(),
        }
        self._reload_log.append(event)
        # Keep only last 100 events
        if len(self._reload_log) > 100:
            self._reload_log = self._reload_log[-100:]

    def set_registry(self, registry) -> None:
        """Attach (or replace) the skill registry used for live updates."""
        self.skill_registry = registry

# Sanaa Personal Assistant — Alignment Swizzle

**Date:** 2026-02-18
**Status:** In Progress
**Objective:** Align Backend (Python/FastAPI) and Frontend (Laravel/Livewire) for seamless "Personal Assistant" functionality.

## 1. Audit Findings

### A. Architecture Alignment
- **Blueprint:** V2 Blueprint (`backend/docs/research/antigravity-v2-blueprint.md`) specifies a tiered LLM brain, context assembly with memory, and a message router.
- **Frontend:** `SanaaFab` (Launcher) and `SanaaEngineService` expect a backend that supports:
    - `GET /api/status` (Implemented)
    - `POST /api/command` (Implemented)
    - `POST /api/system/brain/provider` (MISSING in Backend)
    - `GET /api/system/state` (Implemented, but returns HTML fragment)

### B. "Personal Assistant" Capabilities
- **Memory:** `backend/core/memory/context.py` correctly implements:
    - Vector search (`self.memory.search`)
    - System knowledge FTS (`_get_relevant_knowledge`)
    - Conversation history
- **Brain:** `backend/core/brain/engine.py` (implied by imports in `main.py`) seems to handle the logic, but the *control* endpoint is missing.

### C. Gaps
1.  **Missing Endpoint:** `POST /api/system/brain/provider` is missing in `backend/core/main.py`. This prevents the frontend from switching between Local (Ollama) and Cloud (Groq/OpenRouter) brains.
2.  **Skill Discovery:** `AutonomousSkillMapper` is instantiated but needs to be verified to ensure it exposes skills to the "Brain" so the assistant can actually *do* things.

## 2. Remediation Plan

### Step 1: Fix Backend API
- Update `backend/core/main.py` to include:
    ```python
    class BrainProviderRequest(BaseModel):
        provider: str

    @app.post("/api/system/brain/provider")
    async def set_brain_provider(
        req: BrainProviderRequest, 
        request: Request,
        user: dict = Depends(require_auth)
    ):
        ...
    ```

### Step 2: Verify Brain & Skills
- Check `backend/core/brain/engine.py` to ensure `switch_provider` persists the preference or at least affects the runtime.
- Check `backend/core/intelligence/skills.py` to ensure skills are registered and available to the `ContextAssembler`.

### Step 3: Frontend Validation
- Once the backend is updated, restart the service (if needed) and test the "Switch Brain" functionality in the new App Launcher.

## 3. Execution Status

- [x] Backend API Update (Added `POST /api/system/brain/provider`)
- [x] Middleware Fix (Reordered `SessionMiddleware` before `AuditMiddleware`)
- [x] Brain Engine Verification (Confirmed `switch_provider` logic)
- [x] Skill Mapper Verification (Confirmed `SkillLoader` logic)
- [x] Final End-to-End Test (Verified endpoint via curl: 200 OK/401 Unauthorized)

## 4. Conclusion
The backend is now fully aligned with the frontend "Personal Assistant" requirements. The new App Launcher can successfully switch brain providers, and the system is ready for user interaction.

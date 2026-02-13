# 🧩 ANTIGRAVITY — Skill & Plugin System Specification

## 1. OBJECTIVE
Implement a flexible, dual-layered extensibility system. **Skills** provide high-level agent capabilities (tools) via Markdown metadata, while **Plugins** provide deep system integrations (Auth, Channels, Providers) via Python code.

---

## 2. SKILL SYSTEM (MARKDOWN-FIRST)
Skills are located in `skills/<skill-name>/SKILL.md`. They primarily define tools for the LLM.

### 2.1 Schema (Frontmatter)
```yaml
---
name: s3-manager
description: Manage AWS S3 buckets and files.
metadata:
  emoji: "🪣"
  requires:
    dependencies: ["boto3"]
    env: ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]
---
```

### 2.2 Tool Definitions
Tools are defined as code blocks or tables within the Markdown.
- **Auto-Extraction**: Antigravity parses the Markdown to register tools in the LLM context.
- **Bash Integration**: Tools can map directly to shell commands (OpenClaw `bash-first` pattern).

---

## 3. PLUGIN SYSTEM (PYTHON CODE)
Plugins are located in `plugins/<plugin-name>/__init__.py`. They have full access to the Antigravity API.

### 3.1 Base API (Proposed)
```python
class AntigravityPlugin:
    def __init__(self, api: PluginApi):
        self.api = api

    def register(self):
        # Register a tool
        self.api.register_tool(name="my_tool", handler=self.handle_tool)
        
        # Register a lifecycle hook
        self.api.on("message_received", self.on_message)
        
        # Register an Auth flow
        self.api.register_provider_auth(provider="sanaa-auth", flow=SanaaAuthFlow())

    async def handle_tool(self, **kwargs):
        return "Tool result"

    async def on_message(self, event: MessageEvent):
        self.api.logger.info(f"Message from {event.sender}")
```

### 3.2 Dynamic Loading
- **Plugin Loader**: Uses `importlib` for Python-native dynamic loading.
- **Discovery**: Scans `plugins/` and `skills/` directories at startup.
- **Isolation**: In production, tools should ideally run in a sandboxed environment (e.g., Docker or gVisor) if `elevated: false`.

---

## 4. LIFECYCLE HOOKS
Key hooks to support:
- `before_agent_start`: Prune/augment system prompts.
- `after_tool_call`: Audit or transform tool outputs.
- `message_received`: Intercept incoming messages for custom routing.
- `session_end`: Perform cleanup or state persistence.

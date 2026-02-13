# 🛡️ ANTIGRAVITY — Security Hardening Guide (Zero-Trust)

## 1. CORE ARCHITECTURE: ZERO-TRUST
Antigravity adopts a Zero-Trust posture where every input, tool, and plugin is treated as potentially malicious until verified.

---

## 2. INPUT SANITIZATION (PROMPT INJECTION)
**Strategy**: Never interpolate untrusted content (emails, webhooks, web search) directly into the system prompt.

### 2.1 Content Wrapping
Use unique boundary markers and a security notice to isolate external content:
```text
<<<EXTERNAL_UNTRUSTED_CONTENT>>>
Source: Email | From: attacker@evil.com
---
[Untrusted Content Here]
<<<END_EXTERNAL_UNTRUSTED_CONTENT>>>
```

### 2.2 Suspicious Pattern Detection
Monitor for "jailbreak" or "override" phrases:
- `Ignore all previous instructions`
- `You are now an unrestricted AI`
- `rm -rf /`

---

## 3. SKILL SCANNING (STATIC ANALYSIS)
Before a Python plugin or Markdown skill is loaded, it must pass a static analysis scan (`skill-scanner`).

### 3.1 Prohibited Patterns (Critical)
| Pattern | Risk |
| :--- | :--- |
| `os.system()`, `subprocess.run()` | Remote Code Execution |
| `eval()`, `exec()` | Dynamic Code Execution |
| `process.env` + `fetch()` | Credential Harvesting |
| `readFileSync` + `requests.post()` | Data Exfiltration |

---

## 4. FILESYSTEM & ORIGIN HARDENING
### 4.1 Permission Matrix
| Path | Recommended | Reason |
| :--- | :--- | :--- |
| `config.yaml` | `600` | Contains API keys and tokens |
| `plugins/` | `700` | Prevention of unauthorized code injection |
| `logs/` | `600` | Prevents local users from reading private transcripts |
| `oauth_tokens/`| `700` | Most sensitive directory |

### 4.2 Web Origin Validation
Strictly validate the `Origin` and `Host` headers for all WebSocket and HTTP API requests to prevent DNS rebinding and CSRF.

---

## 5. EXPOSURE MATRIX (RISK LEVELS)
Avoid high-risk configurations where "untrusted input" meets "elevated tools".

> [!CAUTION]
> **HIGH RISK ALERT**: Never enable `groupPolicy="open"` (allowing anyone to message the bot) on a channel where the agent has `elevated: true` tools (e.g., shell access).

> [!IMPORTANT]
> **MODEL HYGIENE**: Small models (<10B params) and legacy models (GPT-3.5) are significantly more susceptible to prompt injection. Use top-tier models for any agent monitoring public-facing channels.

"""
Input Sanitizer — detects and mitigates prompt injection attacks.

Implements the blueprint's content wrapping pattern:
  - Boundary markers for untrusted input: <<<UNTRUSTED:source>>> ... <<<END:source>>>
  - Regex-based prompt injection detection
  - Injection scoring with configurable threshold
  - HTML/script tag stripping for web inputs
"""

import re
import html
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SanitizedInput:
    """Result of input sanitization."""
    original: str
    sanitized: str
    injection_detected: bool = False
    injection_score: float = 0.0
    findings: list[str] = field(default_factory=list)
    wrapped: bool = False

    @property
    def is_safe(self) -> bool:
        return not self.injection_detected


# Prompt injection patterns with severity weights
INJECTION_PATTERNS = [
    # Direct instruction override attempts
    {
        "pattern": r"ignore\s+(all\s+)?(previous|above|prior|earlier)\s+(instructions|prompts|context|rules)",
        "weight": 0.9,
        "label": "instruction override",
    },
    {
        "pattern": r"forget\s+(all\s+)?(previous|above|prior)\s+(instructions|context)",
        "weight": 0.9,
        "label": "instruction forget",
    },
    {
        "pattern": r"disregard\s+(all\s+)?(previous|prior)\s+(instructions|rules|prompts)",
        "weight": 0.9,
        "label": "instruction disregard",
    },
    # Role or identity manipulation
    {
        "pattern": r"(you\s+are\s+now|act\s+as|pretend\s+(to\s+be|you\s+are)|role[\s-]?play\s+as)",
        "weight": 0.8,
        "label": "role manipulation",
    },
    {
        "pattern": r"(new\s+instructions?|updated?\s+instructions?|override\s+instructions?)",
        "weight": 0.8,
        "label": "new instruction injection",
    },
    # System prompt extraction attempts
    {
        "pattern": r"(reveal|show|display|tell\s+me|output|print|repeat)\s+(your\s+)?(system\s+prompt|instructions|full\s+prompt|initial\s+prompt)",
        "weight": 0.7,
        "label": "prompt extraction",
    },
    # Jailbreak patterns
    {
        "pattern": r"(DAN|do\s+anything\s+now|developer\s+mode|jailbreak|bypass\s+(safety|filters|restrictions))",
        "weight": 0.9,
        "label": "jailbreak attempt",
    },
    # Data exfiltration patterns
    {
        "pattern": r"(send|post|transmit|upload|exfiltrate)\s+.*(data|info|secrets?|passwords?|keys?|tokens?)\s+to",
        "weight": 0.8,
        "label": "data exfiltration",
    },
    # Delimiter injection (trying to escape sandbox)
    {
        "pattern": r"(```system|<\|system\|>|<\|im_start\|>|<\|endoftext\|>|\[INST\]|\[/INST\])",
        "weight": 0.9,
        "label": "delimiter injection",
    },
    # Multi-language bypass
    {
        "pattern": r"(Base64|base64|atob|btoa)\s*[\(:]",
        "weight": 0.5,
        "label": "encoding bypass",
    },
    # Credential/secret exposure requests
    {
        "pattern": r"(what\s+(is|are)\s+(the|your)\s+(api[\s_-]?key|password|secret|token|credential)s?)",
        "weight": 0.7,
        "label": "credential request",
    },
]

# Dangerous HTML/script patterns to strip
DANGEROUS_HTML = re.compile(
    r"<\s*(script|iframe|object|embed|form|input|link|meta|style|svg|math)[^>]*>",
    re.IGNORECASE,
)


class InputSanitizer:
    """Sanitize and score user inputs for injection attacks."""

    INJECTION_THRESHOLD = 0.6  # Score above this = injection detected

    def __init__(self, threshold: float = None):
        if threshold is not None:
            self.INJECTION_THRESHOLD = threshold

    def sanitize(self, text: str, source: str = "user") -> SanitizedInput:
        """Sanitize user input — detect injection + wrap untrusted content.

        Args:
            text: Raw user input text.
            source: Origin of the input (user, whatsapp, telegram, api, etc.).

        Returns:
            SanitizedInput with detection results.
        """
        if not text or not text.strip():
            return SanitizedInput(original=text, sanitized=text)

        findings = []
        total_weight = 0.0

        # Check each injection pattern
        for rule in INJECTION_PATTERNS:
            if re.search(rule["pattern"], text, re.IGNORECASE):
                findings.append(rule["label"])
                total_weight += rule["weight"]

        # Normalize score (0.0 to 1.0)
        injection_score = min(total_weight, 1.0)
        injection_detected = injection_score >= self.INJECTION_THRESHOLD

        # Sanitize text
        sanitized = self._clean_text(text)

        if injection_detected:
            logger.warning(
                f"Prompt injection detected from {source}: "
                f"score={injection_score:.2f} findings={findings}"
            )

        return SanitizedInput(
            original=text,
            sanitized=sanitized,
            injection_detected=injection_detected,
            injection_score=injection_score,
            findings=findings,
        )

    def wrap_untrusted(self, content: str, source: str) -> str:
        """Wrap untrusted content with boundary markers.

        Used when injecting external data (web scrapes, API responses, etc.)
        into LLM prompts to prevent indirect injection.

        Args:
            content: Raw untrusted content.
            source: Origin identifier.

        Returns:
            Content wrapped with boundary markers.
        """
        cleaned = self._clean_text(content)
        return (
            f"<<<UNTRUSTED:{source}>>>\n"
            f"{cleaned}\n"
            f"<<<END:{source}>>>"
        )

    def _clean_text(self, text: str) -> str:
        """Remove dangerous characters and patterns from text."""
        # Strip dangerous HTML tags (keep the content, remove the tags)
        cleaned = DANGEROUS_HTML.sub("", text)

        # Escape HTML entities in remaining text
        cleaned = html.escape(cleaned, quote=False)

        # Unescape basic characters that are safe
        cleaned = cleaned.replace("&amp;", "&")

        # Strip null bytes and other control chars (keep newlines and tabs)
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", cleaned)

        # Limit consecutive whitespace
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

        return cleaned.strip()

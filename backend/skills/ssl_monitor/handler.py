import logging
import ssl
import socket
from datetime import datetime
from typing import Dict, Any, Optional

from core.skills.base import BaseSkill, SkillResult
from core.database import Alert
from core.approvals.manager import ApprovalManager

logger = logging.getLogger(__name__)

class SSLMonitorSkill(BaseSkill):
    async def execute(self, params: Dict[str, Any], context: Any) -> SkillResult:
        action = params.get("action")
        domains_str = params.get("domains", "")
        
        domains_to_check = [d.strip() for d in domains_str.split(",") if d.strip()]
        if not domains_to_check and action == "check_domains":
            # Default to tracking known domains if none provided
            domains_to_check = [
                "ai.sanaa.co", "sanaa.co", "sanaa.ug", "finance.sanaa.ug", "kalamba.sanaa.ug", 
                "bukuya.sanaa.ug", "mail.sanaa.co", "baraka.sanaa.co", "documents.kyu.ac.ug.sanaa.co"
            ]

        results = []
        alerts_created = []
        approval_requests = []

        if action in ["check_domains", "list_expiring"]:
            for domain in domains_to_check:
                expiry_days = self._check_expiry_days(domain)
                
                if expiry_days is None:
                    results.append({"domain": domain, "status": "error", "message": "Failed to check"})
                    continue
                    
                status = "ok"
                if expiry_days <= 14:
                    status = "critical"
                elif expiry_days <= 30:
                    status = "warning"
                    
                results.append({"domain": domain, "status": status, "days_remaining": expiry_days})
                
                if status in ["warning", "critical"]:
                    # Create an alert
                    await Alert.create(
                        title=f"SSL Expiry Warning: {domain}",
                        description=f"The SSL certificate for {domain} will expire in {expiry_days} days.",
                        severity="high" if status == "critical" else "medium",
                        source="ssl_monitor"
                    )
                    alerts_created.append(domain)
                    
                    if status == "critical":
                        # Auto-request renewal approval
                        am = ApprovalManager()
                        await am.request_approval(
                            action="renew_ssl",
                            target=domain,
                            details={"days_remaining": expiry_days},
                            channels=["whatsapp", "email"]
                        )
                        approval_requests.append(domain)

            output = "SSL Check Results:\n"
            for r in results:
                if r["status"] == "error":
                    output += f"- {r['domain']}: Extraction Failed\n"
                else:
                    output += f"- {r['domain']}: {r['days_remaining']} days remaining [{r['status'].upper()}]\n"
                    
            if alerts_created:
                output += f"\nCreated alerts for: {', '.join(alerts_created)}"
            if approval_requests:
                output += f"\nRequested auto-renewal approval for: {', '.join(approval_requests)}"

            return SkillResult(
                success=True,
                output=output,
                data={"results": results}
            )
            
        return SkillResult(success=False, error=f"Unknown action: {action}")

    def _check_expiry_days(self, domain: str) -> Optional[int]:
        """Check SSL certificate expiry using Python's ssl module (no subprocess)."""
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((domain, 443), timeout=10) as sock:
                with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                    cert = ssock.getpeercert()

            # cert['notAfter'] format: 'Mar  1 12:00:00 2026 GMT'
            not_after = cert.get("notAfter", "")
            if not not_after:
                return None

            expiry_date = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
            delta = expiry_date - datetime.utcnow()
            return delta.days
        except Exception as e:
            logger.error(f"Error checking SSL for {domain}: {e}")
            return None

handler = SSLMonitorSkill

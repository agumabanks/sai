import logging
import subprocess
from core.skills.base import BaseSkill, SkillContext, SkillResult

logger = logging.getLogger(__name__)

class GithubSkill(BaseSkill):
    name = "github"
    
    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action")
        limit = args.get("limit", 5)
        # Sandbox to the backend directory where the AI operates
        target_dir = "/var/www/ai.sanaa.co/backend"
        
        try:
            if action == "status":
                result = subprocess.run(["git", "status"], cwd=target_dir, capture_output=True, text=True, check=True)
                return SkillResult(success=True, output=result.stdout)
                
            elif action == "log":
                result = subprocess.run(["git", "log", f"-n{limit}", "--oneline"], cwd=target_dir, capture_output=True, text=True, check=True)
                return SkillResult(success=True, output=result.stdout)
                
            elif action == "diff":
                # Only show uncommitted changes
                result = subprocess.run(["git", "diff"], cwd=target_dir, capture_output=True, text=True)
                # Truncate if too long to prevent token overflow
                out = result.stdout[:5000] + "\n...[truncated]" if len(result.stdout) > 5000 else result.stdout
                return SkillResult(success=True, output=out or "No uncommitted changes.")
                
            return SkillResult(success=False, error=f"Unknown action: {action}")
            
        except subprocess.CalledProcessError as e:
            return SkillResult(success=False, error=f"Git command failed: {e.stderr}")
        except Exception as e:
            return SkillResult(success=False, error=str(e))

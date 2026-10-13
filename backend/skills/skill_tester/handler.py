import logging
from typing import Dict, Any

from core.skills.base import BaseSkill, SkillResult

logger = logging.getLogger(__name__)

class SkillTesterSkill(BaseSkill):
    async def execute(self, params: Dict[str, Any], context: Any) -> SkillResult:
        target_skill = params.get("target_skill")
        
        # Load all skills
        await context.brain.ensure_skills_loaded()
        registry = context.brain.skill_registry
        
        if target_skill:
            skills_to_test = [registry.get(target_skill)]
            if not skills_to_test[0]:
                return SkillResult(success=False, error=f"Skill '{target_skill}' not found.")
        else:
            skills_to_test = registry._skills.values()
            
        test_results = []
        total_tests = 0
        passed_tests = 0
        
        for skill in skills_to_test:
            if not getattr(skill, "test_cases", None):
                continue
                
            for case in skill.test_cases:
                total_tests += 1
                case_name = case.get("name", "Unnamed Test")
                args = case.get("args", {})
                expect_success = case.get("expect_success", True)
                
                # Execute the skill
                try:
                    res = await context.brain.execute_skill(
                        name=skill.name,
                        args=args,
                        session_id=context.session_id,
                        execution_mode="skill_tester"
                    )
                    
                    is_success = res.get("success", False)
                    if is_success == expect_success:
                        passed_tests += 1
                        test_results.append(f"✅ {skill.name} - {case_name}: PASSED")
                    else:
                        error_msg = res.get("error", "Unknown error")
                        test_results.append(f"❌ {skill.name} - {case_name}: FAILED (Expected success={expect_success}, got {is_success}. Error: {error_msg})")
                        
                except Exception as e:
                    test_results.append(f"❌ {skill.name} - {case_name}: ERROR ({str(e)})")

        if total_tests == 0:
            return SkillResult(success=True, output="No test_cases found in any evaluated skills.")
            
        summary = f"Skill Test Results: {passed_tests}/{total_tests} passed.\n\n" + "\n".join(test_results)
        
        all_passed = passed_tests == total_tests
        
        return SkillResult(
            success=all_passed, 
            output=summary,
            data={
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failures": total_tests - passed_tests
            }
        )

handler = SkillTesterSkill

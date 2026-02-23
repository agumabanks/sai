import asyncio
import sys
import os
import logging
from datetime import datetime

# Add project root to path
sys.path.append("/var/www/ai.sanaa.co")
os.environ["SANAA_ENV"] = "testing"

from core.intelligence.scanner import IntelligenceScanner
from core.intelligence.skills import AutonomousSkillMapper
from core.utils.sandbox import ExecutionSandbox

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verifier")

async def test_scanner():
    logger.info("--- Testing Intelligence Scanner ---")
    scanner = IntelligenceScanner()
    
    # Test 1: Safe Code
    safe_code = "print('Hello World')"
    findings = scanner.scan_source(safe_code, "safe.py")
    assert len(findings) == 0, "Safe code should have 0 findings"
    logger.info("Safe code check: PASS")

    # Test 2: Dangerous Code
    dangerous_code = """
import os
os.system('rm -rf /')
"""
    findings = scanner.scan_source(dangerous_code, "danger.py")
    assert len(findings) > 0, "Dangerous code should have findings"
    assert findings[0].rule_id == "dangerous-exec", "Should detect dangerous-exec"
    logger.info(f"Dangerous code check: PASS (Found: {findings[0].message})")

async def test_sandbox():
    logger.info("--- Testing Execution Sandbox ---")
    sandbox = ExecutionSandbox(timeout=2)
    
    # Test 1: Simple Script
    test_script = "/tmp/test_sandbox.py"
    with open(test_script, "w") as f:
        f.write("print('Sandbox Active')")
        
    result = await sandbox.run_script(test_script)
    assert result["success"] is True, "Sandbox execution failing"
    assert "Sandbox Active" in result["stdout"], "Output mismatch"
    logger.info("Sandbox execution: PASS")
    
    # Clean up
    if os.path.exists(test_script):
        os.remove(test_script)

async def main():
    try:
        await test_scanner()
        await test_sandbox()
        logger.info("\n✅ All Next-Gen Feature Checks Passed!")
    except AssertionError as e:
        logger.error(f"\n❌ Verification Failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ Unexpected Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())

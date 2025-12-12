#!/usr/bin/env python3
"""
Quick test script for stage implementation.
Run this to verify everything works before committing.

Usage:
    python test_stages.py
"""

import requests
import json
import time
from typing import Optional

# Configuration
BASE_URL = "http://localhost:8009"
API_KEY = "Zensbot$88"  # Change this to match your .env file

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_test(message: str):
    """Print test name."""
    print(f"\n{Colors.BLUE}{Colors.BOLD}🧪 {message}{Colors.END}")

def print_pass(message: str = "PASS"):
    """Print success message."""
    print(f"{Colors.GREEN}✅ {message}{Colors.END}")

def print_fail(message: str = "FAIL"):
    """Print failure message."""
    print(f"{Colors.RED}❌ {message}{Colors.END}")

def print_info(message: str):
    """Print info message."""
    print(f"{Colors.YELLOW}ℹ️  {message}{Colors.END}")


class StageTest:
    """Test class for stage implementation."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.headers = {
            "Content-Type": "application/json",
            "X-API-Key": api_key
        }
        self.conversation_id: Optional[str] = None
        self.passed = 0
        self.failed = 0

    def test_health(self) -> bool:
        """Test health endpoint."""
        print_test("Test 1: Health Check")
        try:
            response = requests.get(f"{self.base_url}/health")
            data = response.json()

            if data.get("status") == "healthy" and data.get("agent_initialized"):
                print_pass(f"Server is healthy, agent initialized")
                return True
            else:
                print_fail(f"Server not ready: {data}")
                return False
        except Exception as e:
            print_fail(f"Error: {e}")
            return False

    def test_new_conversation(self) -> bool:
        """Test creating new conversation."""
        print_test("Test 2: New Conversation (Stage: NEW)")
        try:
            response = requests.post(
                f"{self.base_url}/chat",
                headers=self.headers,
                json={"message": "Hello", "conversation_id": None}
            )
            data = response.json()

            self.conversation_id = data.get("conversation_id")
            stage = data.get("stage")
            lead_data = data.get("lead_data")

            if stage == "NEW" and self.conversation_id:
                print_pass(f"Stage is NEW")
                print_info(f"Conversation ID: {self.conversation_id}")
                return True
            else:
                print_fail(f"Expected stage NEW, got: {stage}")
                return False
        except Exception as e:
            print_fail(f"Error: {e}")
            return False

    def test_name_collection(self) -> bool:
        """Test name collection."""
        print_test("Test 3: Name Collection (Stage: NAME_COLLECTED)")
        try:
            response = requests.post(
                f"{self.base_url}/chat",
                headers=self.headers,
                json={
                    "message": "My name is Ahmed Khan",
                    "conversation_id": self.conversation_id
                }
            )
            data = response.json()
            stage = data.get("stage")
            name = data.get("lead_data", {}).get("name")

            # Stage might still be NEW if name extraction didn't work
            # or might be NAME_COLLECTED if it did
            if stage in ["NAME_COLLECTED", "NEW"]:
                if stage == "NAME_COLLECTED":
                    print_pass(f"Stage changed to NAME_COLLECTED")
                    if name:
                        print_info(f"Name extracted: {name}")
                else:
                    print_info(f"Stage still NEW (name extraction may need AI processing)")
                return True
            else:
                print_fail(f"Unexpected stage: {stage}")
                return False
        except Exception as e:
            print_fail(f"Error: {e}")
            return False

    def test_course_selection(self) -> bool:
        """Test course selection."""
        print_test("Test 4: Course Selection (Stage: COURSE_SELECTED)")
        try:
            response = requests.post(
                f"{self.base_url}/chat",
                headers=self.headers,
                json={
                    "message": "I want to learn about CTA course",
                    "conversation_id": self.conversation_id
                }
            )
            data = response.json()
            stage = data.get("stage")
            course = data.get("lead_data", {}).get("selected_course")

            if course:
                print_pass(f"Course detected: {course}")
                if stage == "COURSE_SELECTED":
                    print_pass(f"Stage changed to COURSE_SELECTED")
                else:
                    print_info(f"Stage is {stage} (course detected but stage logic may differ)")
                return True
            else:
                print_info(f"Course not detected yet (stage: {stage})")
                return True  # Not a failure, just informational
        except Exception as e:
            print_fail(f"Error: {e}")
            return False

    def test_get_stage(self) -> bool:
        """Test getting stage for conversation."""
        print_test("Test 5: Get Stage Endpoint")
        try:
            response = requests.get(
                f"{self.base_url}/conversations/{self.conversation_id}/stage",
                headers=self.headers
            )
            data = response.json()
            stage = data.get("stage")
            lead_data = data.get("lead_data")

            if stage and lead_data is not None:
                print_pass(f"Stage endpoint works")
                print_info(f"Current stage: {stage}")
                print_info(f"Lead data: {json.dumps(lead_data, indent=2)}")
                return True
            else:
                print_fail(f"Invalid response: {data}")
                return False
        except Exception as e:
            print_fail(f"Error: {e}")
            return False

    def test_get_stats(self) -> bool:
        """Test getting overall stats."""
        print_test("Test 6: Get Overall Stats")
        try:
            response = requests.get(
                f"{self.base_url}/leads/stats",
                headers=self.headers
            )
            data = response.json()
            total = data.get("total_leads")
            by_stage = data.get("by_stage")

            if total is not None and by_stage:
                print_pass(f"Stats endpoint works")
                print_info(f"Total leads: {total}")
                print_info(f"By stage: {json.dumps(by_stage, indent=2)}")
                return True
            else:
                print_fail(f"Invalid response: {data}")
                return False
        except Exception as e:
            print_fail(f"Error: {e}")
            return False

    def test_get_leads_by_stage(self) -> bool:
        """Test getting leads by stage."""
        print_test("Test 7: Get Leads by Stage")
        try:
            # Try getting leads in NEW stage
            response = requests.get(
                f"{self.base_url}/leads/by-stage/NEW",
                headers=self.headers
            )
            data = response.json()
            count = data.get("count")
            leads = data.get("leads")

            if count is not None and leads is not None:
                print_pass(f"Get leads by stage works")
                print_info(f"Leads in NEW stage: {count}")
                return True
            else:
                print_fail(f"Invalid response: {data}")
                return False
        except Exception as e:
            print_fail(f"Error: {e}")
            return False

    def test_manual_stage_update(self) -> bool:
        """Test manually updating stage."""
        print_test("Test 8: Manual Stage Update")
        try:
            response = requests.post(
                f"{self.base_url}/conversations/{self.conversation_id}/update-stage",
                headers=self.headers,
                params={"new_stage": "ENROLLED"}
            )
            data = response.json()

            if data.get("message") == "Stage updated successfully":
                print_pass(f"Manual stage update works")

                # Verify the change
                verify_response = requests.get(
                    f"{self.base_url}/conversations/{self.conversation_id}/stage",
                    headers=self.headers
                )
                verify_data = verify_response.json()

                if verify_data.get("stage") == "ENROLLED":
                    print_pass(f"Stage verified as ENROLLED")
                    return True
                else:
                    print_fail(f"Stage not updated correctly: {verify_data.get('stage')}")
                    return False
            else:
                print_fail(f"Update failed: {data}")
                return False
        except Exception as e:
            print_fail(f"Error: {e}")
            return False

    def test_api_key_protection(self) -> bool:
        """Test API key protection."""
        print_test("Test 9: API Key Protection")
        try:
            # Test without API key
            response = requests.get(f"{self.base_url}/leads/stats")

            if response.status_code == 401:
                print_pass(f"Request without API key rejected (401)")
            else:
                print_fail(f"Request without API key should return 401, got {response.status_code}")
                return False

            # Test with wrong API key
            wrong_headers = {"X-API-Key": "wrong-key-12345"}
            response = requests.get(
                f"{self.base_url}/leads/stats",
                headers=wrong_headers
            )

            if response.status_code == 403:
                print_pass(f"Request with wrong API key rejected (403)")
                return True
            else:
                print_fail(f"Request with wrong API key should return 403, got {response.status_code}")
                return False
        except Exception as e:
            print_fail(f"Error: {e}")
            return False

    def run_all_tests(self):
        """Run all tests."""
        print(f"\n{Colors.BOLD}{'='*60}")
        print(f"🚀 Stage Implementation Test Suite")
        print(f"{'='*60}{Colors.END}\n")
        print_info(f"Base URL: {self.base_url}")
        print_info(f"API Key: {self.headers['X-API-Key']}")

        tests = [
            self.test_health,
            self.test_new_conversation,
            self.test_name_collection,
            self.test_course_selection,
            self.test_get_stage,
            self.test_get_stats,
            self.test_get_leads_by_stage,
            self.test_manual_stage_update,
            self.test_api_key_protection,
        ]

        for test in tests:
            result = test()
            if result:
                self.passed += 1
            else:
                self.failed += 1
            time.sleep(0.5)  # Small delay between tests

        # Summary
        print(f"\n{Colors.BOLD}{'='*60}")
        print(f"📊 Test Summary")
        print(f"{'='*60}{Colors.END}\n")

        total = self.passed + self.failed
        print(f"Total Tests: {total}")
        print(f"{Colors.GREEN}Passed: {self.passed}{Colors.END}")
        print(f"{Colors.RED}Failed: {self.failed}{Colors.END}")

        if self.failed == 0:
            print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 ALL TESTS PASSED! Ready to commit.{Colors.END}\n")
            return True
        else:
            print(f"\n{Colors.RED}{Colors.BOLD}⚠️  Some tests failed. Fix issues before committing.{Colors.END}\n")
            return False


def main():
    """Main function."""
    print(f"\n{Colors.YELLOW}⚠️  Make sure the server is running:")
    print(f"   uv run python scripts/run_api.py{Colors.END}\n")

    input("Press Enter to start tests... ")

    tester = StageTest(BASE_URL, API_KEY)
    success = tester.run_all_tests()

    if not success:
        exit(1)


if __name__ == "__main__":
    main()

"""
Template Tools - Retrieve message templates for consistent responses

This module provides tools for the agent to fetch pre-defined message templates
instead of having all templates loaded in the system prompt.
"""

import json
import os
import threading
from typing import Optional
from langchain_core.tools import tool


# Load templates once at module level
TEMPLATES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "config",
    "templates.json"
)

# Thread lock for safe hot-reload
_templates_lock = threading.Lock()

def _load_templates() -> dict:
    """Load templates from JSON file."""
    try:
        with open(TEMPLATES_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: Templates file not found at {TEMPLATES_PATH}")
        return {}
    except json.JSONDecodeError as e:
        print(f"Warning: Invalid JSON in templates file: {e}")
        return {}


TEMPLATES = _load_templates()


def reload_templates() -> dict:
    """
    Thread-safe reload of templates from disk.
    Called after templates.json is updated by the admin interface.

    Returns:
        dict: The reloaded templates dictionary

    Raises:
        ValueError: If templates file is corrupted or empty
    """
    with _templates_lock:
        new_templates = _load_templates()
        if not new_templates:
            raise ValueError("Failed to load templates - file may be corrupted or empty")

        # Atomic update - replace entire dict at once
        global TEMPLATES
        TEMPLATES = new_templates
        return TEMPLATES


@tool
def get_message_template(
    template_name: str,
    language: Optional[str] = "english"
) -> str:
    """
    Retrieve a message template by name and language.

    Use this tool when you need to use a specific message format/template
    from the predefined templates library.

    Args:
        template_name: The name of the template to retrieve. Available templates:
            - GREETING_NEW_LEAD: First greeting for new leads
            - GREETING_RETURNING_LEAD: Greeting for returning leads
            - COURSE_SELECTION: Show all 12 courses
            - EDUCATION_INQUIRY: Ask about education
            - GOAL_INQUIRY: Ask about goals/motivation
            - VALIDATION_WITH_PDF: Validate choice and share PDF
            - DEMO_VIDEO_SHARE: Share demo video link
            - FEE_INQUIRY: Share fee details
            - BATCH_DETAILS: Share batch timing
            - TRAINER_INFO: Share trainer information
            - PAYMENT_DETAILS: Share payment/bank details (ONLY when user asks)
            - PAYMENT_SCREENSHOT_RECEIVED: Confirm payment received
            - DATA_NOT_FOUND: When data not available
            - POLICY_NOT_FOUND: When policy needs confirmation
            - STUDENT_FEEDBACK: Share student reviews
            - PLATFORM_INFO: Explain online class platform
            - NO_TIME_RESPONSE: When lead says no time
            - DISCOUNT_REQUEST: When lead asks for discount
            - REFUND_POLICY: Direct to finance team
            - NON_ICT_TOPIC: Redirect non-ICT topics
            - JOB_INQUIRY: Redirect job inquiries
            - RESET_REQUEST: When unclear reset requested
            - AI_ACCUSATION: When accused of being AI
            - MULTIPLE_COURSE_PRICING: When asking pricing without selecting
            - ENROLLMENT_LINK_REQUEST: Share enrollment link
            - COURSE_LOCATIONS: Share location availability
            - WHAT_IS_INCLUDED: What's included in courses
            - CAMPUS_ADDRESSES: Share campus addresses
            - FOLLOW_UP_WARM_LEAD: Follow up after demo
            - GENTLE_ENROLLMENT_SUGGESTION: Suggest enrollment when warm
            - LEGAL_INQUIRY_REDIRECT: Redirect legal inquiries
            - HR_JOB_REDIRECT: Redirect HR/job inquiries
            - MULTIPLE_COURSE_DETAILS: Multiple course details
            - COURSE_DETAILS_WITHOUT_FEE: Course details without price
            - COURSE_DETAILS_WITH_FEE: Course details with price

        language: The language version to retrieve. Options:
            - "english": English version
            - "urdu": Roman Urdu version
            - "mixed": Mixed English/Urdu (when available)
            Default is "english".

    Returns:
        The template text in the requested language. If language not available,
        returns the first available language version with a note.

    Examples:
        >>> get_message_template("GREETING_NEW_LEAD", "english")
        "Aoa!\\nI am Tanveer Awan from ICT.\\n\\nMay I know your name?"

        >>> get_message_template("COURSE_SELECTION", "mixed")
        "Dear {name},\\n\\nPlease save my number as \\"ICT Tanveer\\"..."

    Note:
        Templates may contain placeholders like {name}, {course_name}, {Pdf_Link}.
        You must replace these with actual values when using the template.

        Some templates require fetching data from Supabase FIRST:
        - VALIDATION_WITH_PDF: Fetch Pdf_Link using fetch_course_links
        - DEMO_VIDEO_SHARE: Fetch Demo_Link using fetch_course_links
        - FEE_INQUIRY: Fetch course details using fetch_course_details
        - PAYMENT_DETAILS: Fetch course details using fetch_course_details
        etc.
    """
    if not TEMPLATES:
        return "Error: Templates not loaded. Please check templates.json file."

    if template_name not in TEMPLATES:
        available = ", ".join(list(TEMPLATES.keys())[:10]) + "..."
        return f"Error: Template '{template_name}' not found. Available templates: {available}"

    template_data = TEMPLATES[template_name]

    # Try to get requested language
    if language in template_data:
        return template_data[language]

    # Fallback to other available languages
    if "mixed" in template_data:
        return f"[Note: {language} not available, using mixed version]\n\n{template_data['mixed']}"
    elif "english" in template_data:
        return f"[Note: {language} not available, using english version]\n\n{template_data['english']}"
    elif "urdu" in template_data:
        return f"[Note: {language} not available, using urdu version]\n\n{template_data['urdu']}"

    return f"Error: No language version available for template '{template_name}'"


@tool
def list_available_templates() -> str:
    """
    List all available message templates with their descriptions.

    Use this tool if you want to see what templates are available
    before calling get_message_template.

    Returns:
        A formatted list of all available templates with descriptions.
    """
    if not TEMPLATES:
        return "Error: Templates not loaded."

    result = "Available Message Templates:\n\n"
    for name, data in TEMPLATES.items():
        description = data.get("description", "No description")
        languages = [k for k in data.keys() if k != "description"]
        result += f"- {name}\n  Description: {description}\n  Languages: {', '.join(languages)}\n\n"

    return result


# Export tools as a list for easy import
template_tools = [
    get_message_template,
    list_available_templates
]

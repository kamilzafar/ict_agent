"""Template Manager - Thread-safe CRUD operations for message templates

This module provides centralized template management with:
- Thread-safe file operations
- Atomic writes (temp + rename pattern)
- Windows compatibility
- Automatic backups
- Hot-reload triggering
"""

import os
import json
import sys
import time
import threading
import shutil
import logging
from typing import Dict, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class TemplateManager:
    """Manages template CRUD operations with thread-safety and atomic writes.

    Follows the same atomic write patterns as LongTermMemory in core/memory.py
    to ensure reliability and Windows compatibility.
    """

    def __init__(self, templates_path: str):
        """Initialize the template manager.

        Args:
            templates_path: Path to templates.json file
        """
        self.templates_path = templates_path
        self.backup_path = templates_path + ".backup"
        self._file_lock = threading.Lock()

        # Validate templates file exists
        if not os.path.exists(templates_path):
            raise FileNotFoundError(f"Templates file not found: {templates_path}")

    def _load_templates(self) -> dict:
        """Load templates from JSON file.

        Returns:
            dict: Templates dictionary

        Raises:
            json.JSONDecodeError: If JSON is invalid
            FileNotFoundError: If file doesn't exist
        """
        with open(self.templates_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save_templates(self, templates: dict, create_backup: bool = True):
        """Thread-safe atomic write following memory.py pattern.

        Uses temp file + rename for atomicity. Windows-compatible with retry logic.

        Args:
            templates: Templates dictionary to save
            create_backup: Whether to create backup before writing

        Raises:
            ValueError: If template data is not serializable
            RuntimeError: If file write fails after retries
        """
        with self._file_lock:
            # Validate JSON serializability first
            try:
                json_data = json.dumps(templates, indent=2, ensure_ascii=False)
            except Exception as e:
                raise ValueError(f"Invalid template data: {e}")

            # Create backup before modifying
            if create_backup and os.path.exists(self.templates_path):
                try:
                    shutil.copy2(self.templates_path, self.backup_path)
                    logger.info(f"Created backup: {self.backup_path}")
                except Exception as e:
                    logger.warning(f"Failed to create backup: {e}")
                    # Continue anyway - backup failure shouldn't block the update

            # Atomic write with Windows compatibility
            # This pattern matches memory.py lines 120-161
            temp_file = self.templates_path + ".tmp"
            max_retries = 3
            retry_delay = 0.1

            try:
                # Write to temp file
                with open(temp_file, 'w', encoding='utf-8') as f:
                    f.write(json_data)

                # Atomic replace with retry logic for Windows
                for attempt in range(max_retries):
                    try:
                        if sys.platform == "win32" and os.path.exists(self.templates_path):
                            # Windows-specific: remove then rename
                            try:
                                os.remove(self.templates_path)
                            except PermissionError:
                                if attempt < max_retries - 1:
                                    time.sleep(retry_delay * (attempt + 1))
                                    continue
                                else:
                                    raise
                            os.rename(temp_file, self.templates_path)
                        else:
                            # Unix-like systems: atomic replace
                            os.replace(temp_file, self.templates_path)

                        # Success - break out of retry loop
                        break

                    except (PermissionError, OSError) as e:
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay * (attempt + 1))
                            continue
                        else:
                            raise

            except Exception as e:
                # Clean up temp file on error
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except Exception:
                        pass
                raise RuntimeError(f"Failed to save templates: {e}")

            logger.info(f"Successfully saved templates to {self.templates_path}")

            # Trigger hot-reload in template_tools.py
            try:
                from tools.template_tools import reload_templates
                reload_templates()
                logger.info("Templates reloaded in memory")
            except Exception as e:
                logger.error(f"Failed to reload templates: {e}")
                raise RuntimeError(f"Templates saved but hot-reload failed: {e}")

    def get_all_templates(self) -> dict:
        """Get all templates from file.

        Returns:
            dict: All templates

        Raises:
            json.JSONDecodeError: If JSON is invalid
            FileNotFoundError: If file doesn't exist
        """
        return self._load_templates()

    def get_template(self, name: str) -> Optional[dict]:
        """Get single template by name.

        Args:
            name: Template name (e.g., "GREETING_NEW_LEAD")

        Returns:
            dict: Template data or None if not found
        """
        templates = self._load_templates()
        return templates.get(name)

    def create_template(self, name: str, data: dict) -> bool:
        """Create new template.

        Args:
            name: Template name (UPPERCASE_SNAKE_CASE)
            data: Template data (description, language versions)

        Returns:
            bool: True if created successfully

        Raises:
            ValueError: If template already exists or data is invalid
            RuntimeError: If save fails
        """
        templates = self._load_templates()

        if name in templates:
            raise ValueError(f"Template '{name}' already exists")

        # Validate template data has at least description
        if "description" not in data:
            raise ValueError("Template must have a 'description' field")

        # Validate at least one language version exists
        language_fields = [k for k in data.keys() if k != "description"]
        if not language_fields:
            raise ValueError("Template must have at least one language version (english, urdu, or mixed)")

        templates[name] = data
        self._save_templates(templates)

        logger.info(f"Created template: {name}")
        return True

    def update_template(self, name: str, data: dict) -> bool:
        """Update existing template.

        Args:
            name: Template name
            data: Template data to update (partial updates supported)

        Returns:
            bool: True if updated successfully

        Raises:
            ValueError: If template not found
            RuntimeError: If save fails
        """
        templates = self._load_templates()

        if name not in templates:
            raise ValueError(f"Template '{name}' not found")

        # Merge with existing template (allows partial updates)
        templates[name].update(data)

        # Ensure description still exists
        if "description" not in templates[name]:
            raise ValueError("Template must have a 'description' field")

        self._save_templates(templates)

        logger.info(f"Updated template: {name}")
        return True

    def delete_template(self, name: str) -> bool:
        """Delete template.

        Args:
            name: Template name

        Returns:
            bool: True if deleted successfully

        Raises:
            ValueError: If template not found
            RuntimeError: If save fails
        """
        templates = self._load_templates()

        if name not in templates:
            raise ValueError(f"Template '{name}' not found")

        del templates[name]
        self._save_templates(templates)

        logger.info(f"Deleted template: {name}")
        return True

    def template_exists(self, name: str) -> bool:
        """Check if template exists.

        Args:
            name: Template name

        Returns:
            bool: True if template exists
        """
        templates = self._load_templates()
        return name in templates

    def get_template_count(self) -> int:
        """Get total number of templates.

        Returns:
            int: Template count
        """
        templates = self._load_templates()
        return len(templates)

    def validate_template_name(self, name: str) -> bool:
        """Validate template name format.

        Template names should be UPPERCASE_SNAKE_CASE.

        Args:
            name: Template name to validate

        Returns:
            bool: True if valid
        """
        if not name:
            return False

        # Check UPPERCASE_SNAKE_CASE format
        if not name.isupper():
            return False

        # Check only contains A-Z, 0-9, and underscore
        import re
        if not re.match(r'^[A-Z0-9_]+$', name):
            return False

        return True

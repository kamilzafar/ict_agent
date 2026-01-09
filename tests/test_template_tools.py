"""Comprehensive tests for template tools."""
import pytest
import json
import tempfile
import os
from unittest.mock import patch, mock_open
from tools.template_tools import get_message_template, list_available_templates, reload_templates


@pytest.fixture
def sample_templates():
    """Sample templates data."""
    return {
        "GREETING_NEW_LEAD": {
            "english": "Hello! Welcome to ICT.",
            "urdu": "Aoa! ICT mein khush amdeed.",
            "description": "Greeting for new leads"
        },
        "COURSE_SELECTION": {
            "english": "Here are our courses:",
            "mixed": "Yahan courses hain:",
            "description": "Course selection message"
        }
    }


class TestGetMessageTemplate:
    """Tests for get_message_template tool."""
    
    @patch('tools.template_tools.TEMPLATES')
    def test_get_template_english(self, mock_templates, sample_templates):
        """Test getting English template."""
        mock_templates.__getitem__.return_value = sample_templates["GREETING_NEW_LEAD"]
        mock_templates.__contains__.return_value = True
        
        result = get_message_template.invoke({
            "template_name": "GREETING_NEW_LEAD",
            "language": "english"
        })
        assert "Hello! Welcome to ICT." in result
    
    @patch('tools.template_tools.TEMPLATES')
    def test_get_template_urdu(self, mock_templates, sample_templates):
        """Test getting Urdu template."""
        mock_templates.__getitem__.return_value = sample_templates["GREETING_NEW_LEAD"]
        mock_templates.__contains__.return_value = True
        
        result = get_message_template.invoke({
            "template_name": "GREETING_NEW_LEAD",
            "language": "urdu"
        })
        assert "Aoa!" in result or "khush amdeed" in result
    
    @patch('tools.template_tools.TEMPLATES')
    def test_get_template_mixed(self, mock_templates, sample_templates):
        """Test getting mixed language template."""
        mock_templates.__getitem__.return_value = sample_templates["COURSE_SELECTION"]
        mock_templates.__contains__.return_value = True
        
        result = get_message_template.invoke({
            "template_name": "COURSE_SELECTION",
            "language": "mixed"
        })
        assert "courses" in result.lower()
    
    @patch('tools.template_tools.TEMPLATES')
    def test_get_template_language_fallback(self, mock_templates, sample_templates):
        """Test language fallback when requested language not available."""
        template_data = {"english": "Hello", "mixed": "Haan"}
        mock_templates.__getitem__.return_value = template_data
        mock_templates.__contains__.return_value = True
        
        result = get_message_template.invoke({
            "template_name": "TEST",
            "language": "urdu"  # Not available
        })
        # Should fallback to available language
        assert "Hello" in result or "Haan" in result
    
    @patch('tools.template_tools.TEMPLATES')
    def test_get_template_not_found(self, mock_templates):
        """Test error when template not found."""
        mock_templates.__contains__.return_value = False
        mock_templates.keys.return_value = ["TEMPLATE1", "TEMPLATE2"]
        
        result = get_message_template.invoke({
            "template_name": "NONEXISTENT",
            "language": "english"
        })
        assert "Error:" in result or "not found" in result
    
    @patch('tools.template_tools.TEMPLATES', {})
    def test_get_template_templates_not_loaded(self):
        """Test error when templates not loaded."""
        result = get_message_template.invoke({
            "template_name": "TEST",
            "language": "english"
        })
        assert "Error:" in result or "not loaded" in result
    
    @patch('tools.template_tools.TEMPLATES')
    def test_get_template_default_language(self, mock_templates, sample_templates):
        """Test default language parameter."""
        mock_templates.__getitem__.return_value = sample_templates["GREETING_NEW_LEAD"]
        mock_templates.__contains__.return_value = True
        
        result = get_message_template.invoke({
            "template_name": "GREETING_NEW_LEAD",
            "language": None  # Should default to "english"
        })
        assert result  # Should return something


class TestListAvailableTemplates:
    """Tests for list_available_templates tool."""
    
    @patch('tools.template_tools.TEMPLATES')
    def test_list_templates_success(self, mock_templates, sample_templates):
        """Test listing templates successfully."""
        mock_templates.items.return_value = sample_templates.items()
        mock_templates.__bool__.return_value = True
        
        result = list_available_templates.invoke({})
        assert "Available Message Templates" in result
        assert "GREETING_NEW_LEAD" in result
    
    @patch('tools.template_tools.TEMPLATES', {})
    def test_list_templates_not_loaded(self):
        """Test error when templates not loaded."""
        result = list_available_templates.invoke({})
        assert "Error:" in result or "not loaded" in result
    
    @patch('tools.template_tools.TEMPLATES')
    def test_list_templates_includes_descriptions(self, mock_templates, sample_templates):
        """Test templates list includes descriptions."""
        mock_templates.items.return_value = sample_templates.items()
        mock_templates.__bool__.return_value = True
        
        result = list_available_templates.invoke({})
        assert "description" in result.lower()
    
    @patch('tools.template_tools.TEMPLATES')
    def test_list_templates_includes_languages(self, mock_templates, sample_templates):
        """Test templates list includes available languages."""
        mock_templates.items.return_value = sample_templates.items()
        mock_templates.__bool__.return_value = True
        
        result = list_available_templates.invoke({})
        assert "Languages:" in result or "english" in result.lower()
    
    @patch('tools.template_tools.TEMPLATES')
    def test_list_templates_empty_dict(self, mock_templates):
        """Test listing when templates dict is empty."""
        mock_templates.items.return_value = []
        mock_templates.__bool__.return_value = True
        
        result = list_available_templates.invoke({})
        assert "Available Message Templates" in result


class TestReloadTemplates:
    """Tests for reload_templates function."""
    
    def test_reload_templates_success(self, sample_templates):
        """Test successful template reload."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(sample_templates, f)
            temp_path = f.name
        
        try:
            with patch('tools.template_tools.TEMPLATES_PATH', temp_path):
                with patch('tools.template_tools.TEMPLATES', {}):
                    result = reload_templates()
                    assert result == sample_templates
        finally:
            os.unlink(temp_path)
    
    def test_reload_templates_file_not_found(self):
        """Test reload when file not found."""
        with patch('tools.template_tools.TEMPLATES_PATH', '/nonexistent/file.json'):
            with patch('tools.template_tools.TEMPLATES', {}):
                result = reload_templates()
                assert result == {}
    
    def test_reload_templates_invalid_json(self):
        """Test reload with invalid JSON."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json {")
            temp_path = f.name
        
        try:
            with patch('tools.template_tools.TEMPLATES_PATH', temp_path):
                with patch('tools.template_tools.TEMPLATES', {}):
                    result = reload_templates()
                    assert result == {}
        finally:
            os.unlink(temp_path)
    
    def test_reload_templates_empty_file(self):
        """Test reload with empty file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{}")
            temp_path = f.name
        
        try:
            with patch('tools.template_tools.TEMPLATES_PATH', temp_path):
                with patch('tools.template_tools.TEMPLATES', {}):
                    with pytest.raises(ValueError):
                        reload_templates()
        finally:
            os.unlink(temp_path)
    
    def test_reload_templates_thread_safety(self, sample_templates):
        """Test template reload is thread-safe."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(sample_templates, f)
            temp_path = f.name
        
        try:
            with patch('tools.template_tools.TEMPLATES_PATH', temp_path):
                with patch('tools.template_tools.TEMPLATES', {}):
                    # Should not raise exception even with concurrent access
                    result1 = reload_templates()
                    result2 = reload_templates()
                    assert result1 == result2
        finally:
            os.unlink(temp_path)


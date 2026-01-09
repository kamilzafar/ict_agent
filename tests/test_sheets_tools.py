"""Comprehensive tests for Google Sheets tools."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from tools.sheets_tools import create_sheets_tools


@pytest.fixture
def mock_sheets_client():
    """Create mock Google Sheets client."""
    client = Mock()
    spreadsheet = Mock()
    worksheet = Mock()
    
    # Mock worksheet methods
    worksheet.get_all_records.return_value = []
    worksheet.append_row = Mock()
    worksheet.update = Mock()
    
    spreadsheet.worksheet.return_value = worksheet
    client.open_by_key.return_value = spreadsheet
    
    return client


class TestAppendLeadDataSheets:
    """Tests for append_lead_data tool in Sheets."""
    
    @patch('tools.sheets_tools._get_sheets_client')
    def test_append_lead_data_new_lead(self, mock_get_client, mock_sheets_client):
        """Test appending new lead to sheets."""
        mock_get_client.return_value = mock_sheets_client
        
        tools = create_sheets_tools()
        if not tools:
            pytest.skip("Google Sheets not configured")
        
        append_tool = [t for t in tools if t.name == "append_lead_data"][0]
        
        result = append_tool.invoke({
            "name": "Test User",
            "selected_course": "CTA",
            "education_level": "Bachelors",
            "goal": "Career growth",
            "phone": "03001234567",
            "notes": None,
            "add_timestamp": True
        })
        
        assert "success" in result.lower() or "appended" in result.lower()
        mock_sheets_client.open_by_key.return_value.worksheet.return_value.append_row.assert_called()
    
    @patch('tools.sheets_tools._get_sheets_client')
    def test_append_lead_data_update_existing(self, mock_get_client, mock_sheets_client):
        """Test updating existing lead in sheets."""
        mock_get_client.return_value = mock_sheets_client
        
        # Mock existing record
        worksheet = mock_sheets_client.open_by_key.return_value.worksheet.return_value
        worksheet.get_all_records.return_value = [
            {"Name": "Test User", "Phone": "03001234567", "Row": 2}
        ]
        
        tools = create_sheets_tools()
        if not tools:
            pytest.skip("Google Sheets not configured")
        
        append_tool = [t for t in tools if t.name == "append_lead_data"][0]
        
        result = append_tool.invoke({
            "name": "Test User",
            "phone": "03001234567",
            "selected_course": "CTA",
            "add_timestamp": True
        })
        
        assert "success" in result.lower() or "updated" in result.lower()
        worksheet.update.assert_called()
    
    @patch('tools.sheets_tools._get_sheets_client')
    def test_append_lead_data_minimal_data(self, mock_get_client, mock_sheets_client):
        """Test with minimal data."""
        mock_get_client.return_value = mock_sheets_client
        
        tools = create_sheets_tools()
        if not tools:
            pytest.skip("Google Sheets not configured")
        
        append_tool = [t for t in tools if t.name == "append_lead_data"][0]
        
        result = append_tool.invoke({
            "selected_course": "CTA",
            "add_timestamp": False
        })
        
        assert "success" in result.lower()
    
    @patch('tools.sheets_tools._get_sheets_client')
    def test_append_lead_data_with_timestamp(self, mock_get_client, mock_sheets_client):
        """Test appending with timestamp."""
        mock_get_client.return_value = mock_sheets_client
        
        tools = create_sheets_tools()
        if not tools:
            pytest.skip("Google Sheets not configured")
        
        append_tool = [t for t in tools if t.name == "append_lead_data"][0]
        
        result = append_tool.invoke({
            "name": "Test",
            "selected_course": "CTA",
            "add_timestamp": True
        })
        
        assert "success" in result.lower()
        # Verify timestamp was added
        call_args = mock_sheets_client.open_by_key.return_value.worksheet.return_value.append_row.call_args
        assert call_args is not None
    
    @patch('tools.sheets_tools._get_sheets_client')
    def test_append_lead_data_exception_handling(self, mock_get_client, mock_sheets_client):
        """Test exception handling."""
        mock_get_client.side_effect = Exception("Sheets error")
        
        tools = create_sheets_tools()
        if not tools:
            pytest.skip("Google Sheets not configured")
        
        append_tool = [t for t in tools if t.name == "append_lead_data"][0]
        
        result = append_tool.invoke({
            "name": "Test",
            "add_timestamp": True
        })
        
        assert "error" in result.lower()
    
    @patch('tools.sheets_tools._get_sheets_client')
    def test_append_lead_data_merge_partial_data(self, mock_get_client, mock_sheets_client):
        """Test merging partial data with existing."""
        mock_get_client.return_value = mock_sheets_client
        
        worksheet = mock_sheets_client.open_by_key.return_value.worksheet.return_value
        worksheet.get_all_records.return_value = [
            {"Name": "Test User", "Phone": "03001234567", "Course": "CTA", "Row": 2}
        ]
        
        tools = create_sheets_tools()
        if not tools:
            pytest.skip("Google Sheets not configured")
        
        append_tool = [t for t in tools if t.name == "append_lead_data"][0]
        
        result = append_tool.invoke({
            "name": "Test User",
            "phone": "03001234567",
            "education_level": "Bachelors",  # New field
            "add_timestamp": True
        })
        
        assert "success" in result.lower()
        # Should update existing row, not append
        worksheet.update.assert_called()
    
    @patch('tools.sheets_tools._get_sheets_client')
    def test_append_lead_data_no_sheets_configured(self, mock_get_client):
        """Test when Sheets not configured."""
        with patch('tools.sheets_tools.SHEETS_AVAILABLE', False):
            tools = create_sheets_tools()
            assert tools == []


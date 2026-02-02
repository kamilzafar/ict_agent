"""Comprehensive tests for SupabaseService.append_lead_data method."""
import sys
import os

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set test environment variables before any imports
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-supabase-key")

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime


class TestAppendLeadData:
    """Tests for SupabaseService.append_lead_data method."""

    @pytest.fixture
    def mock_supabase_client(self):
        """Create a mock Supabase client."""
        client = Mock()
        client.table.return_value = client
        client.select.return_value = client
        client.eq.return_value = client
        client.ilike.return_value = client
        client.limit.return_value = client
        client.insert.return_value = client
        client.update.return_value = client
        return client

    @pytest.fixture
    def supabase_service(self, mock_supabase_client):
        """Create SupabaseService with mocked client."""
        with patch('core.supabase_service.create_client') as mock_create:
            mock_create.return_value = mock_supabase_client
            from core.supabase_service import SupabaseService
            service = SupabaseService()
            service.client = mock_supabase_client
            return service

    def test_create_new_lead_with_all_fields(self, supabase_service, mock_supabase_client):
        """Test creating a new lead with all fields populated."""
        # Create separate mocks for select and insert chains
        select_mock = Mock()
        select_mock.eq.return_value = select_mock
        select_mock.ilike.return_value = select_mock
        select_mock.limit.return_value = select_mock
        select_mock.execute.return_value = Mock(data=[])  # No existing lead

        insert_mock = Mock()
        insert_mock.execute.return_value = Mock(
            data=[{'id': 'new-lead-123', 'lead_name': 'John Doe'}]
        )

        def table_side_effect(table_name):
            mock = Mock()
            mock.select.return_value = select_mock
            mock.insert.return_value = insert_mock
            return mock

        mock_supabase_client.table.side_effect = table_side_effect

        result = supabase_service.append_lead_data(
            name="John Doe",
            phone="03001234567",
            selected_course="CTA",
            education_level="Masters",
            goal="Career growth",
            notes="Interested in weekend classes"
        )

        assert result['status'] == 'success'
        assert result['action'] == 'created'
        assert result['lead_id'] == 'new-lead-123'
        assert 'elapsed_ms' in result

    def test_create_new_lead_with_minimal_data(self, supabase_service, mock_supabase_client):
        """Test creating a new lead with only name."""
        select_mock = Mock()
        select_mock.eq.return_value = select_mock
        select_mock.ilike.return_value = select_mock
        select_mock.limit.return_value = select_mock
        select_mock.execute.return_value = Mock(data=[])

        insert_mock = Mock()
        insert_mock.execute.return_value = Mock(data=[{'id': 'lead-456'}])

        def table_side_effect(table_name):
            mock = Mock()
            mock.select.return_value = select_mock
            mock.insert.return_value = insert_mock
            return mock

        mock_supabase_client.table.side_effect = table_side_effect

        result = supabase_service.append_lead_data(name="Jane Doe")

        assert result['status'] == 'success'
        assert result['action'] == 'created'

    def test_update_existing_lead_by_phone(self, supabase_service, mock_supabase_client):
        """Test updating an existing lead found by phone number."""
        existing_lead = {
            'id': 'existing-lead-789',
            'lead_name': 'John Doe',
            'phone_number': '03001234567',
            'course_selected': 'CTA'
        }
        mock_supabase_client.execute.return_value = Mock(data=[existing_lead])
        mock_supabase_client.update.return_value.eq.return_value.execute.return_value = Mock(
            data=[{'id': 'existing-lead-789'}]
        )

        result = supabase_service.append_lead_data(
            phone="03001234567",
            goal="Updated goal"
        )

        assert result['status'] == 'success'
        assert result['action'] == 'updated'
        assert result['lead_id'] == 'existing-lead-789'

    def test_update_existing_lead_by_name(self, supabase_service, mock_supabase_client):
        """Test updating an existing lead found by name when phone not provided."""
        existing_lead = {
            'id': 'lead-by-name-111',
            'lead_name': 'Jane Smith',
            'phone_number': None,
            'course_selected': 'ACCA'
        }

        # Track which select query is called (by name via ilike)
        select_mock = Mock()
        select_mock.eq.return_value = select_mock
        select_mock.ilike.return_value = select_mock
        select_mock.limit.return_value = select_mock
        select_mock.execute.return_value = Mock(data=[existing_lead])  # Found by name

        update_mock = Mock()
        update_mock.eq.return_value = update_mock
        update_mock.execute.return_value = Mock(data=[{'id': 'lead-by-name-111'}])

        def table_side_effect(table_name):
            mock = Mock()
            mock.select.return_value = select_mock
            mock.update.return_value = update_mock
            return mock

        mock_supabase_client.table.side_effect = table_side_effect

        result = supabase_service.append_lead_data(
            name="Jane Smith",
            selected_course="CTA"  # Updating course
        )

        assert result['status'] == 'success'
        assert result['action'] == 'updated'
        assert result['lead_id'] == 'lead-by-name-111'

    def test_error_when_no_data_provided(self, supabase_service, mock_supabase_client):
        """Test error returned when no lead data provided."""
        result = supabase_service.append_lead_data()

        assert result['status'] == 'error'
        assert 'No lead data provided' in result['message']

    def test_error_when_only_empty_strings_provided(self, supabase_service, mock_supabase_client):
        """Test error when only empty/whitespace strings provided."""
        result = supabase_service.append_lead_data(
            name="   ",
            phone="",
            selected_course="  "
        )

        assert result['status'] == 'error'
        assert 'No lead data provided' in result['message']

    def test_missing_id_column_error(self, supabase_service, mock_supabase_client):
        """Test KeyError when leads table doesn't have 'id' column."""
        # Simulate a lead record without 'id' column (the bug scenario)
        existing_lead_without_id = {
            'lead_name': 'John Doe',
            'phone_number': '03001234567',
            'course_selected': 'CTA'
            # No 'id' field!
        }
        mock_supabase_client.execute.return_value = Mock(data=[existing_lead_without_id])

        result = supabase_service.append_lead_data(phone="03001234567", name="John Doe")

        assert result['status'] == 'error'
        assert "'id'" in result['message'] or "id" in result['message'].lower()

    def test_whitespace_is_stripped_from_inputs(self, supabase_service, mock_supabase_client):
        """Test that whitespace is stripped from all input fields."""
        mock_supabase_client.execute.return_value = Mock(data=[])
        mock_supabase_client.insert.return_value.execute.return_value = Mock(
            data=[{'id': 'trimmed-lead'}]
        )

        result = supabase_service.append_lead_data(
            name="  John Doe  ",
            phone="  03001234567  ",
            selected_course="  CTA  "
        )

        assert result['status'] == 'success'
        # Verify the insert was called with trimmed data
        insert_call = mock_supabase_client.insert.call_args
        if insert_call:
            inserted_data = insert_call[0][0]
            assert inserted_data.get('lead_name') == 'John Doe'
            assert inserted_data.get('phone_number') == '03001234567'
            assert inserted_data.get('course_selected') == 'CTA'

    def test_timestamp_is_always_added(self, supabase_service, mock_supabase_client):
        """Test that timestamp is automatically added to lead data."""
        mock_supabase_client.execute.return_value = Mock(data=[])
        mock_supabase_client.insert.return_value.execute.return_value = Mock(
            data=[{'id': 'timestamped-lead'}]
        )

        result = supabase_service.append_lead_data(name="Test User")

        assert result['status'] == 'success'
        insert_call = mock_supabase_client.insert.call_args
        if insert_call:
            inserted_data = insert_call[0][0]
            assert 'timestamp' in inserted_data
            # Verify it's a valid ISO format timestamp
            datetime.fromisoformat(inserted_data['timestamp'])

    def test_merge_data_on_update(self, supabase_service, mock_supabase_client):
        """Test that new data merges with existing data on update."""
        existing_lead = {
            'id': 'merge-test-lead',
            'lead_name': 'Original Name',
            'phone_number': '03001234567',
            'course_selected': 'ACCA',
            'education': 'Bachelors'
        }

        select_mock = Mock()
        select_mock.eq.return_value = select_mock
        select_mock.ilike.return_value = select_mock
        select_mock.limit.return_value = select_mock
        select_mock.execute.return_value = Mock(data=[existing_lead])

        # Capture the update data
        captured_update_data = {}
        update_mock = Mock()
        def capture_update(data):
            captured_update_data.update(data)
            eq_mock = Mock()
            eq_mock.execute.return_value = Mock(data=[{'id': 'merge-test-lead'}])
            return eq_mock
        update_mock.side_effect = capture_update

        def table_side_effect(table_name):
            mock = Mock()
            mock.select.return_value = select_mock
            mock.update = update_mock
            return mock

        mock_supabase_client.table.side_effect = table_side_effect

        result = supabase_service.append_lead_data(
            phone="03001234567",
            selected_course="CTA"  # Update only course
        )

        assert result['status'] == 'success'
        # Original data should be preserved
        assert captured_update_data.get('lead_name') == 'Original Name'
        assert captured_update_data.get('education') == 'Bachelors'
        # New data should override
        assert captured_update_data.get('course_selected') == 'CTA'
        # id should not be in update data
        assert 'id' not in captured_update_data

    def test_database_exception_handling(self, supabase_service, mock_supabase_client):
        """Test handling of database exceptions."""
        mock_supabase_client.execute.side_effect = Exception("Connection timeout")

        result = supabase_service.append_lead_data(name="Test User", phone="03001234567")

        assert result['status'] == 'error'
        assert 'Connection timeout' in result['message']

    def test_insert_returns_no_data(self, supabase_service, mock_supabase_client):
        """Test error handling when insert returns no data."""
        mock_supabase_client.execute.return_value = Mock(data=[])
        mock_supabase_client.insert.return_value.execute.return_value = Mock(data=[])

        result = supabase_service.append_lead_data(name="Ghost Lead")

        assert result['status'] == 'error'
        assert 'Failed to create lead' in result['message']


class TestAppendLeadDataIntegration:
    """Integration-style tests using real service initialization."""

    @pytest.fixture
    def mock_env(self):
        """Set up mock environment variables."""
        with patch.dict('os.environ', {
            'SUPABASE_URL': 'https://test.supabase.co',
            'SUPABASE_KEY': 'test-key'
        }):
            yield

    def test_service_initialization_and_lead_creation(self, mock_env):
        """Test full flow from service init to lead creation."""
        with patch('core.supabase_service.create_client') as mock_create:
            mock_client = Mock()
            mock_create.return_value = mock_client

            # Set up the mock chain
            mock_client.table.return_value = mock_client
            mock_client.select.return_value = mock_client
            mock_client.eq.return_value = mock_client
            mock_client.ilike.return_value = mock_client
            mock_client.limit.return_value = mock_client
            mock_client.execute.return_value = Mock(data=[])
            mock_client.insert.return_value = mock_client
            mock_client.insert.return_value.execute.return_value = Mock(
                data=[{'id': 'integration-test-lead'}]
            )

            from core.supabase_service import SupabaseService
            service = SupabaseService()

            result = service.append_lead_data(
                name="Integration Test",
                phone="03009876543",
                selected_course="CTA"
            )

            assert result['status'] == 'success'
            assert result['lead_id'] == 'integration-test-lead'


class TestAppendLeadDataEdgeCases:
    """Edge case tests for append_lead_data."""

    @pytest.fixture
    def mock_supabase_client(self):
        """Create a mock Supabase client."""
        client = Mock()
        client.table.return_value = client
        client.select.return_value = client
        client.eq.return_value = client
        client.ilike.return_value = client
        client.limit.return_value = client
        client.insert.return_value = client
        client.update.return_value = client
        return client

    @pytest.fixture
    def supabase_service(self, mock_supabase_client):
        """Create SupabaseService with mocked client."""
        with patch('core.supabase_service.create_client') as mock_create:
            mock_create.return_value = mock_supabase_client
            from core.supabase_service import SupabaseService
            service = SupabaseService()
            service.client = mock_supabase_client
            return service

    def test_phone_search_takes_priority_over_name(self, supabase_service, mock_supabase_client):
        """Test that phone-based search is tried before name-based search."""
        phone_lead = {
            'id': 'phone-lead',
            'lead_name': 'Different Name',
            'phone_number': '03001234567'
        }
        mock_supabase_client.execute.return_value = Mock(data=[phone_lead])
        mock_supabase_client.update.return_value.eq.return_value.execute.return_value = Mock(
            data=[{'id': 'phone-lead'}]
        )

        result = supabase_service.append_lead_data(
            name="John Doe",  # Different name
            phone="03001234567"
        )

        assert result['lead_id'] == 'phone-lead'
        # Verify phone search was used (eq called with phone_number)
        mock_supabase_client.eq.assert_called()

    def test_special_characters_in_name(self, supabase_service, mock_supabase_client):
        """Test handling of special characters in name."""
        mock_supabase_client.execute.return_value = Mock(data=[])
        mock_supabase_client.insert.return_value.execute.return_value = Mock(
            data=[{'id': 'special-char-lead'}]
        )

        result = supabase_service.append_lead_data(
            name="O'Brien-Smith, Jr."
        )

        assert result['status'] == 'success'

    def test_unicode_characters_in_fields(self, supabase_service, mock_supabase_client):
        """Test handling of unicode characters."""
        mock_supabase_client.execute.return_value = Mock(data=[])
        mock_supabase_client.insert.return_value.execute.return_value = Mock(
            data=[{'id': 'unicode-lead'}]
        )

        result = supabase_service.append_lead_data(
            name="محمد علی",  # Urdu/Arabic name
            goal="Career میں growth"
        )

        assert result['status'] == 'success'

    def test_very_long_field_values(self, supabase_service, mock_supabase_client):
        """Test handling of very long field values."""
        mock_supabase_client.execute.return_value = Mock(data=[])
        mock_supabase_client.insert.return_value.execute.return_value = Mock(
            data=[{'id': 'long-field-lead'}]
        )

        long_goal = "A" * 10000  # Very long string

        result = supabase_service.append_lead_data(
            name="Test User",
            goal=long_goal
        )

        assert result['status'] == 'success'

    def test_none_values_are_ignored(self, supabase_service, mock_supabase_client):
        """Test that None values are not included in the data."""
        mock_supabase_client.execute.return_value = Mock(data=[])
        mock_supabase_client.insert.return_value.execute.return_value = Mock(
            data=[{'id': 'none-values-lead'}]
        )

        result = supabase_service.append_lead_data(
            name="Test User",
            phone=None,
            selected_course=None,
            education_level=None,
            goal=None,
            notes=None
        )

        assert result['status'] == 'success'
        insert_call = mock_supabase_client.insert.call_args
        if insert_call:
            inserted_data = insert_call[0][0]
            # Only name and timestamp should be present
            assert 'lead_name' in inserted_data
            assert 'timestamp' in inserted_data
            assert 'phone_number' not in inserted_data
            assert 'course_selected' not in inserted_data

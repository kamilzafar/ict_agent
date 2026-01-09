"""Comprehensive tests for Supabase tools."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from tools.supabase_tools import create_supabase_tools


@pytest.fixture
def mock_supabase_service():
    """Create mock Supabase service."""
    service = Mock()
    return service


class TestFetchCourseLinks:
    """Tests for fetch_course_links tool."""
    
    def test_fetch_course_links_success_all_links(self, mock_supabase_service):
        """Test fetching all course links successfully."""
        mock_supabase_service.get_course_links.return_value = [{
            "demo_link": "https://example.com/demo",
            "pdf_link": "https://example.com/pdf",
            "course_link": "https://example.com/course"
        }]
        
        tools = create_supabase_tools(mock_supabase_service)
        fetch_tool = [t for t in tools if t.name == "fetch_course_links"][0]
        
        result = fetch_tool.invoke({"course_name": "CTA", "link_type": None})
        assert "Demo_Link:" in result
        assert "Pdf_Link:" in result
        assert "Course_Link:" in result
    
    def test_fetch_course_links_demo_only(self, mock_supabase_service):
        """Test fetching only demo link."""
        mock_supabase_service.get_course_links.return_value = [{
            "demo_link": "https://example.com/demo",
            "pdf_link": "https://example.com/pdf"
        }]
        
        tools = create_supabase_tools(mock_supabase_service)
        fetch_tool = [t for t in tools if t.name == "fetch_course_links"][0]
        
        result = fetch_tool.invoke({"course_name": "CTA", "link_type": "demo"})
        assert "Demo_Link:" in result
        assert "Pdf_Link:" not in result
    
    def test_fetch_course_links_pdf_only(self, mock_supabase_service):
        """Test fetching only PDF link."""
        mock_supabase_service.get_course_links.return_value = [{
            "pdf_link": "https://example.com/pdf"
        }]
        
        tools = create_supabase_tools(mock_supabase_service)
        fetch_tool = [t for t in tools if t.name == "fetch_course_links"][0]
        
        result = fetch_tool.invoke({"course_name": "CTA", "link_type": "pdf"})
        assert "Pdf_Link:" in result
    
    def test_fetch_course_links_course_not_found(self, mock_supabase_service):
        """Test error when course not found."""
        mock_supabase_service.get_course_links.return_value = []
        
        tools = create_supabase_tools(mock_supabase_service)
        fetch_tool = [t for t in tools if t.name == "fetch_course_links"][0]
        
        result = fetch_tool.invoke({"course_name": "Nonexistent", "link_type": None})
        assert "Error:" in result
        assert "No course found" in result
    
    def test_fetch_course_links_no_links_available(self, mock_supabase_service):
        """Test when course exists but no links available."""
        mock_supabase_service.get_course_links.return_value = [{
            "course_name": "CTA"
        }]
        
        tools = create_supabase_tools(mock_supabase_service)
        fetch_tool = [t for t in tools if t.name == "fetch_course_links"][0]
        
        result = fetch_tool.invoke({"course_name": "CTA", "link_type": "demo"})
        assert "Error:" in result
    
    def test_fetch_course_links_exception_handling(self, mock_supabase_service):
        """Test exception handling."""
        mock_supabase_service.get_course_links.side_effect = Exception("Database error")
        
        tools = create_supabase_tools(mock_supabase_service)
        fetch_tool = [t for t in tools if t.name == "fetch_course_links"][0]
        
        result = fetch_tool.invoke({"course_name": "CTA", "link_type": None})
        assert "Error" in result


class TestFetchCourseDetails:
    """Tests for fetch_course_details tool."""
    
    def test_fetch_course_details_all_fields(self, mock_supabase_service):
        """Test fetching all course details."""
        mock_supabase_service.get_course_details.return_value = [{
            "course_name": "CTA",
            "course_fee_physical": "40000",
            "course_duration": "6 months",
            "professor_name": "Test Professor"
        }]
        
        tools = create_supabase_tools(mock_supabase_service)
        fetch_tool = [t for t in tools if t.name == "fetch_course_details"][0]
        
        result = fetch_tool.invoke({"course_name": "CTA", "field": None})
        assert "course_fee_physical:" in result
        assert "course_duration:" in result
    
    def test_fetch_course_details_specific_field(self, mock_supabase_service):
        """Test fetching specific field."""
        mock_supabase_service.get_course_details.return_value = [{
            "course_name": "CTA",
            "course_fee_physical": "40000"
        }]
        
        tools = create_supabase_tools(mock_supabase_service)
        fetch_tool = [t for t in tools if t.name == "fetch_course_details"][0]
        
        result = fetch_tool.invoke({"course_name": "CTA", "field": "course_fee_physical"})
        assert "course_fee_physical:" in result
        assert "40000" in result
    
    def test_fetch_course_details_course_not_found(self, mock_supabase_service):
        """Test error when course not found."""
        mock_supabase_service.get_course_details.return_value = []
        
        tools = create_supabase_tools(mock_supabase_service)
        fetch_tool = [t for t in tools if t.name == "fetch_course_details"][0]
        
        result = fetch_tool.invoke({"course_name": "Nonexistent", "field": None})
        assert "Error:" in result
        assert "No course found" in result
    
    def test_fetch_course_details_field_not_found(self, mock_supabase_service):
        """Test error when field not found."""
        mock_supabase_service.get_course_details.return_value = [{
            "course_name": "CTA"
        }]
        
        tools = create_supabase_tools(mock_supabase_service)
        fetch_tool = [t for t in tools if t.name == "fetch_course_details"][0]
        
        result = fetch_tool.invoke({"course_name": "CTA", "field": "nonexistent_field"})
        assert "Error:" in result
        assert "not found" in result
    
    def test_fetch_course_details_exception_handling(self, mock_supabase_service):
        """Test exception handling."""
        mock_supabase_service.get_course_details.side_effect = Exception("Database error")
        
        tools = create_supabase_tools(mock_supabase_service)
        fetch_tool = [t for t in tools if t.name == "fetch_course_details"][0]
        
        result = fetch_tool.invoke({"course_name": "CTA", "field": None})
        assert "Error" in result


class TestFetchFAQs:
    """Tests for fetch_faqs tool."""
    
    def test_fetch_faqs_with_query(self, mock_supabase_service):
        """Test fetching FAQs with query."""
        mock_supabase_service.get_faqs.return_value = [
            {"question": "What is the fee?", "answer": "Rs. 40,000"}
        ]
        
        tools = create_supabase_tools(mock_supabase_service)
        fetch_tool = [t for t in tools if t.name == "fetch_faqs"][0]
        
        result = fetch_tool.invoke({"query": "fee", "course_name": None, "top_k": 5})
        assert "What is the fee?" in result
    
    def test_fetch_faqs_with_course_name(self, mock_supabase_service):
        """Test fetching FAQs for specific course."""
        mock_supabase_service.get_faqs.return_value = [
            {"question": "CTA fee?", "answer": "Rs. 40,000"}
        ]
        
        tools = create_supabase_tools(mock_supabase_service)
        fetch_tool = [t for t in tools if t.name == "fetch_faqs"][0]
        
        result = fetch_tool.invoke({"query": None, "course_name": "CTA", "top_k": 5})
        assert "CTA" in result
    
    def test_fetch_faqs_no_results(self, mock_supabase_service):
        """Test when no FAQs found."""
        mock_supabase_service.get_faqs.return_value = []
        
        tools = create_supabase_tools(mock_supabase_service)
        fetch_tool = [t for t in tools if t.name == "fetch_faqs"][0]
        
        result = fetch_tool.invoke({"query": "nonexistent", "course_name": None, "top_k": 5})
        assert "No FAQs found" in result
    
    def test_fetch_faqs_custom_top_k(self, mock_supabase_service):
        """Test fetching with custom top_k."""
        mock_supabase_service.get_faqs.return_value = [
            {"question": f"Q{i}", "answer": f"A{i}"} for i in range(10)
        ]
        
        tools = create_supabase_tools(mock_supabase_service)
        fetch_tool = [t for t in tools if t.name == "fetch_faqs"][0]
        
        result = fetch_tool.invoke({"query": None, "course_name": None, "top_k": 3})
        # Should limit to 3 results
        assert result.count("Q") <= 3
    
    def test_fetch_faqs_exception_handling(self, mock_supabase_service):
        """Test exception handling."""
        mock_supabase_service.get_faqs.side_effect = Exception("Database error")
        
        tools = create_supabase_tools(mock_supabase_service)
        fetch_tool = [t for t in tools if t.name == "fetch_faqs"][0]
        
        result = fetch_tool.invoke({"query": "test", "course_name": None, "top_k": 5})
        assert "Error" in result


class TestFetchProfessorInfo:
    """Tests for fetch_professor_info tool."""
    
    def test_fetch_professor_info_by_name(self, mock_supabase_service):
        """Test fetching professor by name."""
        mock_supabase_service.get_professor_info.return_value = {
            "name": "Test Professor",
            "qualifications": "CA, ACCA"
        }
        
        tools = create_supabase_tools(mock_supabase_service)
        fetch_tool = [t for t in tools if t.name == "fetch_professor_info"][0]
        
        result = fetch_tool.invoke({"professor_name": "Test Professor", "course_name": None})
        assert "Test Professor" in result
    
    def test_fetch_professor_info_by_course(self, mock_supabase_service):
        """Test fetching professor by course."""
        mock_supabase_service.get_professor_info.return_value = {
            "name": "Test Professor",
            "qualifications": "CA"
        }
        
        tools = create_supabase_tools(mock_supabase_service)
        fetch_tool = [t for t in tools if t.name == "fetch_professor_info"][0]
        
        result = fetch_tool.invoke({"professor_name": None, "course_name": "CTA"})
        assert "Test Professor" in result
    
    def test_fetch_professor_info_not_found(self, mock_supabase_service):
        """Test when professor not found."""
        mock_supabase_service.get_professor_info.return_value = {}
        
        tools = create_supabase_tools(mock_supabase_service)
        fetch_tool = [t for t in tools if t.name == "fetch_professor_info"][0]
        
        result = fetch_tool.invoke({"professor_name": "Nonexistent", "course_name": None})
        assert "Error:" in result or "not found" in result
    
    def test_fetch_professor_info_exception_handling(self, mock_supabase_service):
        """Test exception handling."""
        mock_supabase_service.get_professor_info.side_effect = Exception("Database error")
        
        tools = create_supabase_tools(mock_supabase_service)
        fetch_tool = [t for t in tools if t.name == "fetch_professor_info"][0]
        
        result = fetch_tool.invoke({"professor_name": "Test", "course_name": None})
        assert "Error" in result


class TestFetchCompanyInfo:
    """Tests for fetch_company_info tool."""
    
    def test_fetch_company_info_success(self, mock_supabase_service):
        """Test fetching company info successfully."""
        mock_supabase_service.get_company_info.return_value = {
            "company_name": "ICT",
            "phone_number": "+923001234567"
        }
        
        tools = create_supabase_tools(mock_supabase_service)
        fetch_tool = [t for t in tools if t.name == "fetch_company_info"][0]
        
        result = fetch_tool.invoke({"field": None})
        assert "ICT" in result or "+923001234567" in result
    
    def test_fetch_company_info_specific_field(self, mock_supabase_service):
        """Test fetching specific company field."""
        mock_supabase_service.get_company_info.return_value = {
            "phone_number": "+923001234567"
        }
        
        tools = create_supabase_tools(mock_supabase_service)
        fetch_tool = [t for t in tools if t.name == "fetch_company_info"][0]
        
        result = fetch_tool.invoke({"field": "phone_number"})
        assert "+923001234567" in result
    
    def test_fetch_company_info_field_not_found(self, mock_supabase_service):
        """Test error when field not found."""
        mock_supabase_service.get_company_info.return_value = {
            "company_name": "ICT"
        }
        
        tools = create_supabase_tools(mock_supabase_service)
        fetch_tool = [t for t in tools if t.name == "fetch_company_info"][0]
        
        result = fetch_tool.invoke({"field": "nonexistent"})
        assert "Error:" in result or "not found" in result
    
    def test_fetch_company_info_exception_handling(self, mock_supabase_service):
        """Test exception handling."""
        mock_supabase_service.get_company_info.side_effect = Exception("Database error")
        
        tools = create_supabase_tools(mock_supabase_service)
        fetch_tool = [t for t in tools if t.name == "fetch_company_info"][0]
        
        result = fetch_tool.invoke({"field": None})
        assert "Error" in result


class TestSearchCourses:
    """Tests for search_courses tool."""
    
    def test_search_courses_success(self, mock_supabase_service):
        """Test searching courses successfully."""
        mock_supabase_service.search_courses.return_value = [
            {"course_name": "CTA", "description": "Tax course"}
        ]
        
        tools = create_supabase_tools(mock_supabase_service)
        search_tool = [t for t in tools if t.name == "search_courses"][0]
        
        result = search_tool.invoke({"search_term": "tax", "limit": 10})
        assert "CTA" in result
    
    def test_search_courses_no_results(self, mock_supabase_service):
        """Test when no courses found."""
        mock_supabase_service.search_courses.return_value = []
        
        tools = create_supabase_tools(mock_supabase_service)
        search_tool = [t for t in tools if t.name == "search_courses"][0]
        
        result = search_tool.invoke({"search_term": "nonexistent", "limit": 10})
        assert "No courses found" in result
    
    def test_search_courses_custom_limit(self, mock_supabase_service):
        """Test searching with custom limit."""
        mock_supabase_service.search_courses.return_value = [
            {"course_name": f"Course{i}", "description": "Test"} for i in range(20)
        ]
        
        tools = create_supabase_tools(mock_supabase_service)
        search_tool = [t for t in tools if t.name == "search_courses"][0]
        
        result = search_tool.invoke({"search_term": "test", "limit": 5})
        # Should limit results
        assert result.count("Course") <= 5
    
    def test_search_courses_exception_handling(self, mock_supabase_service):
        """Test exception handling."""
        mock_supabase_service.search_courses.side_effect = Exception("Database error")
        
        tools = create_supabase_tools(mock_supabase_service)
        search_tool = [t for t in tools if t.name == "search_courses"][0]
        
        result = search_tool.invoke({"search_term": "test", "limit": 10})
        assert "Error" in result


class TestAppendLeadData:
    """Tests for append_lead_data tool."""
    
    def test_append_lead_data_create_new(self, mock_supabase_service):
        """Test creating new lead."""
        mock_supabase_service.append_lead_data.return_value = {
            "status": "success",
            "message": "Lead created",
            "lead_id": "test-id"
        }
        
        tools = create_supabase_tools(mock_supabase_service)
        append_tool = [t for t in tools if t.name == "append_lead_data"][0]
        
        result = append_tool.invoke({
            "name": "Test User",
            "phone": "03001234567",
            "selected_course": "CTA",
            "education_level": "Bachelors",
            "goal": "Career growth",
            "notes": None,
            "add_timestamp": True
        })
        assert "success" in result.lower() or "created" in result.lower()
    
    def test_append_lead_data_update_existing(self, mock_supabase_service):
        """Test updating existing lead."""
        mock_supabase_service.append_lead_data.return_value = {
            "status": "success",
            "message": "Lead updated",
            "lead_id": "test-id"
        }
        
        tools = create_supabase_tools(mock_supabase_service)
        append_tool = [t for t in tools if t.name == "append_lead_data"][0]
        
        result = append_tool.invoke({
            "phone": "03001234567",
            "notes": "Updated info",
            "add_timestamp": True
        })
        assert "success" in result.lower() or "updated" in result.lower()
    
    def test_append_lead_data_minimal_data(self, mock_supabase_service):
        """Test with minimal required data."""
        mock_supabase_service.append_lead_data.return_value = {
            "status": "success",
            "message": "Lead created",
            "lead_id": "test-id"
        }
        
        tools = create_supabase_tools(mock_supabase_service)
        append_tool = [t for t in tools if t.name == "append_lead_data"][0]
        
        result = append_tool.invoke({
            "selected_course": "CTA",
            "add_timestamp": True
        })
        assert "success" in result.lower()
    
    def test_append_lead_data_no_data_error(self, mock_supabase_service):
        """Test error when no data provided."""
        mock_supabase_service.append_lead_data.return_value = {
            "status": "error",
            "message": "No lead data provided"
        }
        
        tools = create_supabase_tools(mock_supabase_service)
        append_tool = [t for t in tools if t.name == "append_lead_data"][0]
        
        result = append_tool.invoke({
            "add_timestamp": True
        })
        assert "error" in result.lower() or "No lead data" in result
    
    def test_append_lead_data_exception_handling(self, mock_supabase_service):
        """Test exception handling."""
        mock_supabase_service.append_lead_data.side_effect = Exception("Database error")
        
        tools = create_supabase_tools(mock_supabase_service)
        append_tool = [t for t in tools if t.name == "append_lead_data"][0]
        
        result = append_tool.invoke({
            "name": "Test",
            "add_timestamp": True
        })
        assert "Error" in result


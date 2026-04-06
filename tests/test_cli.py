"""Tests for ai-recruitment-agent CLI and core functions."""

import pytest
from pathlib import Path
from typer.testing import CliRunner

from ai_recruitment_agent import __version__
from ai_recruitment_agent.main import (
    app,
    _truncate,
    _parse_json_response,
    check_notion_duplicate,
    create_notion_page,
    extract_jd_details_with_gemini,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_env(monkeypatch):
    """Patch all required environment globals in the main module."""
    monkeypatch.setattr("ai_recruitment_agent.main.GOOGLE_GEMINI_API_KEY", "test-gemini-key", raising=False)
    monkeypatch.setattr("ai_recruitment_agent.main.NOTION_API_KEY", "test-notion-key", raising=False)
    monkeypatch.setattr("ai_recruitment_agent.main.DEFAULT_NOTION_DB_ID", "test-db-id", raising=False)


@pytest.fixture()
def cv_folder(tmp_path: Path):
    """Temporary folder with two dummy CV files."""
    folder = tmp_path / "cvs"
    folder.mkdir()
    (folder / "alice.pdf").write_text("dummy pdf")
    (folder / "bob.docx").write_text("dummy docx")
    return folder


@pytest.fixture()
def jd_file(tmp_path: Path):
    """Temporary JD PDF file."""
    f = tmp_path / "jd.pdf"
    f.write_text("dummy jd content")
    return f


@pytest.fixture()
def mock_notion():
    """A minimal mock Notion client."""
    from unittest.mock import MagicMock
    client = MagicMock()
    client.databases.retrieve.return_value = {"id": "test-db-id"}
    client.databases.query.return_value = {"results": []}
    client.pages.create.return_value = {"id": "new-page-id"}
    return client


# ---------------------------------------------------------------------------
# Unit tests — helpers
# ---------------------------------------------------------------------------

class TestTruncate:
    def test_short_string_unchanged(self):
        assert _truncate("hello", 10) == "hello"

    def test_long_string_truncated(self):
        assert _truncate("a" * 2500) == "a" * 1999

    def test_exact_limit_unchanged(self):
        assert _truncate("a" * 1999) == "a" * 1999

    def test_custom_limit(self):
        assert _truncate("hello world", 5) == "hello"


class TestParseJsonResponse:
    def test_valid_json(self):
        assert _parse_json_response('{"key": "value"}') == {"key": "value"}

    def test_json_in_markdown_block(self):
        text = 'Some text\n{"key": "value"}\nMore text'
        assert _parse_json_response(text) == {"key": "value"}

    def test_invalid_returns_none(self):
        assert _parse_json_response("not json at all") is None

    def test_empty_string_returns_none(self):
        assert _parse_json_response("") is None


# ---------------------------------------------------------------------------
# Unit tests — Notion helpers
# ---------------------------------------------------------------------------

class TestCheckNotionDuplicate:
    def test_no_notion_returns_false(self):
        assert check_notion_duplicate(None, "db", "a@b.com", "JOB-1") is False

    def test_no_email_returns_false(self, mock_notion):
        assert check_notion_duplicate(mock_notion, "db", None, "JOB-1") is False

    def test_na_email_returns_false(self, mock_notion):
        assert check_notion_duplicate(mock_notion, "db", "N/A", "JOB-1") is False

    def test_duplicate_found(self, mock_notion):
        mock_notion.databases.query.return_value = {"results": [{"id": "existing"}]}
        assert check_notion_duplicate(mock_notion, "db", "a@b.com", "JOB-1") is True

    def test_no_duplicate(self, mock_notion):
        assert check_notion_duplicate(mock_notion, "db", "a@b.com", "JOB-1") is False

    def test_api_exception_returns_false(self, mock_notion):
        mock_notion.databases.query.side_effect = Exception("API error")
        assert check_notion_duplicate(mock_notion, "db", "a@b.com", "JOB-1") is False

    def test_na_job_id_omits_filter(self, mock_notion):
        mock_notion.databases.query.return_value = {"results": []}
        check_notion_duplicate(mock_notion, "db", "a@b.com", "N/A")
        call_args = mock_notion.databases.query.call_args
        # Only one filter (email) should be used — not wrapped in "and"
        assert "and" not in call_args.kwargs.get("filter", {})


class TestCreateNotionPage:
    def test_no_notion_returns_true(self):
        assert create_notion_page(None, "db", {}, {}, "cv.pdf") is True

    def test_successful_creation(self, mock_notion):
        data = {
            "full_name": "Alice Smith",
            "email": "alice@example.com",
            "contact_number": "1234567890",
            "skills": ["Python", "ML"],
            "experience_summary": "5 years of experience.",
            "match_score": 88,
            "ranking_category": "High Fit",
            "ranking_reason": "Strong match.",
        }
        assert create_notion_page(mock_notion, "db", data, {"position_title": "Engineer", "job_id": "ENG-1"}, "alice.pdf") is True
        mock_notion.pages.create.assert_called_once()

    def test_api_exception_returns_false(self, mock_notion):
        mock_notion.pages.create.side_effect = Exception("Notion error")
        assert create_notion_page(mock_notion, "db", {}, {}, "cv.pdf") is False

    def test_long_text_truncated(self, mock_notion):
        data = {"experience_summary": "x" * 3000, "full_name": "Test"}
        create_notion_page(mock_notion, "db", data, {}, "cv.pdf")
        call_kwargs = mock_notion.pages.create.call_args.kwargs
        summary = call_kwargs["properties"]["Experience Summary"]["rich_text"][0]["text"]["content"]
        assert len(summary) <= 1999

    def test_na_email_not_added(self, mock_notion):
        data = {"email": "N/A", "full_name": "Test"}
        create_notion_page(mock_notion, "db", data, {}, "cv.pdf")
        call_kwargs = mock_notion.pages.create.call_args.kwargs
        assert "Email" not in call_kwargs["properties"]


# ---------------------------------------------------------------------------
# Unit tests — Gemini wrappers
# ---------------------------------------------------------------------------

class TestExtractJdDetails:
    def test_valid_response(self, mocker):
        mocker.patch(
            "ai_recruitment_agent.main._call_gemini_api",
            return_value={"position_title": "Engineer", "job_id": "ENG-1"},
        )
        result = extract_jd_details_with_gemini("some jd text")
        assert result == {"position_title": "Engineer", "job_id": "ENG-1"}

    def test_none_response_returns_defaults(self, mocker):
        mocker.patch("ai_recruitment_agent.main._call_gemini_api", return_value=None)
        result = extract_jd_details_with_gemini("some jd text")
        assert result == {"position_title": "N/A", "job_id": "N/A"}

    def test_non_dict_response_returns_defaults(self, mocker):
        mocker.patch("ai_recruitment_agent.main._call_gemini_api", return_value="bad")
        result = extract_jd_details_with_gemini("some jd text")
        assert result == {"position_title": "N/A", "job_id": "N/A"}


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------

class TestCliHelp:
    def test_main_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "process" in result.stdout

    def test_process_help(self):
        result = runner.invoke(app, ["process", "--help"])
        assert result.exit_code == 0
        assert "cv_folder_path" in result.stdout.lower() or "CV_FOLDER_PATH" in result.stdout
        assert "--notion-db-id" in result.stdout

    def test_version_flag(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "ai-recruitment-agent" in result.stdout
        assert f"v{__version__}" in result.stdout

    def test_no_command_shows_guidance(self):
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "AI Recruitment" in result.stdout


class TestCliValidation:
    def test_missing_args(self):
        result = runner.invoke(app, ["process"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output

    def test_invalid_paths(self):
        result = runner.invoke(app, ["process", "./no_such_folder/", "./no_such_jd.pdf"])
        assert result.exit_code != 0
        assert "Invalid value" in result.output

    def test_missing_gemini_key(self, monkeypatch, cv_folder, jd_file):
        monkeypatch.setattr("ai_recruitment_agent.main.GOOGLE_GEMINI_API_KEY", None, raising=False)
        monkeypatch.setattr("ai_recruitment_agent.main.NOTION_API_KEY", "key", raising=False)
        monkeypatch.setattr("ai_recruitment_agent.main.DEFAULT_NOTION_DB_ID", "db", raising=False)
        result = runner.invoke(app, ["process", str(cv_folder), str(jd_file)])
        assert result.exit_code == 1
        assert "GOOGLE_GEMINI_API_KEY not found" in result.stdout

    def test_missing_notion_key(self, monkeypatch, cv_folder, jd_file):
        monkeypatch.setattr("ai_recruitment_agent.main.GOOGLE_GEMINI_API_KEY", "key", raising=False)
        monkeypatch.setattr("ai_recruitment_agent.main.NOTION_API_KEY", None, raising=False)
        monkeypatch.setattr("ai_recruitment_agent.main.DEFAULT_NOTION_DB_ID", "db", raising=False)
        result = runner.invoke(app, ["process", str(cv_folder), str(jd_file)])
        assert result.exit_code == 1
        assert "NOTION_API_KEY not found" in result.stdout

    def test_missing_notion_db_id(self, monkeypatch, cv_folder, jd_file):
        monkeypatch.setattr("ai_recruitment_agent.main.GOOGLE_GEMINI_API_KEY", "key", raising=False)
        monkeypatch.setattr("ai_recruitment_agent.main.NOTION_API_KEY", "key", raising=False)
        monkeypatch.setattr("ai_recruitment_agent.main.DEFAULT_NOTION_DB_ID", None, raising=False)
        result = runner.invoke(app, ["process", str(cv_folder), str(jd_file)])
        assert result.exit_code == 1
        assert "Notion Database ID is not provided" in result.stdout


class TestCliProcessFlow:
    def _invoke(self, mocker, mock_env, cv_folder, jd_file, notion_side_effect=None):
        mock_extract_pdf = mocker.patch("ai_recruitment_agent.main.extract_text_from_pdf")
        mock_extract_pdf.side_effect = ["JD text content", "CV text for alice"]
        mocker.patch("ai_recruitment_agent.main.extract_text_from_docx", return_value="CV text for bob")
        mocker.patch(
            "ai_recruitment_agent.main.extract_jd_details_with_gemini",
            return_value={"position_title": "Engineer", "job_id": "ENG-1"},
        )
        mocker.patch(
            "ai_recruitment_agent.main.process_cv_with_gemini",
            return_value={
                "full_name": "Alice", "email": "alice@example.com",
                "contact_number": "000", "skills": ["Python"],
                "experience_summary": "Good.", "match_score": 90,
                "ranking_category": "High Fit", "ranking_reason": "Strong.",
            },
        )
        mocker.patch("ai_recruitment_agent.main.check_notion_duplicate", return_value=False)
        mocker.patch("ai_recruitment_agent.main.create_notion_page", return_value=True)
        mock_client = mocker.MagicMock()
        mock_client.databases.retrieve.return_value = {"id": "test-db-id"}
        mocker.patch("ai_recruitment_agent.main.NotionClient", return_value=mock_client)
        return runner.invoke(
            app,
            ["process", str(cv_folder), str(jd_file), "--notion-db-id", "test-db-id"],
        )

    def test_successful_run(self, mocker, mock_env, cv_folder, jd_file):
        result = self._invoke(mocker, mock_env, cv_folder, jd_file)
        assert result.exit_code == 0, result.stdout
        assert "Pre-run checks passed" in result.stdout
        assert "Processing Summary" in result.stdout
        assert "Done." in result.stdout

    def test_empty_cv_folder(self, mocker, mock_env, tmp_path, jd_file):
        empty_folder = tmp_path / "empty"
        empty_folder.mkdir()
        mocker.patch("ai_recruitment_agent.main.extract_text_from_pdf", return_value="JD text")
        mocker.patch(
            "ai_recruitment_agent.main.extract_jd_details_with_gemini",
            return_value={"position_title": "Eng", "job_id": "E-1"},
        )
        mock_client = mocker.MagicMock()
        mock_client.databases.retrieve.return_value = {"id": "test-db-id"}
        mocker.patch("ai_recruitment_agent.main.NotionClient", return_value=mock_client)
        result = runner.invoke(
            app,
            ["process", str(empty_folder), str(jd_file), "--notion-db-id", "test-db-id"],
        )
        assert result.exit_code == 0
        assert "No supported CV files" in result.stdout

    def test_duplicate_skipped(self, mocker, mock_env, cv_folder, jd_file):
        mocker.patch("ai_recruitment_agent.main.extract_text_from_pdf", side_effect=["JD text", "CV text"])
        mocker.patch("ai_recruitment_agent.main.extract_text_from_docx", return_value="CV text")
        mocker.patch(
            "ai_recruitment_agent.main.extract_jd_details_with_gemini",
            return_value={"position_title": "Eng", "job_id": "E-1"},
        )
        mocker.patch(
            "ai_recruitment_agent.main.process_cv_with_gemini",
            return_value={"full_name": "Alice", "email": "alice@example.com", "match_score": 80},
        )
        mocker.patch("ai_recruitment_agent.main.check_notion_duplicate", return_value=True)
        create_mock = mocker.patch("ai_recruitment_agent.main.create_notion_page")
        mock_client = mocker.MagicMock()
        mock_client.databases.retrieve.return_value = {"id": "test-db-id"}
        mocker.patch("ai_recruitment_agent.main.NotionClient", return_value=mock_client)
        result = runner.invoke(
            app,
            ["process", str(cv_folder), str(jd_file), "--notion-db-id", "test-db-id"],
        )
        assert result.exit_code == 0
        create_mock.assert_not_called()
        assert "Duplicate skipped" in result.stdout or "duplicate" in result.stdout.lower()

    def test_failed_gemini_response_counted(self, mocker, mock_env, cv_folder, jd_file):
        mocker.patch("ai_recruitment_agent.main.extract_text_from_pdf", side_effect=["JD text", "CV text"])
        mocker.patch("ai_recruitment_agent.main.extract_text_from_docx", return_value="CV text")
        mocker.patch(
            "ai_recruitment_agent.main.extract_jd_details_with_gemini",
            return_value={"position_title": "Eng", "job_id": "E-1"},
        )
        mocker.patch("ai_recruitment_agent.main.process_cv_with_gemini", return_value=None)
        mock_client = mocker.MagicMock()
        mock_client.databases.retrieve.return_value = {"id": "test-db-id"}
        mocker.patch("ai_recruitment_agent.main.NotionClient", return_value=mock_client)
        result = runner.invoke(
            app,
            ["process", str(cv_folder), str(jd_file), "--notion-db-id", "test-db-id"],
        )
        assert result.exit_code == 0
        assert "Processing Summary" in result.stdout

    def test_unreadable_jd_exits(self, mocker, mock_env, cv_folder, jd_file):
        mocker.patch("ai_recruitment_agent.main.extract_text_from_pdf", return_value=None)
        mock_client = mocker.MagicMock()
        mock_client.databases.retrieve.return_value = {"id": "test-db-id"}
        mocker.patch("ai_recruitment_agent.main.NotionClient", return_value=mock_client)
        result = runner.invoke(
            app,
            ["process", str(cv_folder), str(jd_file), "--notion-db-id", "test-db-id"],
        )
        assert result.exit_code == 1
        assert "Could not extract text" in result.stdout

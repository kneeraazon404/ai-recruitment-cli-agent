# tests/test_cli.py
import pytest
from typer.testing import CliRunner
from pathlib import Path
import os

from ai_recruitment_agent.main import app

runner = CliRunner()


# --- Fixtures ---
@pytest.fixture(scope="function")
def mock_env_vars(monkeypatch):
    """Mocks essential environment variables."""
    monkeypatch.setenv("GOOGLE_GEMINI_API_KEY", "test_gemini_key")
    monkeypatch.setenv("NOTION_API_KEY", "test_notion_key")
    monkeypatch.setenv("DEFAULT_NOTION_DB_ID", "test_default_db_id")
    # If main.py re-imports os and load_dotenv, you might need to patch them there too
    # or ensure these are set before main.py's module-level code runs.
    # For simplicity, we assume main.py reads them once at import time.
    # To be absolutely sure, you could also patch the global variables in main.py directly:
    monkeypatch.setattr("ai_recruitment_agent.main.GOOGLE_GEMINI_API_KEY", "test_gemini_key", raising=False)
    monkeypatch.setattr("ai_recruitment_agent.main.NOTION_API_KEY", "test_notion_key", raising=False)
    monkeypatch.setattr(
        "ai_recruitment_agent.main.DEFAULT_NOTION_DB_ID", "test_default_db_id", raising=False
    )


@pytest.fixture
def temp_files(tmp_path: Path):
    """Creates temporary CV folder and JD file for testing."""
    cv_folder = tmp_path / "cvs"
    cv_folder.mkdir()
    (cv_folder / "cv1.pdf").write_text("dummy pdf content")
    (cv_folder / "cv2.docx").write_text("dummy docx content")

    jd_file = tmp_path / "jd.pdf"
    jd_file.write_text("dummy jd content")
    return cv_folder, jd_file


# --- Test Cases ---


def test_cli_main_help():
    """Test the main help message for the CLI."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "AI Recruitment Scanning Agent" in result.stdout
    assert "process" in result.stdout  # Check if the 'process' command is listed


def test_cli_process_help():
    """Test the help message for the 'process' command."""
    result = runner.invoke(app, ["process", "--help"])
    assert result.exit_code == 0
    assert "Process CVs against a Job Description." in result.stdout
    assert "cv_folder_path" in result.stdout
    assert "jd_pdf_path" in result.stdout
    assert "--notion-db-id" in result.stdout


def test_cli_process_missing_args(mock_env_vars):
    """Test 'process' command with missing required arguments."""
    # mock_env_vars is used to prevent errors about missing API keys during Typer's initial parsing
    result = runner.invoke(app, ["process"])
    assert result.exit_code != 0  # Expect an error
    assert (
        "Missing argument 'CV_FOLDER_PATH'" in result.output
        or "Missing argument 'JD_PDF_PATH'" in result.output
    )


def test_cli_process_invalid_paths(mock_env_vars):
    """Test 'process' command with non-existent paths."""
    result = runner.invoke(
        app, ["process", "./non_existent_cvs/", "./non_existent_jd.pdf"]
    )
    assert result.exit_code != 0
    # Typer's `exists=True` for Path arguments handles this
    assert "Invalid value" in result.output
    assert "does not" in result.output  # Rich box may wrap "does not exist" across lines


def test_cli_pre_run_check_missing_gemini_key(monkeypatch, temp_files):
    """Test pre-run check failure if Gemini API key is missing."""
    monkeypatch.setenv("NOTION_API_KEY", "test_notion_key")
    monkeypatch.setenv("DEFAULT_NOTION_DB_ID", "test_db_id")
    monkeypatch.delenv("GOOGLE_GEMINI_API_KEY", raising=False)
    # Also patch the global in main.py if it's already loaded
    monkeypatch.setattr("ai_recruitment_agent.main.GOOGLE_GEMINI_API_KEY", None, raising=False)

    cv_folder, jd_file = temp_files
    result = runner.invoke(app, ["process", str(cv_folder), str(jd_file)])
    assert result.exit_code == 1
    assert "GOOGLE_GEMINI_API_KEY not found" in result.stdout


def test_cli_pre_run_check_missing_notion_key(monkeypatch, temp_files):
    """Test pre-run check failure if Notion API key is missing."""
    monkeypatch.setenv("GOOGLE_GEMINI_API_KEY", "test_gemini_key")
    monkeypatch.setenv("DEFAULT_NOTION_DB_ID", "test_db_id")
    monkeypatch.delenv("NOTION_API_KEY", raising=False)
    monkeypatch.setattr("ai_recruitment_agent.main.NOTION_API_KEY", None, raising=False)

    cv_folder, jd_file = temp_files
    result = runner.invoke(app, ["process", str(cv_folder), str(jd_file)])
    assert result.exit_code == 1
    assert "NOTION_API_KEY not found" in result.stdout


def test_cli_pre_run_check_missing_notion_db_id(monkeypatch, temp_files):
    """Test pre-run check failure if Notion DB ID is missing (and not provided via CLI)."""
    monkeypatch.setenv("GOOGLE_GEMINI_API_KEY", "test_gemini_key")
    monkeypatch.setenv("NOTION_API_KEY", "test_notion_key")
    monkeypatch.delenv("DEFAULT_NOTION_DB_ID", raising=False)  # Remove default
    monkeypatch.setattr("ai_recruitment_agent.main.DEFAULT_NOTION_DB_ID", None, raising=False)

    cv_folder, jd_file = temp_files
    # Not providing --notion-db-id
    result = runner.invoke(app, ["process", str(cv_folder), str(jd_file)])
    assert result.exit_code == 1
    assert "Notion Database ID is not provided" in result.stdout


def test_cli_process_successful_run_mocked(mocker, mock_env_vars, temp_files):
    """
    Test a 'successful' run of the process command with all underlying functions mocked.
    This tests the CLI flow, argument parsing, and pre-run checks passing.
    """
    cv_folder, jd_file = temp_files

    # Mock all major processing functions to prevent actual API calls or heavy file processing
    mocker.patch("ai_recruitment_agent.main.extract_text_from_pdf", return_value="Mocked JD Text")
    mocker.patch("ai_recruitment_agent.main.extract_text_from_docx", return_value="Mocked CV Text from DOCX")
    # If cv1.pdf is also processed by extract_text_from_pdf for CVs:
    # We might need a side_effect if it's called for both JD and CV pdfs
    mock_extract_pdf = mocker.patch("ai_recruitment_agent.main.extract_text_from_pdf")
    mock_extract_pdf.side_effect = ["Mocked JD Text", "Mocked CV Text from PDF"]

    mocker.patch(
        "ai_recruitment_agent.main.extract_jd_details_with_gemini",
        return_value={"position_title": "Test Job", "job_id": "TJ123"},
    )
    mocker.patch(
        "ai_recruitment_agent.main.process_cv_with_gemini",
        return_value={
            "full_name": "Test Candidate",
            "email": "test@example.com",
            "contact_number": "1234567890",
            "skills": ["Python", "Testing"],
            "experience_summary": "Great experience.",
            "match_score": 90,
            "ranking_category": "High Fit",
            "ranking_reason": "Looks good.",
        },
    )
    mocker.patch(
        "ai_recruitment_agent.main.check_notion_duplicate", return_value=False
    )  # Assume no duplicates
    mocker.patch(
        "ai_recruitment_agent.main.create_notion_page", return_value=True
    )  # Assume Notion page creation is successful

    # Mock Notion client and database retrieval to pass initialization
    mock_notion_client_instance = mocker.MagicMock()
    mocker.patch("ai_recruitment_agent.main.NotionClient", return_value=mock_notion_client_instance)
    mock_notion_client_instance.databases.retrieve.return_value = {
        "id": "test_db_id_from_cli"
    }

    # Run with CLI-provided Notion DB ID
    result = runner.invoke(
        app,
        [
            "process",
            str(cv_folder),
            str(jd_file),
            "--notion-db-id",
            "test_db_id_from_cli",
        ],
    )

    print(f"CLI Output:\n{result.stdout}")  # For debugging if assertions fail

    assert result.exit_code == 0, f"CLI command failed with output: {result.stdout}"
    assert "Pre-run checks passed." in result.stdout
    assert "Notion Database ID to be used: test_db_id_from_cli" in result.stdout
    assert "Job Description processing complete." in result.stdout
    assert (
        f"Processing CV: {Path('cv1.pdf').name}" in result.stdout
    )  # Check one of the CVs
    assert (
        f"Processing CV: {Path('cv2.docx').name}" in result.stdout
    )  # Check one of the CVs
    assert "CVs successfully processed & added to Notion" in result.stdout
    assert (
        "[green]2[/green]" in result.stdout
    )  # Assuming 2 CVs processed based on temp_files
    assert "Script execution finished." in result.stdout

    # Check if NotionClient was called with the correct auth
    # main.NotionClient.assert_called_once_with(auth="test_notion_key") # This needs NotionClient to be the mock object itself
    # Check if retrieve was called on the instance
    mock_notion_client_instance.databases.retrieve.assert_called_once_with(
        database_id="test_db_id_from_cli"
    )


def test_cli_initial_guidance_on_no_command():
    """Tests that initial guidance is shown if no command is provided."""
    result = runner.invoke(app, [])  # No command
    assert (
        result.exit_code == 0
    )  # Typer's default for no command if callback is well-defined
    assert "AI Recruitment Scanning Agent" in result.stdout
    assert "Purpose:" in result.stdout
    assert "Required CLI Arguments:" in result.stdout
    assert "Configuration (.env file):" in result.stdout
    assert (
        "Usage:" in result.stdout and "OPTIONS" in result.stdout and "COMMAND" in result.stdout
    )  # Part of Typer's help output


# Add more tests:
# - Test specific error handling for individual CV processing failures.
# - Test duplicate skipping logic (mock check_notion_duplicate to return True).
# - Test different combinations of .env and CLI arguments for Notion DB ID.
# - Test behavior when CV folder is empty or contains no supported files.

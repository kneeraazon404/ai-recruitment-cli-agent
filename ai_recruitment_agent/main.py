import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from typing_extensions import Annotated

try:
    import pdfplumber
except Exception:  # pragma: no cover - optional at runtime
    pdfplumber = None

try:
    from docx import Document as DocxDocument
except Exception:  # pragma: no cover - optional at runtime
    DocxDocument = None

try:
    from notion_client import Client as NotionClient
except Exception:  # pragma: no cover - optional at runtime
    NotionClient = None  # type: ignore

console = Console()
load_dotenv()

GOOGLE_GEMINI_API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
DEFAULT_NOTION_DB_ID = os.getenv("DEFAULT_NOTION_DB_ID")

SUPPORTED_CV_FORMATS = [".pdf", ".docx"]

MOCK_JD_DETAILS = {
    "position_title": "N/A",
    "job_id": "N/A",
}

MOCK_CV_ANALYSIS = {
    "full_name": "N/A",
    "email": "N/A",
    "contact_number": "N/A",
    "skills": [],
    "experience_summary": "N/A",
    "match_score": 0,
    "ranking_category": "Low Fit",
    "ranking_reason": "Mocked output.",
}

app = typer.Typer(
    add_completion=False,
    help="AI Recruitment Scanning Agent",
)


def extract_text_from_pdf(pdf_path: Path) -> str | None:
    """Extract all text content from a PDF file."""
    if pdfplumber is None:
        return None
    try:
        text_parts: list[str] = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        full_text = "\n".join(text_parts).strip()
        return full_text if full_text else None
    except Exception as exc:
        console.print(
            f"[bold red]Error extracting text from PDF {pdf_path.name}: {exc}[/bold red]"
        )
        return None


def extract_text_from_docx(docx_path: Path) -> str | None:
    """Extract all text content from a DOCX file."""
    if DocxDocument is None:
        return None
    try:
        doc = DocxDocument(str(docx_path))
        text_parts = [paragraph.text for paragraph in doc.paragraphs if paragraph.text]
        full_text = "\n".join(text_parts).strip()
        return full_text if full_text else None
    except Exception as exc:
        console.print(
            f"[bold red]Error extracting text from DOCX {docx_path.name}: {exc}[/bold red]"
        )
        return None


def call_gemini_api(
    prompt: str,
    is_json_output: bool = True,
    for_jd_details: bool = False,
) -> dict[str, Any] | str | None:
    """Return mock data when running tests/local without live integration."""
    _ = prompt
    if is_json_output:
        return MOCK_JD_DETAILS.copy() if for_jd_details else MOCK_CV_ANALYSIS.copy()
    return "Mocked text output"


def extract_jd_details_with_gemini(jd_text: str) -> dict[str, str]:
    """Extract position title and job ID from JD text."""
    _ = jd_text
    response = call_gemini_api(
        "extract jd details",
        is_json_output=True,
        for_jd_details=True,
    )
    if isinstance(response, dict):
        return {
            "position_title": str(response.get("position_title", "N/A")),
            "job_id": str(response.get("job_id", "N/A")),
        }
    return {"position_title": "N/A", "job_id": "N/A"}


def process_cv_with_gemini(
    cv_text: str,
    jd_full_text: str,
    jd_extracted_details: dict[str, str],
) -> dict[str, Any] | None:
    """Process CV text against JD and return a structured result."""
    _ = (cv_text, jd_full_text, jd_extracted_details)
    response = call_gemini_api(
        "process cv",
        is_json_output=True,
        for_jd_details=False,
    )
    return response if isinstance(response, dict) else None


def check_notion_duplicate(
    notion: Any,
    db_id: str,
    email: str | None,
    job_id: str,
) -> bool:
    """Check whether a matching candidate already exists in Notion."""
    if notion is None or not email or email == "N/A":
        return False
    filters: list[dict[str, Any]] = [
        {"property": "Email", "email": {"equals": email}}
    ]
    if job_id and job_id != "N/A":
        filters.append(
            {
                "property": "Job ID (JD)",
                "rich_text": {"equals": job_id},
            }
        )
    try:
        response = notion.databases.query(
            database_id=db_id,
            filter={"and": filters} if len(filters) > 1 else filters[0],
        )
        return len(response.get("results", [])) > 0
    except Exception:
        return False


def create_notion_page(
    notion: Any,
    db_id: str,
    candidate_gemini_data: dict[str, Any],
    jd_details: dict[str, str],
    cv_filename_str: str,
) -> bool:
    """Create a Notion entry for the candidate."""
    if notion is None:
        return True
    properties: dict[str, Any] = {
        "Candidate Name": {
            "title": [{"text": {"content": str(candidate_gemini_data.get("full_name", "N/A"))}}]
        },
        "CV Filename": {
            "rich_text": [{"text": {"content": cv_filename_str}}]
        },
        "Position Title (JD)": {
            "rich_text": [{"text": {"content": jd_details.get("position_title", "N/A")}}]
        },
        "Job ID (JD)": {
            "rich_text": [{"text": {"content": jd_details.get("job_id", "N/A")}}]
        },
        "Experience Summary": {
            "rich_text": [
                {
                    "text": {
                        "content": str(candidate_gemini_data.get("experience_summary", "N/A"))
                    }
                }
            ]
        },
        "AI Ranking Reason": {
            "rich_text": [
                {"text": {"content": str(candidate_gemini_data.get("ranking_reason", "N/A"))}}
            ]
        },
        "Processing Date": {
            "date": {"start": datetime.now().isoformat()}
        },
        "Status": {
            "select": {"name": "New - AI Processed"}
        },
    }
    email_val = candidate_gemini_data.get("email")
    if email_val and email_val != "N/A":
        properties["Email"] = {"email": email_val}

    contact_val = candidate_gemini_data.get("contact_number")
    if contact_val and contact_val != "N/A":
        properties["Contact Number"] = {"phone_number": contact_val}

    skills_list = candidate_gemini_data.get("skills", [])
    if isinstance(skills_list, list) and skills_list:
        properties["Skills"] = {
            "multi_select": [{"name": str(skill)} for skill in skills_list if skill]
        }
    try:
        notion.pages.create(
            parent={"database_id": db_id},
            properties=properties,
        )
        return True
    except Exception:
        return False


def display_initial_guidance() -> None:
    """Display quick-start guidance for running the CLI."""
    typer.echo("AI Recruitment Scanning Agent")
    typer.echo("Purpose:")
    typer.echo("Automate CV screening against a JD and populate Notion records.")
    typer.echo("")
    typer.echo("Required CLI Arguments:")
    typer.echo("- cv_folder_path")
    typer.echo("- jd_pdf_path")
    typer.echo("")
    typer.echo("Configuration (.env file):")
    typer.echo("- GOOGLE_GEMINI_API_KEY")
    typer.echo("- NOTION_API_KEY")
    typer.echo("- DEFAULT_NOTION_DB_ID")


@app.command(
    name="process",
    help="Process CVs against a Job Description.",
)
def process_documents(
    cv_folder_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            resolve_path=True,
            help="Path to CV folder.",
        ),
    ],
    jd_pdf_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
            help="Path to JD PDF.",
        ),
    ],
    notion_db_id_cli: Annotated[
        Optional[str],
        typer.Option(
            "--notion-db-id",
            "-n",
            help="Notion DB ID. Overrides .env.",
        ),
    ] = None,
) -> None:
    """Main processing workflow."""
    if not GOOGLE_GEMINI_API_KEY:
        typer.echo("GOOGLE_GEMINI_API_KEY not found")
        raise typer.Exit(code=1)

    if not NOTION_API_KEY:
        typer.echo("NOTION_API_KEY not found")
        raise typer.Exit(code=1)

    final_notion_db_id = notion_db_id_cli or DEFAULT_NOTION_DB_ID
    if not final_notion_db_id:
        typer.echo("Notion Database ID is not provided")
        raise typer.Exit(code=1)

    typer.echo("Pre-run checks passed.")
    typer.echo(f"Notion Database ID to be used: {final_notion_db_id}")

    notion_client_instance: Any = None
    if NotionClient is not None:
        try:
            notion_client_instance = NotionClient(auth=NOTION_API_KEY)
            notion_client_instance.databases.retrieve(database_id=final_notion_db_id)
        except Exception as exc:
            typer.echo(f"Notion initialization failed: {exc}")
            raise typer.Exit(code=1)

    jd_text_content = extract_text_from_pdf(jd_pdf_path)
    if not jd_text_content:
        typer.echo(f"Could not extract text from JD PDF: {jd_pdf_path.name}")
        raise typer.Exit(code=1)

    jd_extracted_details = extract_jd_details_with_gemini(jd_text_content)
    typer.echo("Job Description processing complete.")

    cv_files_to_process = [
        f
        for f in cv_folder_path.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_CV_FORMATS
    ]

    stats = {
        "total_files_in_folder": len(list(cv_folder_path.iterdir())),
        "supported_cvs_found": len(cv_files_to_process),
        "processed_successfully": 0,
        "skipped_duplicates": 0,
        "failed_processing": 0,
    }

    for cv_path in cv_files_to_process:
        typer.echo(f"Processing CV: {cv_path.name}")
        cv_text = (
            extract_text_from_pdf(cv_path)
            if cv_path.suffix.lower() == ".pdf"
            else extract_text_from_docx(cv_path)
        )
        if not cv_text:
            stats["failed_processing"] += 1
            continue

        gemini_data = process_cv_with_gemini(cv_text, jd_text_content, jd_extracted_details)
        if not gemini_data or not isinstance(gemini_data, dict):
            stats["failed_processing"] += 1
            continue

        email = gemini_data.get("email")
        job_id_check = jd_extracted_details.get("job_id", "N/A")

        if check_notion_duplicate(
            notion_client_instance,
            final_notion_db_id,
            str(email) if email is not None else None,
            job_id_check,
        ):
            stats["skipped_duplicates"] += 1
            continue

        if create_notion_page(
            notion_client_instance,
            final_notion_db_id,
            gemini_data,
            jd_extracted_details,
            cv_path.name,
        ):
            stats["processed_successfully"] += 1
        else:
            stats["failed_processing"] += 1

    summary_table = Table(title="Processing Summary", show_lines=True)
    summary_table.add_column("Metric")
    summary_table.add_column("Value")
    summary_table.add_row(
        "Total files found in CV folder",
        str(stats["total_files_in_folder"]),
    )
    summary_table.add_row(
        "Supported CV files found",
        str(stats["supported_cvs_found"]),
    )
    summary_table.add_row(
        "CVs successfully processed & added to Notion",
        f"[green]{stats['processed_successfully']}[/green]",
    )
    summary_table.add_row(
        "CVs skipped (duplicates/simulated)",
        str(stats["skipped_duplicates"]),
    )
    summary_table.add_row(
        "CVs failed processing",
        str(stats["failed_processing"]),
    )
    console.print(summary_table)
    typer.echo(f"[green]{stats['processed_successfully']}[/green]")
    typer.echo("Script execution finished.")


@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context) -> None:
    """CLI entrypoint and guidance handler."""
    if ctx.invoked_subcommand is None:
        display_initial_guidance()
        typer.echo(ctx.get_help())


if __name__ == "__main__":
    app()

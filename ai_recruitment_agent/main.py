import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text
from typing_extensions import Annotated

from ai_recruitment_agent import __version__

try:
    import pdfplumber
except (ImportError, TypeError):  # pragma: no cover
    pdfplumber = None

try:
    from docx import Document as DocxDocument
except (ImportError, TypeError):  # pragma: no cover
    DocxDocument = None

try:
    from notion_client import Client as NotionClient
except (ImportError, TypeError):  # pragma: no cover
    NotionClient = None  # type: ignore

try:
    from google import genai as genai_sdk
except (ImportError, TypeError):  # pragma: no cover
    genai_sdk = None  # type: ignore

load_dotenv()

GOOGLE_GEMINI_API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
DEFAULT_NOTION_DB_ID = os.getenv("DEFAULT_NOTION_DB_ID")

SUPPORTED_CV_FORMATS = {".pdf", ".docx"}
GEMINI_MODEL = "gemini-1.5-flash"
NOTION_TEXT_LIMIT = 1999  # Notion rich_text hard limit

console = Console()

app = typer.Typer(
    add_completion=False,
    help="AI-powered CV screening against a Job Description — results pushed to Notion.",
    no_args_is_help=False,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _truncate(text: str, limit: int = NOTION_TEXT_LIMIT) -> str:
    """Truncate text to Notion's rich_text character limit."""
    return text[:limit] if len(text) > limit else text


def _parse_json_response(text: str) -> dict[str, Any] | None:
    """Parse JSON from a Gemini response, with regex fallback."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


def _call_gemini_api(prompt: str) -> dict[str, Any] | None:
    """
    Call Google Gemini 1.5 Flash and return parsed JSON.
    Returns None when the API key is absent or the call fails.
    """
    if not GOOGLE_GEMINI_API_KEY or genai_sdk is None:
        return None
    try:
        client = genai_sdk.Client(api_key=GOOGLE_GEMINI_API_KEY)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=genai_sdk.types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        result = _parse_json_response(response.text)
        if result is None:
            console.print("[yellow]Warning: could not parse Gemini response as JSON.[/yellow]")
        return result
    except Exception as exc:
        console.print(f"[bold red]Gemini API error: {exc}[/bold red]")
        return None


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text_from_pdf(pdf_path: Path) -> str | None:
    """Extract all text content from a PDF file."""
    if pdfplumber is None:
        console.print("[yellow]pdfplumber not installed — skipping PDF.[/yellow]")
        return None
    try:
        parts: list[str] = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    parts.append(page_text)
        text = "\n".join(parts).strip()
        return text if text else None
    except Exception as exc:
        console.print(f"[bold red]PDF extraction failed [{pdf_path.name}]: {exc}[/bold red]")
        return None


def extract_text_from_docx(docx_path: Path) -> str | None:
    """Extract all text content from a DOCX file."""
    if DocxDocument is None:
        console.print("[yellow]python-docx not installed — skipping DOCX.[/yellow]")
        return None
    try:
        doc = DocxDocument(str(docx_path))
        parts = [p.text for p in doc.paragraphs if p.text.strip()]
        text = "\n".join(parts).strip()
        return text if text else None
    except Exception as exc:
        console.print(f"[bold red]DOCX extraction failed [{docx_path.name}]: {exc}[/bold red]")
        return None


# ---------------------------------------------------------------------------
# Gemini-powered analysis
# ---------------------------------------------------------------------------

def extract_jd_details_with_gemini(jd_text: str) -> dict[str, str]:
    """Extract position title and job ID from JD text via Gemini."""
    prompt = (
        "You are an HR assistant. Extract the following from the Job Description below "
        "and respond with ONLY valid JSON — no markdown, no explanation.\n\n"
        'Return exactly: {"position_title": "...", "job_id": "..."}\n'
        'Use "N/A" for any field not present.\n\n'
        f"Job Description:\n{jd_text[:4000]}"
    )
    result = _call_gemini_api(prompt)
    if not isinstance(result, dict):
        return {"position_title": "N/A", "job_id": "N/A"}
    return {
        "position_title": str(result.get("position_title", "N/A")),
        "job_id": str(result.get("job_id", "N/A")),
    }


def process_cv_with_gemini(
    cv_text: str,
    jd_full_text: str,
    jd_extracted_details: dict[str, str],
) -> dict[str, Any] | None:
    """Analyse a CV against the JD and return structured candidate data."""
    position = jd_extracted_details.get("position_title", "N/A")
    job_id = jd_extracted_details.get("job_id", "N/A")

    prompt = (
        "You are an expert HR recruiter. Analyse the CV against the Job Description "
        "and respond with ONLY valid JSON — no markdown, no explanation.\n\n"
        "Return exactly this structure:\n"
        "{\n"
        '  "full_name": "...",\n'
        '  "email": "...",\n'
        '  "contact_number": "...",\n'
        '  "skills": ["skill1", "skill2"],\n'
        '  "experience_summary": "2-3 sentence summary (max 400 chars)",\n'
        '  "match_score": 75,\n'
        '  "ranking_category": "High Fit",\n'
        '  "ranking_reason": "2-3 sentence explanation (max 400 chars)"\n'
        "}\n\n"
        "Rules:\n"
        "- match_score: integer 0-100\n"
        '- ranking_category: exactly "High Fit" (80-100), "Medium Fit" (50-79), or "Low Fit" (0-49)\n'
        "- skills: list of strings, max 15 items\n"
        '- Use "N/A" for any field not found\n\n'
        f"Job Description (Position: {position}, ID: {job_id}):\n"
        f"{jd_full_text[:3000]}\n\n"
        f"CV:\n{cv_text[:3000]}"
    )
    result = _call_gemini_api(prompt)
    return result if isinstance(result, dict) else None


# ---------------------------------------------------------------------------
# Notion integration
# ---------------------------------------------------------------------------

def check_notion_duplicate(
    notion: Any,
    db_id: str,
    email: str | None,
    job_id: str,
) -> bool:
    """Return True if a candidate with the same email + job ID already exists."""
    if notion is None or not email or email == "N/A":
        return False
    filters: list[dict[str, Any]] = [
        {"property": "Email", "email": {"equals": email}}
    ]
    if job_id and job_id != "N/A":
        filters.append(
            {"property": "Job ID (JD)", "rich_text": {"equals": job_id}}
        )
    try:
        response = notion.databases.query(
            database_id=db_id,
            filter={"and": filters} if len(filters) > 1 else filters[0],
        )
        return len(response.get("results", [])) > 0
    except Exception as exc:
        console.print(f"[yellow]Notion duplicate check failed: {exc}[/yellow]")
        return False


def create_notion_page(
    notion: Any,
    db_id: str,
    candidate_data: dict[str, Any],
    jd_details: dict[str, str],
    cv_filename: str,
) -> bool:
    """Create a Notion database entry for the candidate."""
    if notion is None:
        return True

    def rich_text(value: str) -> dict[str, Any]:
        return {"rich_text": [{"text": {"content": _truncate(str(value))}}]}

    properties: dict[str, Any] = {
        "Candidate Name": {
            "title": [{"text": {"content": _truncate(str(candidate_data.get("full_name", "N/A")))}}]
        },
        "CV Filename": rich_text(cv_filename),
        "Position Title (JD)": rich_text(jd_details.get("position_title", "N/A")),
        "Job ID (JD)": rich_text(jd_details.get("job_id", "N/A")),
        "Experience Summary": rich_text(candidate_data.get("experience_summary", "N/A")),
        "AI Ranking Reason": rich_text(candidate_data.get("ranking_reason", "N/A")),
        "Processing Date": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
        "Status": {"select": {"name": "New - AI Processed"}},
    }

    email_val = candidate_data.get("email")
    if email_val and email_val != "N/A":
        properties["Email"] = {"email": str(email_val)}

    contact_val = candidate_data.get("contact_number")
    if contact_val and contact_val != "N/A":
        properties["Contact Number"] = {"phone_number": str(contact_val)}

    skills_list = candidate_data.get("skills", [])
    if isinstance(skills_list, list) and skills_list:
        properties["Skills"] = {
            "multi_select": [{"name": _truncate(str(s), 99)} for s in skills_list if s]
        }

    match_score = candidate_data.get("match_score")
    if isinstance(match_score, (int, float)):
        properties["Match Score"] = {"number": match_score}

    ranking_category = candidate_data.get("ranking_category")
    if ranking_category and ranking_category != "N/A":
        properties["Ranking Category"] = {"select": {"name": str(ranking_category)}}

    try:
        notion.pages.create(parent={"database_id": db_id}, properties=properties)
        return True
    except Exception as exc:
        console.print(f"[bold red]Notion page creation failed: {exc}[/bold red]")
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"ai-recruitment-agent v{__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: Annotated[
        Optional[bool],
        typer.Option(
            "--version", "-V",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = None,
) -> None:
    """AI-powered CV screening CLI."""
    if ctx.invoked_subcommand is None:
        console.print(
            Panel(
                "[bold cyan]AI Recruitment Scanning Agent[/bold cyan]\n\n"
                "Screens CVs against a Job Description using [bold]Google Gemini[/bold]\n"
                "and pushes ranked candidates into a [bold]Notion database[/bold].",
                title="[bold]ai-recruit[/bold]",
                border_style="cyan",
                padding=(1, 2),
            )
        )
        console.print("[bold]Usage:[/bold]")
        console.print(
            "  ai-recruit process [green]<CV_FOLDER>[/green] [green]<JD_PDF>[/green] "
            "[[yellow]--notion-db-id[/yellow] [yellow]<DB_ID>[/yellow]]\n"
        )
        console.print("[bold]Configure via .env:[/bold]")
        console.print("  GOOGLE_GEMINI_API_KEY=...")
        console.print("  NOTION_API_KEY=...")
        console.print("  DEFAULT_NOTION_DB_ID=...\n")
        console.print(
            "Run [cyan]ai-recruit process --help[/cyan] for full usage details."
        )


@app.command(name="process", help="Screen CVs in a folder against a Job Description PDF.")
def process_documents(
    cv_folder_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            resolve_path=True,
            help="Folder containing CV files (.pdf / .docx).",
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
            help="Job Description PDF file.",
        ),
    ],
    notion_db_id_cli: Annotated[
        Optional[str],
        typer.Option(
            "--notion-db-id", "-n",
            help="Notion database ID (overrides DEFAULT_NOTION_DB_ID in .env).",
        ),
    ] = None,
) -> None:
    """Screen CVs against a Job Description and push results to Notion."""
    # --- Pre-run validation ---
    errors: list[str] = []
    if not GOOGLE_GEMINI_API_KEY:
        errors.append("GOOGLE_GEMINI_API_KEY not found")
    if not NOTION_API_KEY:
        errors.append("NOTION_API_KEY not found")

    final_notion_db_id = notion_db_id_cli or DEFAULT_NOTION_DB_ID
    if not final_notion_db_id:
        errors.append("Notion Database ID is not provided (use --notion-db-id or set DEFAULT_NOTION_DB_ID in .env)")

    if errors:
        for err in errors:
            console.print(f"[bold red]✗[/bold red] {err}")
        raise typer.Exit(code=1)

    console.print(f"[bold green]✓[/bold green] Pre-run checks passed.")
    console.print(f"[dim]Notion DB: {final_notion_db_id}[/dim]")

    # --- Notion initialisation ---
    notion_client_instance: Any = None
    if NotionClient is not None:
        try:
            notion_client_instance = NotionClient(auth=NOTION_API_KEY)
            notion_client_instance.databases.retrieve(database_id=final_notion_db_id)
            console.print("[bold green]✓[/bold green] Notion connection established.")
        except Exception as exc:
            console.print(f"[bold red]✗ Notion initialization failed:[/bold red] {exc}")
            raise typer.Exit(code=1)

    # --- JD processing ---
    console.print(f"\n[bold]Reading JD:[/bold] {jd_pdf_path.name}")
    jd_text_content = extract_text_from_pdf(jd_pdf_path)
    if not jd_text_content:
        console.print(
            f"[bold red]✗[/bold red] Could not extract text from JD: {jd_pdf_path.name}\n"
            "[dim]The file may be scanned, image-based, or password-protected.[/dim]"
        )
        raise typer.Exit(code=1)

    jd_extracted_details = extract_jd_details_with_gemini(jd_text_content)
    console.print(
        f"[bold green]✓[/bold green] JD parsed — "
        f"Position: [cyan]{jd_extracted_details['position_title']}[/cyan]  "
        f"Job ID: [cyan]{jd_extracted_details['job_id']}[/cyan]"
    )

    # --- CV discovery ---
    cv_files = sorted(
        f for f in cv_folder_path.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_CV_FORMATS
    )
    total_in_folder = sum(1 for _ in cv_folder_path.iterdir())

    if not cv_files:
        console.print(
            f"\n[yellow]No supported CV files (.pdf, .docx) found in:[/yellow] {cv_folder_path}"
        )
        raise typer.Exit(code=0)

    console.print(f"\n[bold]Found {len(cv_files)} CV(s) to process.[/bold]\n")

    stats = {
        "total_in_folder": total_in_folder,
        "found": len(cv_files),
        "success": 0,
        "duplicates": 0,
        "failed": 0,
    }

    # --- CV processing loop ---
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[cyan]{task.completed}/{task.total}[/cyan]"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("Starting...", total=len(cv_files))

        for cv_path in cv_files:
            progress.update(task, description=f"[bold]{cv_path.name}[/bold]")

            # Extract text
            cv_text = (
                extract_text_from_pdf(cv_path)
                if cv_path.suffix.lower() == ".pdf"
                else extract_text_from_docx(cv_path)
            )
            if not cv_text:
                console.print(f"  [yellow]⚠[/yellow]  Skipped (empty/unreadable): {cv_path.name}")
                stats["failed"] += 1
                progress.advance(task)
                continue

            # Gemini analysis
            candidate_data = process_cv_with_gemini(cv_text, jd_text_content, jd_extracted_details)
            if not candidate_data:
                console.print(f"  [yellow]⚠[/yellow]  Gemini analysis failed: {cv_path.name}")
                stats["failed"] += 1
                progress.advance(task)
                continue

            # Duplicate check
            email = candidate_data.get("email")
            if check_notion_duplicate(
                notion_client_instance,
                final_notion_db_id,
                str(email) if email else None,
                jd_extracted_details.get("job_id", "N/A"),
            ):
                console.print(f"  [dim]↩  Duplicate skipped:[/dim] {cv_path.name}")
                stats["duplicates"] += 1
                progress.advance(task)
                continue

            # Push to Notion
            if create_notion_page(
                notion_client_instance,
                final_notion_db_id,
                candidate_data,
                jd_extracted_details,
                cv_path.name,
            ):
                score = candidate_data.get("match_score", "?")
                category = candidate_data.get("ranking_category", "?")
                console.print(
                    f"  [green]✓[/green]  {cv_path.name} — "
                    f"[bold]{category}[/bold] ([cyan]{score}/100[/cyan])"
                )
                stats["success"] += 1
            else:
                stats["failed"] += 1

            progress.advance(task)

    # --- Summary ---
    console.print()
    table = Table(title="Processing Summary", show_lines=True, border_style="dim")
    table.add_column("Metric", style="bold")
    table.add_column("Count", justify="right")
    table.add_row("Total files in folder", str(stats["total_in_folder"]))
    table.add_row("Supported CV files found", str(stats["found"]))
    table.add_row(
        "Successfully processed & added to Notion",
        Text(str(stats["success"]), style="bold green"),
    )
    table.add_row("Skipped (duplicates)", str(stats["duplicates"]))
    table.add_row(
        "Failed",
        Text(str(stats["failed"]), style="bold red") if stats["failed"] else str(stats["failed"]),
    )
    console.print(table)
    console.print(
        f"\n[bold green]Done.[/bold green] "
        f"{stats['success']} candidate(s) added to Notion database [dim]{final_notion_db_id}[/dim]"
    )


@app.command(name="setup-notion", help="Add required properties to an existing Notion database.")
def setup_notion(
    notion_db_id: Annotated[
        Optional[str],
        typer.Option(
            "--notion-db-id", "-n",
            help="Notion database ID (overrides DEFAULT_NOTION_DB_ID in .env).",
        ),
    ] = None,
) -> None:
    """Configure a Notion database with all properties required for CV screening."""
    errors: list[str] = []
    if not NOTION_API_KEY:
        errors.append("NOTION_API_KEY not found")

    final_db_id = notion_db_id or DEFAULT_NOTION_DB_ID
    if not final_db_id:
        errors.append("Notion Database ID not provided (use --notion-db-id or set DEFAULT_NOTION_DB_ID in .env)")

    if errors:
        for err in errors:
            console.print(f"[bold red]✗[/bold red] {err}")
        raise typer.Exit(code=1)

    if NotionClient is None:
        console.print("[bold red]notion-client not installed.[/bold red]")
        raise typer.Exit(code=1)

    try:
        notion = NotionClient(auth=NOTION_API_KEY)
        db = notion.databases.retrieve(database_id=final_db_id)
    except Exception as exc:
        console.print(f"[bold red]✗ Cannot connect to Notion database:[/bold red] {exc}")
        raise typer.Exit(code=1)

    db_title_blocks = db.get("title", [])
    db_name = db_title_blocks[0].get("plain_text", final_db_id) if db_title_blocks else final_db_id
    console.print(f"[bold green]✓[/bold green] Connected: [cyan]{db_name}[/cyan]\n")

    existing_props: dict[str, Any] = db.get("properties", {})
    existing_names = set(existing_props.keys())

    # Rename the title property to "Candidate Name" if needed
    title_key = next((k for k, v in existing_props.items() if v.get("type") == "title"), None)
    if title_key and title_key != "Candidate Name":
        try:
            notion.databases.update(
                database_id=final_db_id,
                properties={title_key: {"name": "Candidate Name"}},
            )
            console.print(f"  [green]✓[/green]  Renamed '{title_key}' → Candidate Name")
            existing_names.discard(title_key)
            existing_names.add("Candidate Name")
        except Exception as exc:
            console.print(f"  [yellow]⚠[/yellow]  Could not rename title property: {exc}")
            console.print(f"       Manually rename '{title_key}' to 'Candidate Name' in Notion.")
    elif title_key == "Candidate Name":
        console.print(f"  [dim]↩  Already exists:[/dim] Candidate Name")

    required: dict[str, Any] = {
        "Email": {"email": {}},
        "Contact Number": {"phone_number": {}},
        "Skills": {"multi_select": {}},
        "Position Title (JD)": {"rich_text": {}},
        "Job ID (JD)": {"rich_text": {}},
        "Experience Summary": {"rich_text": {}},
        "AI Ranking Reason": {"rich_text": {}},
        "Match Score": {"number": {"format": "number"}},
        "Ranking Category": {
            "select": {
                "options": [
                    {"name": "High Fit", "color": "green"},
                    {"name": "Medium Fit", "color": "yellow"},
                    {"name": "Low Fit", "color": "red"},
                ]
            }
        },
        "Status": {
            "select": {
                "options": [{"name": "New - AI Processed", "color": "blue"}]
            }
        },
        "CV Filename": {"rich_text": {}},
        "Processing Date": {"date": {}},
    }

    for prop in (k for k in required if k in existing_names):
        console.print(f"  [dim]↩  Already exists:[/dim] {prop}")

    to_add = {k: v for k, v in required.items() if k not in existing_names}
    if to_add:
        try:
            notion.databases.update(database_id=final_db_id, properties=to_add)
            for prop in to_add:
                console.print(f"  [green]✓[/green]  Added: {prop}")
        except Exception as exc:
            console.print(f"[bold red]✗ Failed to add properties:[/bold red] {exc}")
            raise typer.Exit(code=1)

    console.print(
        f"\n[bold green]Notion database is ready.[/bold green] "
        f"Run [cyan]ai-recruit process[/cyan] to start screening CVs."
    )


if __name__ == "__main__":
    app()

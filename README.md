# AI Recruitment Scanning Agent

[![PyPI version](https://img.shields.io/pypi/v/ai-recruitment-agent)](https://pypi.org/project/ai-recruitment-agent/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/ai-recruitment-agent)](https://pypi.org/project/ai-recruitment-agent/)
[![PyPI - License](https://img.shields.io/pypi/l/ai-recruitment-agent)](https://pypi.org/project/ai-recruitment-agent/)

A CLI tool that screens CVs against a Job Description using Google Gemini and populates a Notion database with ranked candidate profiles.

**PyPI:** https://pypi.org/project/ai-recruitment-agent/

## Stack

- **Python 3.9+** with [Typer](https://typer.tiangolo.com/) CLI
- **Google Gemini 1.5 Flash** — JD parsing + CV analysis
- **Notion API** — candidate record storage
- **pdfplumber** / **python-docx** — PDF and DOCX text extraction

## Install from PyPI

```bash
pip install ai-recruitment-agent
```

## Setup

```bash
# 1. Clone and enter the repo
git clone https://github.com/kneeraazon404/ai-recruitment-cli-agent && cd ai-recruitment-cli-agent

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Install in editable mode (includes all dependencies)
pip install -e .

# 4. Configure environment variables
cp .env.example .env
```

Edit `.env`:

```env
GOOGLE_GEMINI_API_KEY=your_gemini_api_key
NOTION_API_KEY=your_notion_integration_secret
DEFAULT_NOTION_DB_ID=your_notion_database_id
```

## Notion Setup

1. Create an integration at [notion.so/my-integrations](https://www.notion.so/my-integrations) with Read, Insert, and Update permissions.
2. Share your target database with the integration (database `•••` > Connections).
3. Required database properties:

| Property | Type |
|---|---|
| Candidate Name | Title |
| Email | Email |
| Contact Number | Phone |
| Skills | Multi-select |
| Position Title (JD) | Text |
| Job ID (JD) | Text |
| Experience Summary | Text |
| AI Ranking Reason | Text |
| Match Score | Number |
| Ranking Category | Select (`High Fit`, `Medium Fit`, `Low Fit`) |
| Status | Select (`New - AI Processed`) |
| CV Filename | Text |
| Processing Date | Date |

## Usage

```bash
# Show help
ai-recruit
ai-recruit process --help

# Run
ai-recruit process <CV_FOLDER> <JD_PDF> [--notion-db-id <DB_ID>]

# Example
ai-recruit process ./cvs/ ./jds/job_description.pdf --notion-db-id xxxx-xxxx-xxxx
```

`--notion-db-id` overrides `DEFAULT_NOTION_DB_ID` from `.env`.

## What it does

1. Validates API keys and Notion database access on startup.
2. Extracts text from the JD PDF and pulls out Position Title and Job ID via Gemini.
3. Iterates all `.pdf` and `.docx` files in the CV folder.
4. For each CV: extracts text, sends to Gemini with the JD for scoring (0–100), ranking, and structured field extraction.
5. Checks Notion for duplicates by email + Job ID before inserting.
6. Prints a summary table of processed / skipped / failed counts.

## Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Publishing to PyPI

PyPI is free. One-time setup:

```bash
# 1. Register a free account at https://pypi.org/account/register/
# 2. Generate an API token at https://pypi.org/manage/account/token/
# 3. Install build tools
pip install build twine

# 4. Build the distribution
python -m build
# Outputs: dist/ai_recruitment_agent-x.x.x.tar.gz and .whl

# 5. Upload to PyPI
twine upload dist/*
# Enter __token__ as username, paste your API token as password

# After publishing, anyone can install it with:
# pip install ai-recruitment-agent
```

To release a new version: bump `version` in `pyproject.toml` and `ai_recruitment_agent/__init__.py`, rebuild, and re-upload.

## Troubleshooting

| Issue | Fix |
|---|---|
| `GOOGLE_GEMINI_API_KEY not found` | Check `.env` is present and key is valid |
| `NOTION_API_KEY not found` | Verify integration secret in `.env` |
| `Notion initialization failed` | Confirm database is shared with the integration |
| `Could not extract text from JD PDF` | PDF may be scanned/password-protected |
| Duplicate entries appearing | Ensure `Email` and `Job ID (JD)` properties exist with exact names |

# AI Recruitment Scanning Agent

[![PyPI version](https://img.shields.io/pypi/v/ai-recruitment-agent)](https://pypi.org/project/ai-recruitment-agent/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/ai-recruitment-agent)](https://pypi.org/project/ai-recruitment-agent/)
[![PyPI - License](https://img.shields.io/pypi/l/ai-recruitment-agent)](https://pypi.org/project/ai-recruitment-agent/)


A CLI tool that screens CVs against a Job Description using **Google Gemini 1.5 Flash** and pushes ranked candidate profiles into a **Notion database** — one command, zero manual effort.

**PyPI:** https://pypi.org/project/ai-recruitment-agent/

---

## Install

```bash
pip install ai-recruitment-agent
```

## Configure

Copy `.env.example` to `.env` and fill in your credentials:

```env
GOOGLE_GEMINI_API_KEY=your_gemini_api_key
NOTION_API_KEY=your_notion_integration_secret
DEFAULT_NOTION_DB_ID=your_notion_database_id
```

**Where to get these:**

| Key | Source |
|---|---|
| `GOOGLE_GEMINI_API_KEY` | https://aistudio.google.com/app/apikey |
| `NOTION_API_KEY` | https://www.notion.so/my-integrations → New integration → copy secret |
| `DEFAULT_NOTION_DB_ID` | Your Notion database URL: `notion.so/yourname/`**`THIS-PART`**`?v=...` |

## Setup Notion Database

Run once to add all required properties to your Notion database automatically:

```bash
ai-recruit setup-notion

# or with an explicit database ID:
ai-recruit setup-notion --notion-db-id xxxx-xxxx-xxxx-xxxx
```

> **Prerequisite:** Share your Notion database with the integration first — open the database → `•••` menu → **Connections** → add your integration.

The command adds 13 properties (`Email`, `Skills`, `Match Score`, `Ranking Category`, etc.), renames the title column to `Candidate Name`, and skips anything already present.

## Run

```bash
ai-recruit process <CV_FOLDER> <JD_PDF> [--notion-db-id <DB_ID>]
```

```bash
# Basic — reads DB ID from .env
ai-recruit process ./cvs/ ./jd.pdf

# Override Notion database
ai-recruit process ./cvs/ ./jd.pdf --notion-db-id xxxx-xxxx-xxxx-xxxx

# Other commands
ai-recruit setup-notion --help
ai-recruit --version
ai-recruit --help
ai-recruit process --help
```

## What it does

1. **Validates** API keys and Notion database access on startup.
2. **Reads** the JD PDF — extracts position title and job ID via Gemini.
3. **Iterates** all `.pdf` and `.docx` files in the CV folder with a live progress bar.
4. For each CV: **extracts** text → **sends** to Gemini → receives a score (0–100), ranking (`High Fit` / `Medium Fit` / `Low Fit`), and structured candidate data.
5. **Checks** Notion for duplicates by email + job ID before inserting.
6. **Pushes** a new page to your Notion database for each unique candidate.
7. **Prints** a summary table of processed / skipped / failed counts.

## Troubleshooting

| Error | Fix |
|---|---|
| `GOOGLE_GEMINI_API_KEY not found` | Check `.env` exists in your working directory and the key is valid |
| `NOTION_API_KEY not found` | Verify the integration secret in `.env` |
| `Notion initialization failed` | Confirm the database is shared with your integration |
| `Could not extract text from JD PDF` | PDF may be scanned, image-based, or password-protected |
| Duplicate entries appearing | Ensure `Email` and `Job ID (JD)` properties exist with exact names |
| Gemini API error | Check your quota at [aistudio.google.com](https://aistudio.google.com) |

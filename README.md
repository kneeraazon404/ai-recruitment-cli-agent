# AI Recruitment Scanning Agent

[![PyPI version](https://img.shields.io/pypi/v/ai-recruitment-agent)](https://pypi.org/project/ai-recruitment-agent/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/ai-recruitment-agent)](https://pypi.org/project/ai-recruitment-agent/)
[![PyPI - License](https://img.shields.io/pypi/l/ai-recruitment-agent)](https://pypi.org/project/ai-recruitment-agent/)

A CLI tool that screens CVs against a Job Description using Google Gemini and populates a Notion database with ranked candidate profiles.

**PyPI:** https://pypi.org/project/ai-recruitment-agent/

## Install

```bash
pip install ai-recruitment-agent
```

## Configure

Create a `.env` file in your working directory:

```env
GOOGLE_GEMINI_API_KEY=your_gemini_api_key
NOTION_API_KEY=your_notion_integration_secret
DEFAULT_NOTION_DB_ID=your_notion_database_id
```

**Where to get these:**
- **Gemini key** → https://aistudio.google.com/app/apikey
- **Notion key** → https://www.notion.so/my-integrations → New integration → copy the secret
- **Notion DB ID** → Open your Notion database in the browser — it's in the URL: `notion.so/yourname/THIS-PART?v=...`

## Run

```bash
ai-recruit process <CV_FOLDER> <JD_PDF> [--notion-db-id <DB_ID>]
```

```bash
# Example
ai-recruit process ./cvs/ ./jd.pdf --notion-db-id xxxx-xxxx-xxxx-xxxx

# Show help
ai-recruit --help
ai-recruit process --help
```

`--notion-db-id` overrides `DEFAULT_NOTION_DB_ID` from `.env`.

## Notion Database Setup

1. Create an integration at [notion.so/my-integrations](https://www.notion.so/my-integrations) with Read, Insert, and Update permissions.
2. Share your target database with the integration (database `•••` > Connections).
3. Required properties:

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

## Troubleshooting

| Issue | Fix |
|---|---|
| `GOOGLE_GEMINI_API_KEY not found` | Check `.env` exists and key is valid |
| `NOTION_API_KEY not found` | Verify integration secret in `.env` |
| `Notion initialization failed` | Confirm database is shared with the integration |
| `Could not extract text from JD PDF` | PDF may be scanned or password-protected |
| Duplicate entries appearing | Ensure `Email` and `Job ID (JD)` properties exist with exact names |

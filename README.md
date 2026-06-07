# AI Recruitment Scanning Agent

[![PyPI version](https://img.shields.io/pypi/v/ai-recruitment-agent)](https://pypi.org/project/ai-recruitment-agent/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/ai-recruitment-agent)](https://pypi.org/project/ai-recruitment-agent/)
[![PyPI - License](https://img.shields.io/pypi/l/ai-recruitment-agent)](https://pypi.org/project/ai-recruitment-agent/)

A CLI tool that screens CVs against a Job Description using **Google Gemini 1.5 Flash** and pushes ranked candidate profiles into a **Notion database** — one command, zero manual effort.

**Workflow:** CV Folder → Extract Text → Gemini Screening → Notion Database  
**PyPI:** https://pypi.org/project/ai-recruitment-agent/

---

## ✨ Features

- **Automated CV Screening** — Analyze multiple CVs against a job description in seconds
- **AI-Powered Ranking** — Uses Google Gemini 1.5 Flash for intelligent candidate matching
- **Real-Time Notion Sync** — Automatically pushes results to your Notion database
- **Duplicate Detection** — Prevents duplicate entries by email + job ID
- **Live Progress Tracking** — See processing status with a progress bar
- **Structured Data Extraction** — Captures email, skills, experience, and more
- **Batch Processing** — Handles both PDF and DOCX files seamlessly

---

## Requirements

- **Python:** 3.8 or higher
- **APIs:** Google Gemini API key + Notion integration
- **PDFs:** Must be searchable (not scanned/image-based)
- **Rate Limiting:** Consider Gemini API quotas for large batches (50+ CVs)

---

## Quick Start

### 1. Install

```bash
pip install ai-recruitment-agent
```

### 2. Get Your Credentials

| Credential | Where to Find |
|---|---|
| `GOOGLE_GEMINI_API_KEY` | https://aistudio.google.com/app/apikey |
| `NOTION_API_KEY` | https://www.notion.so/my-integrations → Create new integration → Copy secret |
| `NOTION_DB_ID` | Your Notion database URL: `notion.so/yourname/`**`THIS-PART`**`?v=...` |

### 3. Configure

Copy `.env.example` to `.env`:

```env
GOOGLE_GEMINI_API_KEY=your_gemini_api_key
NOTION_API_KEY=your_notion_integration_secret
DEFAULT_NOTION_DB_ID=your_notion_database_id
```

### 4. Setup Notion Database

Share your Notion database with the integration first:
1. Open your Notion database
2. Click `•••` (more options)
3. Select **Connections**
4. Add your integration

Then run:

```bash
ai-recruit setup-notion
```

This automatically creates 13 properties and prepares your database for candidate data.

### 5. Run

```bash
ai-recruit process ./cvs/ ./jd.pdf
```

Done! Results appear in your Notion database.

---

## Database Properties

The `setup-notion` command creates these properties automatically:

| Property | Type | Description |
|---|---|---|
| `Candidate Name` | Title | Extracted from CV filename or document |
| `Email` | Email | Candidate email address |
| `Phone` | Text | Candidate phone number |
| `Skills` | Text | Comma-separated list of extracted skills |
| `Experience Years` | Number | Years of professional experience |
| `Match Score` | Number | 0–100 scoring from Gemini analysis |
| `Ranking Category` | Select | `High Fit` / `Medium Fit` / `Low Fit` |
| `Job ID (JD)` | Text | Position title from JD PDF |
| `Summary` | Text | Key highlights from CV |
| `Strengths` | Text | Top 3 matching areas |
| `Gaps` | Text | Missing skills or experience |
| `Processed At` | Date | Timestamp of processing |
| `Source File` | Text | Original CV filename |

---

## Usage

### Basic Commands

```bash
# Screen CVs using database ID from .env
ai-recruit process ./cvs/ ./jd.pdf

# Override database ID
ai-recruit process ./cvs/ ./jd.pdf --notion-db-id xxxx-xxxx-xxxx-xxxx

# Setup Notion (one-time)
ai-recruit setup-notion

# With explicit database ID
ai-recruit setup-notion --notion-db-id xxxx-xxxx-xxxx-xxxx
```

### Help & Info

```bash
ai-recruit --help
ai-recruit process --help
ai-recruit setup-notion --help
ai-recruit --version
```

---

## How It Works

1. **Validates** API keys and Notion database access on startup
2. **Reads** the JD PDF — extracts position title and key requirements via Gemini
3. **Iterates** all `.pdf` and `.docx` files in the CV folder with a live progress bar
4. For each CV:
   - Extracts text content
   - Sends to Gemini for analysis
   - Receives a match score (0–100), ranking category, and structured data
5. **Checks** Notion for duplicates by email + job ID before inserting
6. **Pushes** a new page to Notion for each unique candidate
7. **Prints** a summary table: processed ✓ / skipped ⊘ / failed ✗

---

## Troubleshooting

### Credential Issues

| Error | Fix |
|---|---|
| `GOOGLE_GEMINI_API_KEY not found` | Ensure `.env` exists in your working directory. Check key validity at [aistudio.google.com](https://aistudio.google.com) |
| `NOTION_API_KEY not found` | Verify the integration secret in `.env`. Regenerate at https://www.notion.so/my-integrations if needed |
| `Notion initialization failed` | Confirm the database is shared with your integration (see Quick Start step 4) |

### Processing Issues

| Error | Fix |
|---|---|
| `Could not extract text from JD PDF` | PDF must be searchable, not scanned or image-based. Try converting with a PDF tool |
| Duplicate entries appearing | Ensure `Email` and `Job ID (JD)` properties exist in Notion with exact names. Run `setup-notion` again if needed |
| CVs not being processed | Check that files are `.pdf` or `.docx`. Other formats are skipped silently |

### Gemini API Issues

| Error | Fix |
|---|---|
| `Gemini API error: 429` | Rate limit exceeded. Wait 60 seconds before retrying. Process in smaller batches |
| `Gemini API error: 403` | API key is invalid or quota is exhausted. Check [aistudio.google.com](https://aistudio.google.com) |
| `Gemini API error: 500` | Temporary API outage. Retry in a few minutes |

### PDF Extraction Issues

| Symptom | Solution |
|---|---|
| "Could not extract text from CV PDF" | PDF may be scanned, image-based, or password-protected. Use OCR or convert first |
| Empty or garbled text extracted | Try a different PDF reader or convert DOCX → PDF |
| Poor match scores | Ensure CVs are well-formatted and contain clear skill/experience sections |

---

## Example Output

```
Processing CVs...

✓ john_doe.pdf → High Fit (87/100) — john@example.com
✓ jane_smith.pdf → High Fit (91/100) — jane@example.com
✓ bob_wilson.pdf → Medium Fit (62/100) — bob@example.com
⊘ resume_scan.pdf → Skipped (scanned PDF, no text)
✗ invalid_format.txt → Failed (unsupported format)

Summary:
━━━━━━━━━━━━━━━━━━━━━━━━━━
  Processed:  3
  Skipped:    1
  Failed:     1
━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Contributing

Found a bug or have a feature request? [Open an issue](https://github.com/karkinirajan/ai-recruitment-cli-agent/issues) — contributions welcome!

---

## License

MIT License — see [LICENSE](./LICENSE) file for details.

---

## Support

- **Issues:** https://github.com/karkinirajan/ai-recruitment-cli-agent/issues
- **PyPI:** https://pypi.org/project/ai-recruitment-agent/
- **Documentation:** See this README for full details

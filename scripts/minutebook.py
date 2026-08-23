#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "pyyaml>=6.0",
# ]
# ///
"""
minutebook.py

SF Pride Digital Minutebook — Unified Ingestion, AI Normalization & Verification.
Can be executed directly via:
    pipx run scripts/minutebook.py --year 2024
    pipx run scripts/minutebook.py --file board/2023/2023-05-03.md
    pipx run scripts/minutebook.py --verify-only --year 2023
"""

import os
import re
import sys
try:
    import yaml
except ImportError:
    yaml = None
import shutil
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

DEFAULT_MODEL = "openrouter/google/gemini-3.7-flash"
TEAM_DRIVE_ID = "0AO8MJQcSxn5CUk9PVA"
REMOTE_NAME = "cdn-gd"

LIGATURE_MAP = {
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬀ": "ff",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "’": "'",
    "‘": "'",
    "“": '"',
    "”": '"',
    "–": "-",
    "—": "—",
    "\u00a0": " ",
}

MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12
}

def find_repo_root() -> Path:
    """Finds the root of the minutebook repository by looking for _config.yml."""
    curr = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd().resolve()
    for parent in [curr, *curr.parents]:
        if (parent / "_config.yml").exists() and (parent / "templates").exists():
            return parent
    return Path.cwd().resolve()

def calculate_first_wednesday(year: int, month: int) -> int:
    for day in range(1, 8):
        if datetime(year, month, day).weekday() == 2:
            return day
    return 1

def calculate_second_tuesday(year: int, month: int) -> int:
    tuesdays = [d for d in range(1, 15) if datetime(year, month, d).weekday() == 1]
    return tuesdays[1] if len(tuesdays) > 1 else tuesdays[0]

def extract_date_from_text(text: str, fallback_year: int = None) -> str:
    for line in text.split("\n")[:25]:
        line_clean = line.strip()
        m = re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,)?\s+(\d{4})\b", line_clean, re.IGNORECASE)
        if m:
            mo_str, day_str, yr_str = m.groups()
            mo = MONTH_MAP[mo_str.lower()]
            return f"{yr_str}-{int(mo):02d}-{int(day_str):02d}"
            
        m = re.search(r"\b(20\d{2})[-/\.]([A-Za-z]{3,9})[-/\.](\d{1,2})\b", line_clean)
        if m:
            yr_str, mo_str, day_str = m.groups()
            mo_key = mo_str.lower()[:3]
            if mo_key in MONTH_MAP:
                return f"{yr_str}-{MONTH_MAP[mo_key]:02d}-{int(day_str):02d}"
                
        m = re.search(r"\b(20\d{2})[-/\.](0?[1-9]|1[0-2])[-/\.](0?[1-9]|[12]\d|3[01])\b", line_clean)
        if m:
            yr, mo, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return f"{yr:04d}-{mo:02d}-{day:02d}"
            
        m = re.search(r"\b(0?[1-9]|1[0-2])[-/\.](0?[1-9]|[12]\d|3[01])[-/\.](20\d{2}|\d{2})\b", line_clean)
        if m:
            mo, day, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if yr < 100: yr = 2000 + yr
            return f"{yr:04d}-{mo:02d}-{day:02d}"
    return None

def extract_date_from_filename_or_path(path: str) -> str:
    # 1. Match YYYY.MM.DD or YYYY-MM-DD or YYYY_MM_DD or YYYYMMDD
    m = re.search(r"\b(20\d{2})[._\-]?(0[1-9]|1[0-2])[._\-]?(0[1-9]|[12]\d|3[01])\b", path)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # 2. Match MM_DD_YYYY or M_D_YYYY or MM.DD.YYYY or M.D.YY or M_D_YY (e.g. 1_7_2014, 4.1.14)
    m = re.search(r"\b([01]?\d)[_.\-/]([0-3]?\d)[_.\-/](\d{2,4})\b", path)
    if m:
        mo, day, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= day <= 31:
            if yr < 100: yr = 2000 + yr
            if 2000 <= yr <= 2035:
                return f"{yr:04d}-{mo:02d}-{day:02d}"

    # 3. Match Month_DD_YYYY or MonthDD_YYYY e.g. May3BOD23
    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*[\s_\-]*(0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?[\s_\-]*(?:bod|sfpride|sf pride)?[\s_\-]*(\d{2,4})\b", path, re.IGNORECASE)
    if m:
        mo_str, day_str, yr_str = m.groups()
        mo = MONTH_MAP[mo_str.lower()[:3]]
        yr = int(yr_str)
        if yr < 100: yr = 2000 + yr
        return f"{yr:04d}-{mo:02d}-{int(day_str):02d}"

    # 4. Match Month + Year only (e.g. "Nov 2014_.docx")
    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*[,\s_\-]+(\d{4})\b", path, re.IGNORECASE)
    if m:
        mo_str, yr_str = m.groups()
        mo = MONTH_MAP[mo_str.lower()[:3]]
        yr = int(yr_str)
        if "member" in path.lower() or "gpm" in path.lower():
            day = calculate_second_tuesday(yr, mo)
        else:
            day = calculate_first_wednesday(yr, mo)
        return f"{yr:04d}-{mo:02d}-{day:02d}"

    # 5. Match YYYYMMDD with placeholder day like 202210DD
    m = re.search(r"\b(20\d{2})([01]\d)DD\b", path, re.IGNORECASE)
    if m:
        yr = int(m.group(1))
        mo = int(m.group(2))
        day = calculate_first_wednesday(yr, mo)
        return f"{yr:04d}-{mo:02d}-{day:02d}"

    # 6. Match folder structure Meetings YYYY/MM-YY
    m = re.search(r"Meetings\s+(20\d{2})/([01]\d)-\1", path)
    if m:
        yr = int(m.group(1))
        mo = int(m.group(2))
        day = calculate_first_wednesday(yr, mo)
        return f"{yr:04d}-{mo:02d}-{day:02d}"

    return None

def pre_clean_text(raw_text: str) -> str:
    text = raw_text.replace("\x0c", "\n").replace("\f", "\n")
    for k, v in LIGATURE_MAP.items():
        text = text.replace(k, v)
    text = re.sub(r"\[(.*?)\]\{\.underline\}", r"\1", text)
    text = re.sub(r"\^([a-zA-Z0-9\.]+)\^", r"\1", text)
    text = re.sub(r"\\([\"\'\$\*])", r"\1", text)
    text = re.sub(r"\\([\.])", r"\1", text)
    text = re.sub(r"^[ \t]*[•●○■]\s*", "- ", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def extract_frontmatter_and_body(content: str) -> tuple[dict, str]:
    fm_match = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
    if fm_match:
        try:
            fm = yaml.safe_load(fm_match.group(1))
            if isinstance(fm, dict):
                return fm, fm_match.group(2).strip()
        except Exception:
            pass
    return {}, content

def convert_to_md_text(local_path: Path) -> str:
    local_str = str(local_path)
    if local_str.endswith(".pdf"):
        res = subprocess.run(["pdftotext", "-layout", local_str, "-"], capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"pdftotext failed for {local_path}: {res.stderr}")
        return res.stdout
    elif local_str.endswith(".doc") and not local_str.endswith(".docx"):
        # Legacy Microsoft Word 97-2004 format (.doc)
        if shutil.which("textutil"):
            res = subprocess.run(["textutil", "-convert", "txt", local_str, "-stdout"], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout
        for tool in ["catdoc", "antiword"]:
            if shutil.which(tool):
                res = subprocess.run([tool, local_str], capture_output=True, text=True)
                if res.returncode == 0 and res.stdout.strip():
                    return res.stdout
        raise RuntimeError(f"Cannot convert legacy .doc file {local_path}. textutil, catdoc, or antiword not available.")
    elif local_str.endswith(".docx"):
        cmd = ["pandoc", local_str, "-t", "markdown", "--wrap=none"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout
        # Fallback to textutil if pandoc fails on malformed docx
        if shutil.which("textutil"):
            res2 = subprocess.run(["textutil", "-convert", "txt", local_str, "-stdout"], capture_output=True, text=True)
            if res2.returncode == 0 and res2.stdout.strip():
                return res2.stdout
        raise RuntimeError(f"Pandoc conversion failed for {local_path}: {res.stderr}")
    else:
        raise ValueError(f"Unsupported file type: {local_path}")

def run_rclone(args):
    cmd = [
        "rclone", *args,
        "--drive-team-drive", TEAM_DRIVE_ID,
        "--drive-root-folder-id", TEAM_DRIVE_ID
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"rclone error: {res.stderr.strip()}")
    return res.stdout

def list_drive_files(year=None):
    pattern = f"Meetings {year}/**" if year else "Meetings*/**"
    output = run_rclone(["lsf", "-R", f"{REMOTE_NAME}:General", "--include", pattern])
    return [l.strip() for l in output.split("\n") if l.strip() and not l.endswith("/")]

def is_valid_minute_doc(path):
    path_lower = path.lower()
    if not (path_lower.endswith(".docx") or path_lower.endswith(".doc") or path_lower.endswith(".pdf")):
        return False
    if any(kw in path_lower for kw in ["closed session", "closed-session", "closed_session", "executive session", "closed"]):
        return False
    if ("agenda" in path_lower or "report" in path_lower or "packet" in path_lower) and not ("minute" in path_lower or "minutes" in path_lower):
        return False
    if "minute" not in path_lower and "minutes" not in path_lower:
        return False
    return True

def download_file(remote_path, local_dest):
    local_dest.parent.mkdir(parents=True, exist_ok=True)
    full_remote = f"{REMOTE_NAME}:General/{remote_path}"
    run_rclone(["copyto", full_remote, str(local_dest)])

def ensure_year_index(year, doc_type="board", dry_run=False, repo_root=None):
    if repo_root is None:
        repo_root = find_repo_root()
    if doc_type == "board":
        year_dir = repo_root / "board" / str(year)
        index_file = year_dir / "index.md"
        if not index_file.exists():
            if dry_run:
                print(f"  [dry-run] Would create year index: {index_file.relative_to(repo_root)}")
                return
            year_dir.mkdir(parents=True, exist_ok=True)
            content = f"""---
layout: default
title: Board Meetings {year}
nav_order: {year}
parent: Board Meetings
has_children: true
---

# Board Meetings — {year}

Minutes from Board of Directors meetings held in {year}.
"""
            index_file.write_text(content)
            print(f"  Created year index: {index_file.relative_to(repo_root)}")

def build_normalization_prompt(raw_text: str, doc_date: str, doc_type: str = "board", status: str = "draft", repo_root: Path = None) -> str:
    if repo_root is None:
        repo_root = find_repo_root()
    templates_dir = repo_root / "templates"
    template_path = templates_dir / f"{doc_type}-meeting.md"
    if not template_path.exists():
        template_path = templates_dir / "board-meeting.md"
    exemplar_file = repo_root / "board" / "2022" / "2022-01-05.md"
    template_content = template_path.read_text() if template_path.exists() else ""
    exemplar_content = exemplar_file.read_text() if exemplar_file.exists() else ""
    
    prompt = f"""You are an expert records officer and parliamentarian for San Francisco Pride (San Francisco Lesbian, Gay, Bisexual, Transgender Pride Parade and Celebration Committee, Inc.).
Your task is to normalize raw extracted meeting minutes into clean, standardized, beautifully structured Markdown for our official digital minutebook.

### CRITICAL REQUIREMENTS & NON-MODIFICATION INVARIANTS:
1. **ZERO SUBSTANTIVE MODIFICATION**: You must NEVER alter, fabricate, add, or omit any motions, seconds, vote tallies, attendance records, financial figures, dates, quotes, speaker statements, or recorded actions.
2. **ZERO HALLUCINATION**:
   - DO NOT invent board members, attendees, motions, or discussions.
   - DO NOT insert empty placeholder sections for things that did not happen (e.g. if there was no Land Acknowledgement or no Closed Session in the source text, do NOT create one).
   - Only include sections and facts that actually occurred in the raw minutes.
3. **FAITHFUL FINANCIAL & ACTION DETAILS**: Every single dollar amount (e.g. $162k, $20,000), percentage, motion maker, seconder, and vote count (ayes/noes/abstain/unanimous/consensus) in the source text MUST be preserved accurately.
4. **KNOWN ROSTER & NAME DISAMBIGUATION**:
   When matching first names or abbreviated names in attendance or text, use this canonical roster for disambiguation:
   - Carolyn Wysinger (Board President 2022, Director)
   - Nguyen Pham (Board VP 2022, Board President 2023)
   - Janelle Luster (Director / Treasurer 2022, Board VP 2023)
   - Elizabeth Lanyon (Board Secretary 2022, Director)
   - Spring Collins (Director 2022, Board Secretary 2023)
   - Robert Louie (Board Treasurer 2023)
   - Joshua Smith / Josh Smith (Director)
   - Di'ara Reid / Di'Ara Reed (Director, through May 2023)
   - Maceo Persson (Director)
   - Manuel Alejandro Perez / Manuel Perez (Director)
   - Anjali Rimi (Director)
   - Linda Martley-Jordan (Director)
   - George Smith (Director)
   - Dr. Nas Mohamed (Director, from Oct 2023)
   - Adell Hanson-Kahn (Director, from Oct 2023)
   - Suzanne Ford (Board Treasurer early 2022, Interim ED 2022, Executive Director 2023)
   - Fred Lopez (Executive Director 2021-early 2022)
   - Marsha Levine (Community Relations Manager / Staff)
   - Chris Grafton / Chris Robert (Staff / Deputy Executive Director / Minutes)
   - Peter-Astrid Kane (Communications Manager)
   - RJB / Rachel Jacob Barnett (Director of Partnerships and Giving)
   DO NOT invent random last names for persons not in the roster.
5. **STANDARDIZED STRUCTURE & UNIFORMITY**:
   - Follow the structure of the template and exemplar below.
   - Output valid YAML frontmatter between `---` delimiters at the very top.
   - Use standard Markdown headings:
     `# Board Meeting — Month Day, YYYY` (using em-dash `—`)
     `## Attendance` (categorized into Board Members Present, Staff Present, Guests/Public, Absent, and Quorum confirmation)
     `---` (divider between major sections)
     `## Land Acknowledgement` (if occurred)
     `## Meeting Roles` (Timekeeper, Stack Monitor, Vibe Watch, if recorded)
     `## Mission Statement` (if read)
     `## Financial Protocol` (if read)
     `## Disclosures of Potential Conflicts of Interest` (if recorded)
     `## Approval of Agenda` (Motion, Second, Vote)
     `## Approval of Previous Minutes` (Motion, Second, Vote)
     `## Officer Reports` (with `### President's Report`, `### Vice President's Report`, `### Treasurer's Report`, `### Secretary's Report`)
     `## Executive Director's Report` or `## Agency Updates`
     `## Committee Reports` (with `### <Committee Name>` subsections)
     `## Old Business` / `## Unfinished Business`
     `## New Business`
     `## Announcements`
     `## Public Comment`
     `## In Memoriam`
     `## Adjournment` / `## Closed Session`
     `---`
     `*Minutes recorded by [Name]*` (if recorded)
6. **FRONTMATTER SCHEMA**:
   The YAML frontmatter MUST contain:
   ```yaml
   layout: default
   title: Board Meeting - Month D, YYYY
   date: {doc_date}
   nav_order: {int(doc_date.replace('-', ''))}
   parent: Board Meetings {doc_date.split('-')[0]}
   grand_parent: Board Meetings
   type: {doc_type}
   status: {status}
   presiding: <Name of presiding officer, e.g. Carolyn Wysinger or Nguyen Pham>
   secretary: <Name of secretary, e.g. Elizabeth Lanyon or Spring Collins>
   quorum: true
   attendees:
     - name: <Full Name>
       role: <Role, e.g. President, Vice President, Treasurer, Secretary, Director, Staff, Guest>
       present: true
     # Include absent board members with present: false
   location: <Zoom, In-Person / Location Name, or Hybrid>
   called_to_order: "<e.g. 7:03 PM>"
   adjourned: "<e.g. 8:34 PM>"
   ```
   Note on `attendees`: NEVER include action items, agenda names, or agenda phrases as attendee names.

---
### REFERENCE TEMPLATE:
```markdown
{template_content}
```

---
### REFERENCE GOLD-STANDARD EXEMPLAR:
```markdown
{exemplar_content}
```

---
### RAW EXTRACTED MINUTES TO NORMALIZE (Date: {doc_date}):
```markdown
{raw_text}
```

---
OUTPUT ONLY THE COMPLETE, NORMALIZED MARKDOWN DOCUMENT (INCLUDING YAML FRONTMATTER). DO NOT WRAP IN EXTRA CODE BLOCKS OR CHAT COMMENTARY.
"""
    return prompt

def run_llm_normalization(prompt: str, model: str = DEFAULT_MODEL) -> str:
    cmd = ["llm", "-m", model]
    res = subprocess.run(cmd, input=prompt, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"LLM execution failed: {res.stderr.strip()}")
    output = res.stdout.strip()
    m = re.match(r"^```(?:markdown|yaml)?\n(.*?)\n```$", output, re.DOTALL)
    if m:
        output = m.group(1).strip()
    return output

def verify_fidelity(raw_text: str, normalized_text: str, doc_date: str) -> tuple[bool, list[str]]:
    issues = []
    fm, body = extract_frontmatter_and_body(normalized_text)
    if not fm:
        issues.append("YAML frontmatter missing or failed to parse.")
        return False, issues
        
    required_keys = ["layout", "title", "date", "nav_order", "parent", "grand_parent", "type", "status", "presiding", "secretary", "quorum"]
    for k in required_keys:
        if k not in fm:
            issues.append(f"Missing required frontmatter key: '{k}'")
            
    if str(fm.get("date")) != doc_date:
        issues.append(f"Frontmatter date '{fm.get('date')}' does not match target date '{doc_date}'")
        
    attendees = fm.get("attendees", [])
    if not isinstance(attendees, list) or len(attendees) == 0:
        issues.append("Frontmatter 'attendees' list is empty or invalid.")
    else:
        invalid_name_patterns = [
            r"agenda", r"minutes", r"unfinished", r"new business", r"standing items",
            r"report", r"discussion", r"announcement", r"memoriam", r"consensus"
        ]
        for att in attendees:
            if not isinstance(att, dict) or "name" not in att:
                issues.append(f"Malformed attendee entry: {att}")
                continue
            name = str(att["name"]).strip()
            for pat in invalid_name_patterns:
                if re.search(r"\b" + pat + r"\b", name, re.IGNORECASE):
                    issues.append(f"Suspicious attendee name detected in frontmatter: '{name}'")
                    
    currency_patterns = re.findall(r"\$[\d,]+(?:\.\d+)?(?:\s*[kKmMbB]|(?:\s*thousand|\s*million))?", raw_text)
    norm_no_commas = re.sub(r",(?=\d{3})", "", normalized_text)
    for curr in set(currency_patterns):
        curr_clean = curr.strip()
        num_part = re.sub(r"[^\d]", "", curr_clean)
        if num_part and len(num_part) >= 2:
            if num_part not in norm_no_commas and curr_clean.lower() not in normalized_text.lower():
                issues.append(f"Monetary figure '{curr_clean}' from raw text not found in normalized text.")

    raw_has_motions = bool(re.search(r"\b(motion|moved|seconded|second|ayes|unanimously|consensus)\b", raw_text, re.IGNORECASE))
    norm_has_motions = bool(re.search(r"\b(motion|moved|seconded|second|ayes|unanimously|consensus|approved)\b", normalized_text, re.IGNORECASE))
    if raw_has_motions and not norm_has_motions:
        issues.append("Raw text contained motions/votes but normalized text has none.")

    raw_word_count = len(raw_text.split())
    norm_word_count = len(normalized_text.split())
    if raw_word_count > 100:
        ratio = norm_word_count / raw_word_count
        if ratio < 0.40:
            issues.append(f"Normalized text appears truncated: word count dropped from {raw_word_count} to {norm_word_count} (ratio: {ratio:.2f})")
        elif ratio > 3.0:
            issues.append(f"Normalized text appears unnaturally expanded: word count increased from {raw_word_count} to {norm_word_count} (ratio: {ratio:.2f})")

    return len(issues) == 0, issues

def normalize_minute_content(raw_text: str, doc_date: str, doc_type: str = "board", status: str = "draft", model: str = DEFAULT_MODEL, repo_root: Path = None) -> tuple[str, list[str]]:
    cleaned_raw = pre_clean_text(raw_text)
    prompt = build_normalization_prompt(cleaned_raw, doc_date, doc_type=doc_type, status=status, repo_root=repo_root)
    normalized = run_llm_normalization(prompt, model=model)
    is_valid, issues = verify_fidelity(cleaned_raw, normalized, doc_date)
    return normalized, issues

def normalize_file(file_path: Path, model: str = DEFAULT_MODEL, dry_run: bool = False, force: bool = False, repo_root: Path = None) -> bool:
    if repo_root is None:
        repo_root = find_repo_root()
    if not file_path.is_absolute():
        file_path = repo_root / file_path
    if not file_path.exists():
        print(f"❌ File does not exist: {file_path}")
        return False
        
    content = file_path.read_text()
    fm, body = extract_frontmatter_and_body(content)
    doc_date = fm.get("date")
    if not doc_date:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", file_path.name)
        doc_date = m.group(1) if m else None
    if not doc_date:
        print(f"❌ Could not infer date for file: {file_path}")
        return False
        
    doc_type = fm.get("type", "board")
    status = fm.get("status", "draft")
    
    print(f"✨ Normalizing {file_path.name} ({doc_date}, model: {model})...")
    normalized, issues = normalize_minute_content(body if body else content, str(doc_date), doc_type=doc_type, status=status, model=model, repo_root=repo_root)
    
    if issues:
        print(f"  ⚠️ Fidelity / Verification warnings for {file_path.name}:")
        for iss in issues:
            print(f"     - {iss}")
            
    if dry_run:
        print(f"  [dry-run] Would write normalized content to {file_path}")
        print("\n--- PREVIEW ---")
        print("\n".join(normalized.split("\n")[:35]))
        print("...\n--- END PREVIEW ---\n")
        return True
        
    file_path.write_text(normalized + "\n")
    print(f"  ✅ Successfully normalized and saved: {file_path}")
    return True

def score_candidate_doc(c):
    path = c["remote_path"].lower()
    score = 0
    if ("minute" in path or "minutes" in path) and "agenda" not in path:
        score += 100
    elif "agenda" in path:
        score -= 50
    if c["is_approved"]:
        score += 40
    if c["is_docx"]:
        score += 20
    if "superseded" in path:
        score -= 40
    return score

def classify_meeting_doc(path: str) -> tuple[str, str]:
    path_lower = path.lower()
    if any(k in path_lower for k in ["pnp", "p_p", "policies and procedures", "policies"]):
        return "committees", "policies-and-procedures"
    if any(k in path_lower for k in ["dev comm", "development", "devo"]):
        return "committees", "development"
    if any(k in path_lower for k in ["personnel", "personel"]):
        return "committees", "personnel"
    if any(k in path_lower for k in ["lrpc", "long range"]):
        return "committees", "long-range-planning"
    if any(k in path_lower for k in ["cac", "community affairs"]):
        return "committees", "community-affairs"
    if any(k in path_lower for k in ["audit"]):
        return "committees", "audit"
    if any(k in path_lower for k in ["budget", "finance", "bfc"]):
        return "committees", "budget-and-finance"
    if any(k in path_lower for k in ["executive committee", "excom", "x-com", "xcom"]):
        return "committees", "executive-committee"
    if any(k in path_lower for k in ["gpm", "membership", "members", "agm", "annual", "general public"]):
        return "membership", None
    return "board", None

def process_year(year, dry_run=False, force=False, normalize=True, model=DEFAULT_MODEL, repo_root=None):
    if repo_root is None:
        repo_root = find_repo_root()
        
    raw_cache_dir = repo_root / "_raw"
    raw_md_dir = repo_root / "_raw_md"
    
    print(f"\n================ Processing {year} ================")
    files = list_drive_files(year)
    valid_files = [f for f in files if is_valid_minute_doc(f)]
    print(f"Found {len(valid_files)} valid minute document(s) in Drive for {year}.")
    
    meetings = {}
    for remote_path in valid_files:
        dt = extract_date_from_filename_or_path(remote_path)
        cache_file = raw_cache_dir / str(year) / Path(remote_path).name
        if not cache_file.exists():
            try:
                download_file(remote_path, cache_file)
            except Exception as e:
                print(f"  ⚠️ Could not download {remote_path}: {e}")
                
        if cache_file.exists():
            try:
                txt = convert_to_md_text(cache_file)
                text_dt = extract_date_from_text(txt, fallback_year=year)
                if text_dt:
                    dt = text_dt
            except Exception:
                pass
            
        if not dt:
            print(f"  ⚠️ Could not determine meeting date for: {remote_path}")
            continue
            
        doc_type, committee_slug = classify_meeting_doc(remote_path)
        is_approved = "approved" in remote_path.lower() or "final" in remote_path.lower()
        is_docx = remote_path.lower().endswith(".docx") or remote_path.lower().endswith(".doc")
        status = "approved" if is_approved else "draft"
        
        key = (dt, doc_type, committee_slug)
        if key not in meetings:
            meetings[key] = []
        meetings[key].append({
            "remote_path": remote_path,
            "status": status,
            "is_approved": is_approved,
            "is_docx": is_docx
        })

    ensure_year_index(year, "board", dry_run=dry_run, repo_root=repo_root)
    
    for (dt, doc_type, committee_slug), candidates in sorted(meetings.items()):
        candidates.sort(key=score_candidate_doc, reverse=True)
        chosen = candidates[0]
        remote_path = chosen["remote_path"]
        status = chosen["status"]
        
        if doc_type == "committees" and committee_slug:
            dest_dir = repo_root / "committees" / committee_slug / str(year)
        else:
            dest_dir = repo_root / doc_type / str(year)
            
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / f"{dt}.md"
        
        if dest_file.exists() and not force:
            print(f"  ⏩ Skipping existing: {dest_file.relative_to(repo_root)}")
            continue
            
        print(f"  📥 Processing: {dt} ({doc_type}{f'/{committee_slug}' if committee_slug else ''}, {status}) <- {remote_path}")
        if dry_run:
            continue
            
        cache_file = raw_cache_dir / str(year) / Path(remote_path).name
        if not cache_file.exists():
            download_file(remote_path, cache_file)
            
        raw_md = convert_to_md_text(cache_file)
        
        if doc_type == "committees" and committee_slug:
            year_raw_md_dir = raw_md_dir / "committees" / committee_slug / str(year)
        else:
            year_raw_md_dir = raw_md_dir / doc_type / str(year)
            
        year_raw_md_dir.mkdir(parents=True, exist_ok=True)
        (year_raw_md_dir / f"{dt}.raw.md").write_text(raw_md)
        
        if normalize:
            print(f"  ✨ Running AI normalization ({model})...")
            formatted_md, issues = normalize_minute_content(raw_md, dt, doc_type=doc_type, status=status, model=model, repo_root=repo_root)
            if issues:
                print(f"  ⚠️ Verification warnings for {dt}:")
                for iss in issues:
                    print(f"     - {iss}")
        else:
            formatted_md = raw_md
            
        dest_file.write_text(formatted_md)
        print(f"  ✅ Written: {dest_file.relative_to(repo_root)}")

def run_verify(year=None, file_path=None, repo_root=None):
    if repo_root is None:
        repo_root = find_repo_root()
        
    files_to_check = []
    if file_path:
        p = Path(file_path)
        if not p.is_absolute():
            p = repo_root / p
        if p.exists():
            files_to_check.append(p)
    elif year:
        year_dir = repo_root / "board" / str(year)
        if year_dir.exists():
            files_to_check.extend(sorted([f for f in year_dir.glob("*.md") if f.name != "index.md"]))
    else:
        for year_dir in sorted((repo_root / "board").glob("20*")):
            if year_dir.is_dir():
                files_to_check.extend(sorted([f for f in year_dir.glob("*.md") if f.name != "index.md"]))
                
    if not files_to_check:
        return
        
    print(f"\n🔍 Verifying {len(files_to_check)} document(s)...")
    total_issues = 0
    for f in files_to_check:
        content = f.read_text()
        fm, body = extract_frontmatter_and_body(content)
        dt = str(fm.get("date", ""))
        raw_f = repo_root / "_raw_md" / fm.get("type", "board") / dt[:4] / f"{dt}.raw.md"
        source_text = raw_f.read_text() if raw_f.exists() else body
        
        is_valid, issues = verify_fidelity(source_text, content, dt)
        if not is_valid:
            total_issues += len(issues)
            print(f"❌ {f.relative_to(repo_root)}:")
            for iss in issues:
                print(f"   - {iss}")
        else:
            presiding = fm.get("presiding", "N/A")
            secretary = fm.get("secretary", "N/A")
            attendees = len(fm.get("attendees", []))
            print(f"✅ {f.relative_to(repo_root)} (Date: {dt}, Presiding: {presiding}, Sec: {secretary}, Attendees: {attendees})")
            
    if total_issues == 0:
        print(f"🎉 Verification passed for {len(files_to_check)} file(s)!")
    else:
        print(f"⚠️ Verification completed with {total_issues} issue(s).")

def main():
    parser = argparse.ArgumentParser(
        prog="minutebook",
        description="SF Pride Digital Minutebook — Unified Ingestion, Normalization & Verification Pipeline"
    )
    parser.add_argument("--year", type=int, help="Target meeting year (e.g. 2024)")
    parser.add_argument("--file", type=str, help="Target local Markdown file")
    parser.add_argument("--dry-run", action="store_true", help="Preview actions without writing files")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    parser.add_argument("--no-normalize", action="store_true", help="Skip AI normalization")
    parser.add_argument("--verify-only", action="store_true", help="Run verification without importing/normalizing")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help=f"LLM model (default: {DEFAULT_MODEL})")

    args = parser.parse_args()
    repo_root = find_repo_root()

    if args.verify_only:
        run_verify(year=args.year, file_path=args.file, repo_root=repo_root)
    elif args.file:
        p = Path(args.file)
        if not p.is_absolute():
            p = repo_root / p
        normalize_file(p, model=args.model, dry_run=args.dry_run, force=args.force, repo_root=repo_root)
        run_verify(file_path=p, repo_root=repo_root)
    else:
        years = [args.year] if args.year else range(2013, 2027)
        for yr in years:
            process_year(yr, dry_run=args.dry_run, force=args.force, normalize=not args.no_normalize, model=args.model, repo_root=repo_root)
            if not args.dry_run:
                run_verify(year=yr, repo_root=repo_root)

if __name__ == "__main__":
    main()

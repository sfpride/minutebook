#!/usr/bin/env python3
"""
import_minutes.py

Safely and read-only imports meeting minutes from the SF Pride Board Google Shared Drive,
converts docx files to Markdown via pandoc, extracts structured metadata/frontmatter,
and writes Jekyll pages for the sfpride/minutebook site.
"""

import os
import re
import sys
import json
import shutil
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

TEAM_DRIVE_ID = "0AO8MJQcSxn5CUk9PVA"
REMOTE_NAME = "cdn-gd"
REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_CACHE_DIR = REPO_ROOT / "_raw"

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
    """List all minute files from General/Meetings [year]"""
    pattern = f"Meetings {year}/**" if year else "Meetings*/**"
    output = run_rclone(["lsf", "-R", f"{REMOTE_NAME}:General", "--include", pattern])
    lines = [l.strip() for l in output.split("\n") if l.strip() and not l.endswith("/")]
    return lines

def is_valid_minute_doc(path):
    path_lower = path.lower()
    
    # Must be docx or doc
    if not (path_lower.endswith(".docx") or path_lower.endswith(".doc")):
        return False
        
    # Skip Closed Session / Confidential documents per policy
    if any(kw in path_lower for kw in ["closed session", "closed-session", "closed_session", "executive session"]):
        return False
        
    # Skip obvious non-minutes
    if "agenda" in path_lower or "report" in path_lower or "packet" in path_lower:
        if "minute" not in path_lower:
            return False

    if "minute" not in path_lower and "minutes" not in path_lower:
        return False

    return True

def extract_date_from_filename_or_path(path):
    # Match YYYYMMDD or YYYY-MM-DD or MM-DD-YYYY or YYYY.MM.DD
    m = re.search(r"(20\d{2})[-_.]?([01]\d)[-_.]?([0-3]\d)", path)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None

def download_file(remote_path, local_dest):
    local_dest.parent.mkdir(parents=True, exist_ok=True)
    full_remote = f"{REMOTE_NAME}:General/{remote_path}"
    run_rclone(["copyto", full_remote, str(local_dest)])

def convert_docx_to_md(docx_path):
    cmd = ["pandoc", str(docx_path), "-t", "markdown", "--wrap=none"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Pandoc conversion failed for {docx_path}: {res.stderr}")
    return res.stdout

def parse_metadata_and_clean_md(raw_md, doc_date, doc_type="board", status="draft"):
    """
    Extracts structured frontmatter fields (presiding, secretary, attendees, times, etc.)
    and cleans up pandoc markdown formatting.
    """
    lines = raw_md.split("\n")
    
    # Presiding & Call to order
    presiding = None
    called_to_order = None
    adjourned = None
    secretary = None
    location = "Zoom"
    quorum = True
    attendees = []
    
    date_obj = datetime.strptime(doc_date, "%Y-%m-%d")
    date_formatted = date_obj.strftime("%B %-d, %Y")
    
    # Find call to order
    for line in lines:
        if "order at" in line.lower() or "called to order" in line.lower():
            time_m = re.search(r"(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.))", line, re.IGNORECASE)
            if time_m:
                called_to_order = time_m.group(1).upper().replace(".", "")
            
            pres_m = re.search(r"(?:President(?:\s+of\s+the\s+Board)?|Chair)\s+([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+)+)", line)
            if pres_m:
                presiding = pres_m.group(1)
                
        if "adjourn" in line.lower():
            time_m = re.search(r"(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.))", line, re.IGNORECASE)
            if time_m:
                adjourned = time_m.group(1).upper().replace(".", "")

        if "secretary" in line.lower():
            sec_m = re.search(r"Secretary\s+([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+)+)", line)
            if sec_m and not secretary:
                secretary = sec_m.group(1)

    # Parse attendees block if numbered or bulleted list
    # e.g. "1. Carolyn Wysinger, President"
    in_attendees = False
    for line in lines:
        if any(h in line.lower() for h in ["in attendance were:", "attendance:", "present:"]):
            in_attendees = True
            continue
        if in_attendees:
            if not line.strip() or line.startswith("Quorum") or line.startswith("Apologies") or line.startswith("##"):
                if line.startswith("Quorum") or line.startswith("##") or line.startswith("---"):
                    in_attendees = False
            m_att = re.match(r"^\s*(?:\d+\.|\*|-)\s+([A-Za-z0-9\s'\-\.\(\)]+)(?:,\s*([A-Za-z0-9\s'\-\.\(\)\/]+))?$", line)
            if m_att and in_attendees:
                name = m_att.group(1).strip()
                role = m_att.group(2).strip() if m_att.group(2) else "Director"
                attendees.append({"name": name, "role": role, "present": True})

    # Absences
    for line in lines:
        if "apologies were sent" in line.lower() or "absent:" in line.lower() or "was absent" in line.lower():
            abs_matches = re.findall(r"Director(?:s)?\s+([A-Za-z'\-]+)", line)
            for ab in abs_matches:
                attendees.append({"name": f"[Director {ab}]", "role": "Director", "present": False})

    # Build Frontmatter
    parent_title = f"Board Meetings {date_obj.strftime('%Y')}" if doc_type == "board" else f"Membership Meetings {date_obj.strftime('%Y')}"
    grand_parent = "Board Meetings" if doc_type == "board" else "Membership Meetings"
    meeting_title = f"Board Meeting - {date_formatted}" if doc_type == "board" else f"Membership Meeting - {date_formatted}"
    
    frontmatter = {
        "layout": "default",
        "title": meeting_title,
        "date": doc_date,
        "nav_order": int(doc_date.replace("-", "")),
        "parent": parent_title,
        "grand_parent": grand_parent,
        "type": doc_type,
        "status": status,
        "presiding": presiding or "TBD",
        "secretary": secretary or "TBD",
        "quorum": quorum,
        "attendees": attendees,
        "location": location,
        "called_to_order": called_to_order or "",
        "adjourned": adjourned or ""
    }
    
    # Clean markdown body
    # Remove leading Pandoc title if "MINUTES" or "Meeting Minutes"
    body = raw_md
    body = re.sub(r"^MINUTES\s*\n+", "", body, flags=re.IGNORECASE)
    body = re.sub(r"^\*\*MINUTES\*\*\s*\n+", "", body, flags=re.IGNORECASE)
    body = re.sub(r"\^th\^", "th", body)
    body = re.sub(r"\^st\^", "st", body)
    body = re.sub(r"\^nd\^", "nd", body)
    body = re.sub(r"\^rd\^", "rd", body)

    # Format YAML frontmatter manually for clean layout
    fm_lines = ["---", "layout: default", f"title: {frontmatter['title']}", f"date: {frontmatter['date']}", f"nav_order: {frontmatter['nav_order']}", f"parent: {frontmatter['parent']}", f"grand_parent: {frontmatter['grand_parent']}", "", f"type: {frontmatter['type']}", f"status: {frontmatter['status']}", f"presiding: {frontmatter['presiding']}", f"secretary: {frontmatter['secretary']}", f"quorum: {str(frontmatter['quorum']).lower()}"]
    
    if frontmatter['attendees']:
        fm_lines.append("")
        fm_lines.append("attendees:")
        for att in frontmatter['attendees']:
            fm_lines.append(f"  - name: {att['name']}")
            fm_lines.append(f"    role: {att['role']}")
            fm_lines.append(f"    present: {str(att['present']).lower()}")
            
    fm_lines.append("")
    fm_lines.append(f"location: {frontmatter['location']}")
    if frontmatter['called_to_order']:
        fm_lines.append(f"called_to_order: \"{frontmatter['called_to_order']}\"")
    if frontmatter['adjourned']:
        fm_lines.append(f"adjourned: \"{frontmatter['adjourned']}\"")
    fm_lines.append("---")
    fm_lines.append("")
    fm_lines.append(f"# {meeting_title.replace(' - ', ' — ')}")
    fm_lines.append("")
    
    final_content = "\n".join(fm_lines) + body.strip() + "\n"
    return final_content

def ensure_year_index(year, doc_type="board"):
    if doc_type == "board":
        year_dir = REPO_ROOT / "board" / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)
        index_file = year_dir / "index.md"
        if not index_file.exists():
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
            print(f"  Created year index: {index_file.relative_to(REPO_ROOT)}")

def process_year(year, dry_run=False, force=False):
    print(f"\n================ Processing {year} ================")
    files = list_drive_files(year)
    valid_files = [f for f in files if is_valid_minute_doc(f)]
    print(f"Found {len(valid_files)} valid minute document(s) in Drive for {year}.")
    
    # Group by (date, type)
    meetings = {}
    for remote_path in valid_files:
        dt = extract_date_from_filename_or_path(remote_path)
        if not dt:
            print(f"  ⚠️ Could not parse date from: {remote_path}")
            continue
            
        doc_type = "membership" if "membership" in remote_path.lower() or "agm" in remote_path.lower() else "board"
        is_approved = "approved" in remote_path.lower() or "final" in remote_path.lower()
        status = "approved" if is_approved else "draft"
        
        key = (dt, doc_type)
        if key not in meetings:
            meetings[key] = []
        meetings[key].append({
            "remote_path": remote_path,
            "status": status,
            "is_approved": is_approved
        })

    ensure_year_index(year, "board")
    
    for (dt, doc_type), candidates in sorted(meetings.items()):
        # Prioritize approved version over draft
        candidates.sort(key=lambda x: (1 if x["is_approved"] else 0), reverse=True)
        chosen = candidates[0]
        remote_path = chosen["remote_path"]
        status = chosen["status"]
        
        dest_dir = REPO_ROOT / doc_type / str(year)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / f"{dt}.md"
        
        if dest_file.exists() and not force:
            print(f"  ⏩ Skipping existing: {dest_file.relative_to(REPO_ROOT)}")
            continue
            
        print(f"  📥 Processing: {dt} ({doc_type}, {status}) <- {remote_path}")
        if dry_run:
            continue
            
        # Download docx to cache
        cache_docx = RAW_CACHE_DIR / str(year) / Path(remote_path).name
        download_file(remote_path, cache_docx)
        
        # Convert to Markdown
        raw_md = convert_docx_to_md(cache_docx)
        
        # Parse metadata & inject frontmatter
        formatted_md = parse_metadata_and_clean_md(raw_md, dt, doc_type=doc_type, status=status)
        
        # Write final markdown
        dest_file.write_text(formatted_md)
        print(f"  ✅ Written: {dest_file.relative_to(REPO_ROOT)}")

def main():
    parser = argparse.ArgumentParser(description="Import minutes from SF Pride Drive to Minutebook.")
    parser.add_argument("--year", type=int, help="Specific year to import (e.g. 2022)")
    parser.add_argument("--dry-run", action="store_true", help="List actions without writing files")
    parser.add_argument("--force", action="store_true", help="Overwrite existing markdown files")
    args = parser.parse_args()
    
    if args.year:
        process_year(args.year, dry_run=args.dry_run, force=args.force)
    else:
        # Process from 2013 to 2026
        for yr in range(2013, 2027):
            process_year(yr, dry_run=args.dry_run, force=args.force)

if __name__ == "__main__":
    main()

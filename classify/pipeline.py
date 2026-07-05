 
import json
from collections import Counter
from pathlib import Path
from typing import Optional
 
from config import CATEGORIES
from ollama_client import classify_via_llm
from utils import clean_table_data, extract_year, is_quality_table, keyword_candidates 

def run_pipeline(
    extractions: list[dict],
    model: str,
    dry_run: bool = False,
    resume_set: Optional[set] = None,
) -> list[dict]:
    """
    Iterate over every document → page → table.
    Classify each candidate and return a flat list of result dicts.
    """
    results = []
    resume_set = resume_set or set()

    # Count totals for progress display
    all_tables = [
        (doc, page, tbl)
        for doc  in extractions  if "pages" in doc
        for page in doc["pages"]
        for tbl  in page["tables"]
    ]
    quality_tables = [(d, p, t) for d, p, t in all_tables if is_quality_table(t)]
    candidate_tables = [
        (d, p, t, kws)
        for d, p, t in quality_tables
        for kws in [keyword_candidates(p["text"], t)]
        if kws                                              # skip if no keyword match
    ]

    total = len(candidate_tables)
    print(f"\n  Pipeline summary")
    print(f"    Total tables     : {len(all_tables)}")
    print(f"    After quality filter : {len(quality_tables)}")
    print(f"    After keyword filter : {total}  ← LLM calls needed")
    if dry_run:
        print("    Mode: DRY-RUN (keyword labels only, no LLM)\n")
    else:
        print(f"    Model: {model}\n")

    for idx, (doc, page, tbl, candidates) in enumerate(candidate_tables, 1):
        uid = f"{doc['filename']}::p{page['page_number']}::t{tbl['table_index']}"

        # Resume support
        if uid in resume_set:
            continue

        # Progress bar (simple)
        pct = idx / total * 100
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"\r  [{bar}] {idx}/{total} ({pct:.0f}%)  {doc['filename'][-30:]}", end="", flush=True)

        if dry_run:
            # Use first keyword candidate as label
            category   = candidates[0]
            title      = ""
            confidence = "keyword"
        else:
            llm_result = classify_via_llm(page["text"], tbl, candidates, model)
            category   = llm_result["category"]
            title      = llm_result["title"]
            confidence = llm_result["confidence"]

        if category == "other":
            continue                    # skip unclassified tables

        results.append({
            "uid":        uid,
            "file":       doc["filename"],
            "year":       _extract_year(doc["filename"]),
            "page":       page["page_number"],
            "table_index": tbl["table_index"],
            "category":   category,
            "title":      title,
            "confidence": confidence,
            "rows":       tbl["rows"],
            "cols":       tbl["cols"],
            "data":       clean_table_data(tbl["data"]),
        })

    print()   # newline after progress bar
    return results

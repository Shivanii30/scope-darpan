
import argparse
import json
import time
from pathlib import Path
 
from config import DEFAULT_MODEL
from ollama_client import check_ollama
from pipeline import print_summary, run_pipeline, save_results
 
 
def main():
    parser = argparse.ArgumentParser(
        description="Classify Ombudsman PDF tables using local Qwen2.5:3b via Ollama"
    )
    parser.add_argument("--input",   default="extractions.json",
                        help="Path to extractions.json from extract_tables.py")
    parser.add_argument("--output",  default="output",
                        help="Directory to save results (default: ./output)")
    parser.add_argument("--model",   default=DEFAULT_MODEL,
                        help="Ollama model name (default: qwen2.5:3b)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip LLM calls; use keyword labels only (fast)")
    parser.add_argument("--resume",  action="store_true",
                        help="Resume from classified_tables.json if it exists")
    args = parser.parse_args()
 
    # ── Load extractions ───────────────────────────────────────────────────
    print(f"📂  Loading {args.input} …")
    with open(args.input, encoding="utf-8") as f:
        extractions = json.load(f)
    print(f"    {len(extractions)} documents loaded")
 
    # ── Resume support ─────────────────────────────────────────────────────
    resume_set: set = set()
    existing_results: list[dict] = []
    combined_path = Path(args.output) / "classified_tables.json"
 
    if args.resume and combined_path.exists():
        with open(combined_path, encoding="utf-8") as f:
            existing_results = json.load(f)
        resume_set = {r["uid"] for r in existing_results}
        print(f"♻️   Resuming — {len(existing_results)} tables already classified")
 
    # ── Check Ollama (unless dry-run) ──────────────────────────────────────
    if not args.dry_run:
        if not check_ollama(args.model):
            print("\n💡  To test without Ollama, use:  python classify_tables.py --dry-run")
            return
 
    # ── Run pipeline ───────────────────────────────────────────────────────
    t0 = time.time()
    new_results = run_pipeline(
        extractions,
        model      = args.model,
        dry_run    = args.dry_run,
        resume_set = resume_set,
    )
    all_results = existing_results + new_results
 
    elapsed = time.time() - t0
    print(f"\n⏱️   Done in {elapsed:.0f}s  ({len(new_results)} new tables classified)")
 
    # ── Save ───────────────────────────────────────────────────────────────
    save_results(all_results, args.output)
    print_summary(all_results)
 
 
if __name__ == "__main__":
    main()

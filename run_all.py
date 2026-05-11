#!/usr/bin/env python3
"""
Orchestrator — runs all four pipeline steps in sequence.

Each step is invoked as a subprocess so it can be run independently and
so a crash in one step does not leave the Python process in a bad state.

Usage
-----
  python run_all.py              # run all steps
  python run_all.py --start 2    # start from step 2 (skips step 1)
  python run_all.py --only 3     # run only step 3
"""

import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path

LOG_FILE = Path(__file__).parent / "logs" / "pipeline.log"
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

STEPS = [
    (1, "01_download_audio.py",       "Download audio files"),
    (2, "02_get_transcripts.py",      "Obtain transcripts"),
    (3, "03_generate_descriptions.py","Generate SEO descriptions"),
    (4, "04_write_google_doc.py",     "Write to Google Doc"),
]


def run_step(script: str, label: str) -> bool:
    script_path = Path(__file__).parent / script
    logger.info("=" * 60)
    logger.info("RUNNING: %s — %s", script, label)
    logger.info("=" * 60)
    start = time.time()
    result = subprocess.run([sys.executable, str(script_path)])
    elapsed = time.time() - start
    if result.returncode == 0:
        logger.info("COMPLETED %s in %.1fs", script, elapsed)
        return True
    else:
        logger.error("FAILED %s (exit code %d) after %.1fs", script, result.returncode, elapsed)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the YouTube playlist pipeline.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--start", type=int, metavar="N",
                       help="Start from step N (e.g. --start 2 skips step 1)")
    group.add_argument("--only",  type=int, metavar="N",
                       help="Run only step N")
    args = parser.parse_args()

    if args.only:
        steps_to_run = [(n, s, l) for n, s, l in STEPS if n == args.only]
    elif args.start:
        steps_to_run = [(n, s, l) for n, s, l in STEPS if n >= args.start]
    else:
        steps_to_run = STEPS

    if not steps_to_run:
        logger.error("No matching steps found.")
        sys.exit(1)

    overall_start = time.time()
    failed: list[str] = []

    for step_num, script, label in steps_to_run:
        success = run_step(script, label)
        if not success:
            failed.append(f"Step {step_num}: {label}")
            logger.warning(
                "Step %d failed — continuing with remaining steps (pipeline is resumable).",
                step_num,
            )

    total = time.time() - overall_start
    logger.info("=" * 60)
    logger.info("Pipeline finished in %.1fs", total)
    if failed:
        logger.warning("The following steps reported failures:")
        for f in failed:
            logger.warning("  • %s", f)
        logger.info("Fix the errors and re-run — completed work will be skipped.")
        sys.exit(1)
    else:
        logger.info("All steps completed successfully.")


if __name__ == "__main__":
    main()

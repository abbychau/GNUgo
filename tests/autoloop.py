#!/usr/bin/env python3
"""One-shot automated improvement loop for GNU Go.

Rebuilds the Release binary, runs the key regression suites, stores
results to a timestamped log, and (optionally) updates the baseline.

Usage:
    python autoloop.py                       # rebuild + full suite + log
    python autoloop.py --update-baseline     # also refresh baseline.json
    python autoloop.py --skip-build          # don't rebuild (use current exe)
    python autoloop.py --suite reading.tst   # run a custom suite list
"""

import datetime
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
EXE = os.path.join(ROOT, "build", "src", "interface", "Release", "gnugo.exe")

DEFAULT_SUITES = ["tiny.tst", "tactics.tst", "reading.tst", "atari_atari.tst",
                  "owl.tst", "connect.tst", "semeai.tst", "endgame.tst",
                  "capture.tst"]


def log(msg, fh=None):
    print(msg)
    if fh:
        fh.write(msg + "\n")
        fh.flush()


def main():
    args = sys.argv[1:]
    update_baseline = "--update-baseline" in args
    skip_build = "--skip-build" in args
    suites = [a for a in args if not a.startswith("--")]
    if not suites:
        suites = DEFAULT_SUITES

    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    logfile = os.path.join(TESTS, f"autoloop-{ts}.log")
    fh = open(logfile, "w", encoding="utf-8")
    log(f"=== GNU Go autoloop {ts} ===", fh)
    log(f"exe: {EXE}", fh)
    log(f"suites: {', '.join(suites)}", fh)

    if not skip_build:
        log("\n>> cmake --build (Release)...", fh)
        r = subprocess.run(["cmake", "--build", os.path.join(ROOT, "build"),
                            "--config", "Release", "--parallel"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            log(f"BUILD FAILED:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}", fh)
            fh.close()
            return 1
        log("build OK", fh)

    if not os.path.exists(EXE):
        log(f"ERROR: exe not found: {EXE}", fh)
        fh.close()
        return 1

    # Run the verify script (it builds the baseline and diffs).
    cmd = [sys.executable, os.path.join(TESTS, "verify_gnugo.py"), EXE] + suites
    if update_baseline:
        cmd.append("--update-baseline")
    log("\n>> verify + regression...", fh)
    r = subprocess.run(cmd, capture_output=True, text=True)
    log(r.stdout, fh)
    if r.stderr.strip():
        log("STDERR:\n" + r.stderr, fh)
    log(f"\nlog written: {logfile}", fh)
    fh.close()
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
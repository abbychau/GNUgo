#!/usr/bin/env python3
"""Automated GNU Go improvement loop: rebuild + regression + compare.

Usage:
    python verify_gnugo.py <exe> [suite1.tst suite2.tst ...]

Rebuilds nothing itself (call cmake first), runs the given suites via
run_tests.py, and compares pass/known-fail/unexpected-pass counts
against the stored BASELINE. Prints a verdict for each suite and an
overall summary, exiting non-zero if any REAL regression occurred
(pass decreased, or a known-fail became a hard fail).

The baseline file (baseline.json) stores expected counts per suite.
Use --update-baseline to write current results as the new baseline.
"""

import json
import os
import subprocess
import sys

BASELINE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "baseline.json")
KEY_SUITES = ["tiny.tst", "tactics.tst", "reading.tst", "atari_atari.tst",
              "owl.tst", "connect.tst", "semeai.tst", "endgame.tst",
              "capture.tst", "13x13.tst"]


def run_suite(exe, suite, engine_opts):
    """Run one suite; return dict(pass, fail, known_fail, unexpected_pass) or None on crash."""
    cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "run_tests.py"), exe]
    if engine_opts:
        cmd += ["-e", engine_opts]
    cmd.append(suite)
    out = subprocess.run(cmd, capture_output=True, text=True,
                         cwd=os.path.dirname(os.path.abspath(__file__)))
    txt = out.stdout + out.stderr
    line = next((l for l in txt.splitlines()
                 if l.strip().startswith("TOTAL:")), None)
    if line is None:
        return None
    # TOTAL: pass 236 fail 0 known-fail 25 unexpected-pass 0 ignore 0  (90.4%)
    parts = {}
    toks = line.split()
    for i, t in enumerate(toks):
        if t in ("pass", "fail", "known-fail", "unexpected-pass", "ignore"):
            parts[t.replace("-", "_")] = int(toks[i + 1])
    return parts


def load_baseline():
    if os.path.exists(BASELINE_FILE):
        with open(BASELINE_FILE) as fh:
            return json.load(fh)
    return {}


def save_baseline(data):
    with open(BASELINE_FILE, "w") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    args = sys.argv[1:]
    update = "--update-baseline" in args
    engine_opts = None
    if "-e" in args:
        i = args.index("-e")
        engine_opts = args[i + 1]
        del args[i:i + 2]
    if "--update-baseline" in args:
        args.remove("--update-baseline")
    exe = args[0]
    if not os.path.exists(exe):
        print(f"error: engine not found: {exe}", file=sys.stderr)
        return 2

    suites = args[1:] or KEY_SUITES
    baseline = load_baseline()
    regressions = []
    improvements = []
    results = {}
    for suite in suites:
        if not os.path.exists(os.path.join(
                os.path.dirname(os.path.abspath(__file__)), suite)):
            print(f"  {suite}: MISSING, skipping")
            continue
        res = run_suite(exe, suite, engine_opts)
        if res is None:
            print(f"  {suite}: CRASH (engine died or no TOTAL)")
            regressions.append(f"{suite}: crash")
            continue
        results[suite] = res
        old = baseline.get(suite)
        if update or old is None:
            print(f"  {suite}: pass {res['pass']} / kf {res['known_fail']} "
                  f"/ up {res['unexpected_pass']}  (baseline set)")
            continue
        delta_pass = res["pass"] - old["pass"]
        delta_kf = res["known_fail"] - old["known_fail"]
        delta_up = res["unexpected_pass"] - old["unexpected_pass"]
        flag = "="
        if delta_pass < 0 or delta_kf > 0:
            flag = "REGRESS"
            regressions.append(f"{suite}: pass {delta_pass:+d}, kf {delta_kf:+d}")
        elif delta_pass > 0 or delta_up > 0 or delta_kf < 0:
            flag = "IMPROVE"
            improvements.append(f"{suite}: pass {delta_pass:+d}, "
                                f"kf {delta_kf:+d}, up {delta_up:+d}")
        print(f"  {suite}: pass {res['pass']} / kf {res['known_fail']} "
              f"/ up {res['unexpected_pass']}  "
              f"({flag} vs baseline: pass {delta_pass:+d}, "
              f"kf {delta_kf:+d}, up {delta_up:+d})")

    if update:
        merged = dict(baseline)
        merged.update(results)
        save_baseline(merged)
        print("\nBaseline updated.")

    print("\n=== SUMMARY ===")
    print("Improvements:", "; ".join(improvements) if improvements else "none")
    print("Regressions:", "; ".join(regressions) if regressions else "none")
    return 1 if regressions else 0


if __name__ == "__main__":
    sys.exit(main())
#!/usr/bin/env python3
"""GTP regression runner for GNU Go (.tst suites).

Drives GNU Go over the GTP protocol and checks each test's expected
result. Needs only Python 3 (no perl, awk or pike).

Test file format (see the Texinfo manual, "Regression"):
    <id> <gtp-command>            e.g.  101 reg_genmove black
    #? [expected-result]                #? [B2]   or   #? [1 (S4|T5)]

Expected-result markers (same semantics as the original regress.awk):
    |         alternation of acceptable answers, e.g. [B1|B3|C2]
    (...|...) grouped alternation, e.g. [1 (S4|T5)]
    &         ignore this test (do not compare)
    *         expected failure (known bug): matching counts as
              "unexpected pass", not matching is a "known failure"
    !         negate the match
    CATEGORY  one of the classification tokens listed below: the test
              is accepted without comparing an answer

Usage:
    python run_tests.py ENGINE [options] SUITE [SUITE ...]
    python run_tests.py ENGINE [options] --key     # the suites CI runs
    python run_tests.py ENGINE [options] --all     # every *.tst file

Options:
    --strict           exit 1 on any hard failure or engine crash
    --baseline         also compare pass/known-fail counts with
                       baseline.json; exit 1 if a suite got worse
    --update-baseline  store this run's counts in baseline.json
    -j N, --jobs N     run N suites in parallel (default 1)
    -e OPTS            extra engine options, e.g. -e "--level 8"
    -v                 print every failure and unexpected pass

ENGINE is a native gnugo executable or an Emscripten build (gnugo.js,
run under node). Set GNUGO_STDERR=<file> to keep the engine's stderr,
e.g. to collect sanitizer reports.

The script changes to its own directory (tests/) before running, so
relative paths such as "loadsgf games/foo.sgf" resolve correctly.

This program is part of GNU Go and is distributed under the GNU
General Public License, version 3 or (at your option) any later
version. See the COPYING file for details.
"""

import concurrent.futures
import json
import os
import re
import subprocess
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
BASELINE_FILE = os.path.join(TESTS_DIR, "baseline.json")

# The suites run on every CI build and registered with CTest. All must
# have zero hard failures.
KEY_SUITES = [
    "tiny.tst", "tactics.tst", "reading.tst", "atari_atari.tst",
    "owl.tst", "connect.tst", "semeai.tst", "endgame.tst",
    "capture.tst", "13x13.tst", "strategy.tst",
]

# Regression-test classification tokens: a `#? [TOKEN]` with one of
# these is accepted without comparing a concrete answer.
CATEGORIES = {
    "JOSEKI_DATABASE", "JOSEKI_PATTERN", "FUSEKI_CONCEPT",
    "DYNAMIC_CONNECTION", "TACTICAL_READING", "OWL_TUNING",
    "PATTERN_TUNING", "CONNECTION_TUNING", "MOVE_VALUATION",
    "ATARI_ATARI", "SEMEAI_MODULE", "KO_READING",
}

COUNTS = ("pass", "fail", "known-fail", "unexpected-pass", "ignore")


def evaluate(expected, result):
    """Compare one expected string against a GTP result.

    Markers may appear inside the brackets ([B2*], [0&], [!0]) or after
    them ([B2]*), as in the original regress.awk.

    Returns "pass", "fail", "known-fail", "unexpected-pass" or "ignore".
    """
    raw = expected.strip()
    ignore = raw.endswith("&")
    known_fail = raw.endswith("*")

    if raw.startswith("["):
        end = raw.find("]")
        content = raw[1:end] if end >= 0 else raw[1:]
    else:
        content = raw
    content = content.strip()

    if content.endswith("&"):
        ignore = True
        content = content[:-1].rstrip()
    if content.endswith("*"):
        known_fail = True
        content = content[:-1].rstrip()

    if ignore or content in CATEGORIES:
        return "ignore"

    negate = content.startswith("!")
    if negate:
        content = content[1:].lstrip()

    # awk-compatible regex semantics: '|' inside the expected string is
    # a regex alternation, so both [B1|B2] and [1 (S4|T5)] work.
    matched = re.search("^" + content + "$", result) is not None
    if negate:
        matched = not matched

    if known_fail:
        return "unexpected-pass" if matched else "known-fail"
    return "pass" if matched else "fail"


def read_suite(path):
    """Return the suite's command lines as (command, expected|None).

    A "#?" line attaches the expected result to the command before it.
    """
    pairs = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\r\n")
            if line.startswith("#?"):
                if pairs and pairs[-1][1] is None:
                    pairs[-1] = (pairs[-1][0], line[2:].strip())
            elif line and not line.startswith("#"):
                pairs.append((" ".join(line.split()), None))
    return pairs


def read_response(proc):
    """Read one GTP response line (starting with '=' or '?')."""
    while True:
        line = proc.stdout.readline()
        if not line:
            return None  # EOF: engine died
        line = line.rstrip("\r\n")
        if line and line[0] in "=?":
            return line
        # blank line or stray non-GTP output: skip


def engine_command(exe, engine_opts):
    cmd = [exe, "--mode", "gtp", "--quiet"] + engine_opts
    # An Emscripten build (gnugo.js, linked with NODERAWFS) runs under node.
    if exe.endswith(".js"):
        cmd.insert(0, "node")
    return cmd


def run_suite(suite, exe, engine_opts, verbose=False):
    """Run one suite.

    Returns (stats, failures, notes) where stats is None if the engine
    died, failures is a list of (id, expected, got) and notes holds the
    lines to print in verbose mode.
    """
    stats = dict.fromkeys(COUNTS, 0)
    failures = []
    notes = []

    stderr_path = os.environ.get("GNUGO_STDERR")
    stderr = open(stderr_path, "a") if stderr_path else subprocess.DEVNULL
    proc = subprocess.Popen(engine_command(exe, engine_opts),
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=stderr, text=True, bufsize=1)
    if stderr_path:
        stderr.close()
    try:
        for cmd, expected in read_suite(suite):
            m = re.match(r"^(\d+)\s", cmd)
            sent_id = m.group(1) if m else None
            try:
                proc.stdin.write(cmd + "\n")
                proc.stdin.flush()
            except OSError:
                return None, failures, notes
            resp = read_response(proc)
            if resp is None:
                return None, failures, notes
            body = resp[1:].strip()
            if sent_id is not None and body.startswith(sent_id):
                result = body[len(sent_id):].strip()
            else:
                result = body

            if sent_id is None or expected is None:
                continue  # setup command

            status = evaluate(expected, result)
            stats[status] += 1
            if status == "fail":
                failures.append((sent_id, expected, result))
            if verbose and status in ("fail", "unexpected-pass"):
                notes.append(f"  {suite}:{sent_id} {status}: "
                             f"expected {expected}, got {result}")
    finally:
        for step in (lambda: proc.stdin.write("quit\n"),
                     proc.stdin.flush, proc.stdin.close):
            try:
                step()
            except OSError:
                pass  # engine already exited (e.g. crashed mid-suite)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    return stats, failures, notes


def compare_with_baseline(suite, stats, baseline):
    """Return (verdict, text) comparing stats with the stored counts."""
    old = baseline.get(suite)
    if old is None:
        return "new", "no baseline"
    d_pass = stats["pass"] - old["pass"]
    d_kf = stats["known-fail"] - old["known_fail"]
    d_up = stats["unexpected-pass"] - old["unexpected_pass"]
    text = f"pass {d_pass:+d}, known-fail {d_kf:+d}, unexpected-pass {d_up:+d}"
    if d_pass < 0 or d_kf > 0:
        return "worse", text
    if d_pass > 0 or d_kf < 0 or d_up > 0:
        return "better", text
    return "same", text


def parse_args(argv):
    opts = {"strict": False, "baseline": False, "update": False,
            "jobs": 1, "engine_opts": [], "verbose": False, "suites": []}
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "-v":
            opts["verbose"] = True
        elif a == "--strict":
            opts["strict"] = True
        elif a == "--baseline":
            opts["baseline"] = True
        elif a == "--update-baseline":
            opts["update"] = True
        elif a in ("-j", "--jobs"):
            i += 1
            opts["jobs"] = max(1, int(argv[i]))
        elif a in ("-e", "--engine-opts"):
            i += 1
            opts["engine_opts"] = argv[i].split()
        elif a == "--key":
            opts["suites"] += KEY_SUITES
        elif a == "--all":
            opts["suites"] += sorted(f for f in os.listdir(TESTS_DIR)
                                     if f.endswith(".tst"))
        else:
            name = os.path.basename(a)
            opts["suites"].append(name if name.endswith(".tst")
                                  else name + ".tst")
        i += 1
    return opts


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 2
    exe = os.path.abspath(argv[0])
    if not os.path.exists(exe):
        print(f"error: engine not found: {argv[0]}", file=sys.stderr)
        return 2
    opts = parse_args(argv)
    os.chdir(TESTS_DIR)

    suites = []
    for suite in dict.fromkeys(opts["suites"]):  # dedupe, keep order
        if os.path.exists(suite):
            suites.append(suite)
        else:
            print(f"{suite}: MISSING", file=sys.stderr)
    missing = len(suites) < len(dict.fromkeys(opts["suites"]))

    baseline = {}
    if os.path.exists(BASELINE_FILE):
        with open(BASELINE_FILE) as fh:
            baseline = json.load(fh)

    with concurrent.futures.ThreadPoolExecutor(opts["jobs"]) as pool:
        futures = [pool.submit(run_suite, s, exe, opts["engine_opts"],
                               opts["verbose"]) for s in suites]

        grand = dict.fromkeys(COUNTS, 0)
        crashed, worse = [], []
        # Results are printed in suite order as they become available.
        for suite, future in zip(suites, futures):
            stats, failures, notes = future.result()
            for line in notes:
                print(line)
            if stats is None:
                crashed.append(suite)
                print(f"{suite}: CRASH (engine died mid-suite)")
                continue
            for k in COUNTS:
                grand[k] += stats[k]
            total = stats["pass"] + stats["fail"] + stats["known-fail"]
            pct = 100.0 * stats["pass"] / total if total else 0.0
            line = (f"{suite}: pass {stats['pass']}, fail {stats['fail']}, "
                    f"known-fail {stats['known-fail']}, "
                    f"unexpected-pass {stats['unexpected-pass']}, "
                    f"ignore {stats['ignore']}  ({pct:.1f}%)")
            if opts["baseline"]:
                verdict, text = compare_with_baseline(suite, stats, baseline)
                line += f"  [{verdict}: {text}]"
                if verdict == "worse":
                    worse.append(suite)
            print(line, flush=True)
            for sid, exp, got in failures[:10]:
                print(f"    #{sid}: expected {exp}, got {got}")
            if len(failures) > 10:
                print(f"    ... and {len(failures) - 10} more failures")
            if opts["update"]:
                baseline[suite] = {k.replace("-", "_"): stats[k]
                                   for k in COUNTS}

    total = grand["pass"] + grand["fail"] + grand["known-fail"]
    pct = 100.0 * grand["pass"] / total if total else 0.0
    print("\nTOTAL: pass {} fail {} known-fail {} unexpected-pass {} "
          "ignore {}  ({:.1f}%)".format(
              grand["pass"], grand["fail"], grand["known-fail"],
              grand["unexpected-pass"], grand["ignore"], pct))
    if crashed:
        print("CRASHED SUITES:", ", ".join(crashed))
    if worse:
        print("WORSE THAN BASELINE:", ", ".join(worse))

    if opts["update"]:
        with open(BASELINE_FILE, "w", newline="\n") as fh:
            json.dump(baseline, fh, indent=2, sort_keys=True)
            fh.write("\n")
        print("baseline.json updated.")

    if opts["strict"] and (grand["fail"] or crashed or missing):
        return 1
    if opts["baseline"] and (worse or crashed):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

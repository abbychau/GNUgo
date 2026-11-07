#!/usr/bin/env python3
"""GTP regression runner for GNU Go (.tst suites).

A minimal, self-contained replacement for regression/regress.awk and
regress.pl, useful on systems without perl/awk. It drives GNU Go over
the GTP protocol and checks each test's expected results.

Test file format (see the Texinfo manual, "Regression"):
    <id> <gtp-command>            e.g.  101 reg_genmove black
    #? [expected-result]                #? [B2]   or   #? [1 (S4|T5)]

Expected-result markers (same semantics as regress.awk/regress.pl):
    |         alternation of acceptable answers, e.g. [B1|B3|C2]
    (...|...) grouped alternation, e.g. [1 (S4|T5)]
    &         ignore this test (do not compare)
    *         expected failure (known bug): matching counts as
              "unexpected pass", not matching is a "known failure"
    !         negate the match
    CATEGORY  one of the classification tokens listed below: the test
              is accepted without comparing an answer

Usage:
    python run_tests.py <gnugo.exe> <suite.tst> [suite2.tst ...]
    python run_tests.py <gnugo.exe> --all        # every *.tst file

The script changes to its own directory (tests/) before running, so
relative paths such as "loadsgf games/foo.sgf" resolve correctly.

This program is part of GNU Go and is distributed under the GNU
General Public License, version 3 or (at your option) any later
version. See the COPYING file for details.
"""

import os
import re
import subprocess
import sys

# Regression-test classification tokens (from regress.pl): a `#? [TOKEN]`
# with one of these is accepted without comparing a concrete answer.
CATEGORIES = {
    "JOSEKI_DATABASE", "JOSEKI_PATTERN", "FUSEKI_CONCEPT",
    "DYNAMIC_CONNECTION", "TACTICAL_READING", "OWL_TUNING",
    "PATTERN_TUNING", "CONNECTION_TUNING", "MOVE_VALUATION",
    "ATARI_ATARI", "SEMEAI_MODULE", "KO_READING",
}


def evaluate(expected, result):
    """Compare one expected string against a GTP result.

    Markers may appear inside the brackets ([B2]*, [0&], [!0]) or after
    them ([B2]*), as in the original regress.awk/regress.pl.

    Returns ("pass"|"fail"|"known-fail"|"unexpected-pass"|"ignore", "").
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
        return "ignore", ""

    negate = content.startswith("!")
    if negate:
        content = content[1:].lstrip()

    # awk-compatible regex semantics: '|' inside the expected string is
    # a regex alternation, so both [B1|B2] and [1 (S4|T5)] work.
    regex = "^" + content + "$"
    matched = re.search(regex, result) is not None
    if negate:
        matched = not matched

    if known_fail:
        return ("unexpected-pass" if matched else "known-fail"), ""
    return ("pass" if matched else "fail"), ""


def read_next_response(proc):
    """Read one GTP response line (starting with '=' or '?')."""
    while True:
        line = proc.stdout.readline()
        if not line:
            return None  # EOF: engine died
        line = line.rstrip("\r\n")
        if not line:
            continue
        if line[0] in "=?":
            return line
        # stray non-GTP output (should be suppressed by --quiet): skip


# Phase-2 driver: scan the file into (command, expected) pairs, then
# drive the engine synchronously (GTP is strictly request/response).

def run_suite2(suite_path, exe, verbose=False, engine_opts=None):
    stats = {"pass": 0, "fail": 0, "known-fail": 0,
             "unexpected-pass": 0, "ignore": 0}
    details = []

    # Phase 1: scan the file into an ordered list of commands; a "#?" line
    # attaches the expected result to the immediately preceding command.
    pairs = []          # every command line, in order: (cmd, expected|None)
    with open(suite_path, "r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\r\n")
            if line.startswith("#?"):
                expected = line[2:].strip()
                if pairs and pairs[-1][1] is None:
                    pairs[-1] = (pairs[-1][0], expected)
                # an orphan expected (with no preceding command) is ignored
            elif not line or line.startswith("#"):
                continue
            else:
                pairs.append((" ".join(line.split()), None))

    # Phase 2: drive the engine.
    cmdline = [exe, "--mode", "gtp", "--quiet"]
    if engine_opts:
        cmdline += engine_opts
    proc = subprocess.Popen(
        cmdline,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, bufsize=1,
    )
    try:
        for cmd, expected in pairs:
            if cmd is None:
                continue
            m = re.match(r"^(\d+)\s", cmd)
            sent_id = m.group(1) if m else None
            try:
                proc.stdin.write(cmd + "\n")
                proc.stdin.flush()
            except (BrokenPipeError, OSError):
                return None
            resp = read_next_response(proc)
            if resp is None:
                return None
            body = resp[1:].strip()
            if sent_id is not None and body.startswith(sent_id):
                result = body[len(sent_id):].strip()
            else:
                result = body

            if sent_id is None or expected is None:
                continue  # setup command or orphan expected

            status, _ = evaluate(expected, result)
            stats[status] += 1
            if status == "fail":
                details.append((sent_id, expected, result))
            if verbose and status in ("fail", "unexpected-pass"):
                print(f"  {suite_path}:{sent_id} {status}: "
                      f"expected {expected}, got {result}")
    finally:
        try:
            proc.stdin.write("quit\n")
            proc.stdin.flush()
        except OSError:
            pass
        proc.stdin.close()
        proc.wait(timeout=10)

    return stats, details


def main(argv):
    if len(argv) < 1:
        print(__doc__)
        return 2
    exe = argv[0]
    verbose = False
    engine_opts = []
    args = []
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "-v":
            verbose = True
        elif a in ("-e", "--engine-opts"):
            i += 1
            if i < len(argv):
                engine_opts = argv[i].split()
        else:
            args.append(a)
        i += 1

    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.exists(exe):
        print(f"error: engine not found: {exe}", file=sys.stderr)
        return 2

    suites = []
    if "--all" in args:
        suites = sorted(f for f in os.listdir(".")
                        if f.endswith(".tst"))
    else:
        suites = [a if a.endswith(".tst") else a + ".tst" for a in args]

    grand = {"pass": 0, "fail": 0, "known-fail": 0,
             "unexpected-pass": 0, "ignore": 0}
    crashed = []
    for suite in suites:
        if not os.path.exists(suite):
            print(f"  {suite}: MISSING", file=sys.stderr)
            continue
        res = run_suite2(suite, exe, verbose, engine_opts)
        if res is None:
            crashed.append(suite)
            print(f"{suite}: CRASH (engine died mid-suite)")
            continue
        stats, details = res
        for k in grand:
            grand[k] += stats[k]
        total = stats["pass"] + stats["fail"] + stats["known-fail"]
        pct = (100.0 * stats["pass"] / total) if total else 0.0
        print(f"{suite}: pass {stats['pass']}, fail {stats['fail']}, "
              f"known-fail {stats['known-fail']}, "
              f"unexpected-pass {stats['unexpected-pass']}, "
              f"ignore {stats['ignore']}  ({pct:.1f}%)")
        for sid, exp, got in details[:10]:
            print(f"    #{sid}: expected {exp}, got {got}")
        if len(details) > 10:
            print(f"    ... and {len(details) - 10} more failures")

    total = grand["pass"] + grand["fail"] + grand["known-fail"]
    pct = (100.0 * grand["pass"] / total) if total else 0.0
    print("\nTOTAL: pass {} fail {} known-fail {} unexpected-pass {} "
          "ignore {}  ({:.1f}%)".format(
              grand["pass"], grand["fail"], grand["known-fail"],
              grand["unexpected-pass"], grand["ignore"], pct))
    if crashed:
        print("CRASHED SUITES:", ", ".join(crashed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
#!/usr/bin/env python3
"""Play matches between two GTP engines and estimate their strength difference.

Usage:
    python match.py ENGINE_A ENGINE_B [options]

ENGINE_A is the engine under test, ENGINE_B the reference (for example a
build of unmodified GNU Go 3.8). Each may be a native executable or an
Emscripten build (gnugo.js, run under node); extra command-line options
for one engine go in --args-a / --args-b.

Games alternate colours. GNU Go is nearly deterministic, so without help
most games would repeat; each game therefore starts from a few random
moves (--opening, chosen from the 3rd to 5th lines, the same opening for
both colour assignments of a pair) and a per-game --seed. The result of
a finished game is the reference engine's final_score; if the engine under
test disagrees, the game is counted as the reference says and reported.

Output: win rate of A with a 95% interval, the Elo difference, results
by colour and the number of distinct games. The interval is computed
over game pairs (a Dirichlet posterior over pair outcomes), because a
pair in which both engines play the same moves splits 1-1 regardless of
strength; the number of decisive pairs is the real sample size. --json writes the
same data plus per-game records; --sgf-dir saves every game.

Exit status: 0, or 1 if --min-score is given and A's score is lower.
"""

import argparse
import json
import math
import os
import random
import shlex
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

LETTERS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"


class EngineError(RuntimeError):
    pass


class Engine:
    def __init__(self, path, extra, seed, level, name):
        path = os.path.abspath(path)
        cmd = [path, "--mode", "gtp", "--quiet", "--seed", str(seed),
               "--level", str(level)] + extra
        if path.endswith(".js"):
            cmd.insert(0, "node")
        self.name = name
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL,
                                     text=True, bufsize=1)

    def send(self, command):
        try:
            self.proc.stdin.write(command + "\n")
            self.proc.stdin.flush()
        except OSError as e:
            raise EngineError(f"{self.name}: cannot send '{command}': {e}")
        lines = []
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise EngineError(f"{self.name} exited during '{command}'")
            line = line.rstrip("\r\n")
            if not line and lines:
                break
            if line or lines:
                lines.append(line)
        text = "\n".join(lines)
        if not text.startswith("="):
            raise EngineError(f"{self.name}: '{command}' failed: {text}")
        return text[1:].strip()

    def close(self):
        try:
            self.send("quit")
        except EngineError:
            pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def vertex_to_sgf(vertex, size):
    if vertex.upper() == "PASS":
        return ""
    col = LETTERS.index(vertex[0].upper())
    row = size - int(vertex[1:])
    return "abcdefghijklmnopqrstuvwxy"[col] + "abcdefghijklmnopqrstuvwxy"[row]


def random_opening(rng, size, count):
    lo, hi = (2, size - 3) if size >= 9 else (0, size - 1)
    lo, hi = min(lo, size // 2), max(hi, size // 2)
    band = [(c, r) for c in range(size) for r in range(size)
            if lo <= c <= hi and lo <= r <= hi
            and (min(c, r, size - 1 - c, size - 1 - r) <= 4 or size <= 9)]
    picks = rng.sample(band, min(count, len(band)))
    return [f"{LETTERS[c]}{r + 1}" for c, r in picks]


def parse_score(text):
    """'B+3.5' -> 3.5 for black, 'W+R' -> large negative, '0' -> 0."""
    text = text.strip()
    if text in ("0", "Draw"):
        return 0.0
    side, _, margin = text.partition("+")
    value = 1000.0 if margin.upper() in ("R", "RESIGN", "") else float(margin)
    return value if side.upper() == "B" else -value


def play_game(args, index, opening, a_is_black):
    seed = args.seed + index
    a = Engine(args.engine_a, args.args_a, seed, args.level, "A")
    b = Engine(args.engine_b, args.args_b, seed, args.level_b, "B")
    engines = [a, b]
    black, white = (a, b) if a_is_black else (b, a)
    record = {"game": index, "a_color": "black" if a_is_black else "white",
              "opening": opening, "moves": []}
    start = time.time()
    try:
        for e in engines:
            e.send(f"boardsize {args.size}")
            e.send("clear_board")
            e.send(f"komi {args.komi}")
        to_move, color = black, "black"
        for v in opening:
            for e in engines:
                e.send(f"play {color} {v}")
            record["moves"].append(v)
            to_move, color = (white, "white") if color == "black" else (black, "black")
        passes = 0
        resigned = None
        while len(record["moves"]) < args.max_moves:
            v = to_move.send(f"genmove {color}")
            if v.lower() == "resign":
                resigned = color
                break
            other = b if to_move is a else a
            other.send(f"play {color} {v}")
            record["moves"].append(v)
            passes = passes + 1 if v.upper() == "PASS" else 0
            if passes == 2:
                break
            to_move, color = (white, "white") if color == "black" else (black, "black")
        if resigned:
            result = ("W+R" if resigned == "black" else "B+R")
            record["result"] = result
        else:
            result = b.send("final_score")
            record["result"] = result
            a_view = a.send("final_score")
            if a_view != result:
                record["disagreement"] = a_view
        if len(record["moves"]) >= args.max_moves and passes < 2:
            record["move_limit"] = True
        margin = parse_score(result)
        black_score = 1.0 if margin > 0 else 0.0 if margin < 0 else 0.5
        record["a_score"] = black_score if a_is_black else 1.0 - black_score
    except EngineError as e:
        record["error"] = str(e)
    finally:
        for e in engines:
            e.close()
    record["seconds"] = round(time.time() - start, 1)
    return record


def to_sgf(record, args):
    a_black = record["a_color"] == "black"
    pb, pw = ("A", "B") if a_black else ("B", "A")
    out = [f"(;GM[1]FF[4]SZ[{args.size}]KM[{args.komi}]PB[{pb}]PW[{pw}]"
           f"RE[{record.get('result', '?')}]"]
    color = "B"
    for v in record["moves"]:
        out.append(f";{color}[{vertex_to_sgf(v, args.size)}]")
        color = "W" if color == "B" else "B"
    out.append(")\n")
    return "".join(out)


def wilson(score, n, z=1.96):
    if n == 0:
        return 0.0, 1.0
    p = score / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def pair_interval(records, samples=20000):
    """95% interval for A's score from game pairs.

    The two games of a pair share an opening and are not independent:
    when both engines play the same moves, the pair splits 1-1 whatever
    their strength. Pairs are therefore the unit: each pair scores 0,
    0.5 or 1 (0.25 / 0.75 with draws), and the interval is the central
    95% of the score under a Dirichlet posterior over those outcomes
    (prior 0.5 per outcome). Unlike a normal approximation it stays wide
    when few pairs are decisive, and agrees with it on large samples.
    Returns (low, high, complete pairs, decisive pairs) or None.
    """
    pairs = {}
    for r in records:
        pairs.setdefault(r["game"] // 2, []).append(r["a_score"])
    scores = [sum(s) / 2 for s in pairs.values() if len(s) == 2]
    if not scores:
        return None
    counts = {0.0: 0, 0.5: 0, 1.0: 0}
    for s in scores:
        counts[s] = counts.get(s, 0) + 1
    values = sorted(counts)
    rng = random.Random(0)          # fixed: same games, same interval
    draws = []
    for _ in range(samples):
        g = [rng.gammavariate(counts[v] + 0.5, 1.0) for v in values]
        draws.append(sum(v * x for v, x in zip(values, g)) / sum(g))
    draws.sort()
    lo, hi = draws[int(0.025 * samples)], draws[int(0.975 * samples) - 1]
    decisive = len(scores) - counts[0.5]
    return lo, hi, len(scores), decisive


def elo(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return -400 * math.log10(1 / p - 1)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n\n".join(__doc__.split("\n\n")[1:]))
    ap.add_argument("engine_a", help="engine under test")
    ap.add_argument("engine_b", help="reference engine")
    ap.add_argument("--args-a", default="", help="extra options for A")
    ap.add_argument("--args-b", default="", help="extra options for B")
    ap.add_argument("-n", "--games", type=int, default=100,
                    help="number of games, rounded up to even (default 100)")
    ap.add_argument("--size", type=int, default=9)
    ap.add_argument("--komi", type=float, default=7.5)
    ap.add_argument("--level", type=int, default=10, help="level of A (and B)")
    ap.add_argument("--level-b", type=int, help="level of B (default: --level)")
    ap.add_argument("--opening", type=int, default=4,
                    help="random opening moves per game pair (default 4)")
    ap.add_argument("--max-moves", type=int,
                    help="stop and score after this many moves (default 3*size^2)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--sgf-dir", help="save every game as SGF here")
    ap.add_argument("--json", help="write summary and games to this file")
    ap.add_argument("--min-score", type=float,
                    help="exit 1 if A's score fraction is below this")
    ap.add_argument("-q", "--quiet", action="store_true",
                    help="no per-game lines")
    args = ap.parse_args()
    args.args_a = shlex.split(args.args_a)
    args.args_b = shlex.split(args.args_b)
    if args.level_b is None:
        args.level_b = args.level
    if args.max_moves is None:
        args.max_moves = 3 * args.size * args.size
    pairs = (args.games + 1) // 2

    rng = random.Random(args.seed)
    jobs = []
    for p in range(pairs):
        opening = random_opening(rng, args.size, args.opening)
        jobs.append((2 * p, opening, True))
        jobs.append((2 * p + 1, opening, False))

    if args.sgf_dir:
        os.makedirs(args.sgf_dir, exist_ok=True)
    print(f"{len(jobs)} games, {args.size}x{args.size}, komi {args.komi}, "
          f"level {args.level}/{args.level_b}, {args.opening} opening moves, "
          f"{args.jobs} jobs", flush=True)

    records = []
    start = time.time()
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(play_game, args, *j) for j in jobs]
        for f in as_completed(futures):
            r = f.result()
            records.append(r)
            if args.sgf_dir and "error" not in r:
                with open(os.path.join(args.sgf_dir, f"game{r['game']:04d}.sgf"),
                          "w", encoding="utf-8") as fh:
                    fh.write(to_sgf(r, args))
            if not args.quiet:
                if "error" in r:
                    status = "ERROR " + r["error"]
                else:
                    status = (f"{r['result']:>8}  A {'won' if r['a_score'] == 1 else 'lost' if r['a_score'] == 0 else 'drew'}"
                              f"  {len(r['moves'])} moves")
                    if "disagreement" in r:
                        status += f"  (A scored {r['disagreement']})"
                print(f"[{len(records):4d}/{len(jobs)}] game {r['game']:4d} "
                      f"A={r['a_color']:5}  {status}", flush=True)
    records.sort(key=lambda r: r["game"])

    done = [r for r in records if "error" not in r]
    errors = len(records) - len(done)
    n = len(done)
    score = sum(r["a_score"] for r in done)
    lo, hi = wilson(score, n)
    paired = pair_interval(done)
    if paired:
        lo, hi, n_pairs, decisive = paired
    p = score / n if n else 0.0
    by_color = {}
    for c in ("black", "white"):
        g = [r for r in done if r["a_color"] == c]
        by_color[c] = {"games": len(g), "score": sum(r["a_score"] for r in g)}
    distinct = len({tuple(r["moves"]) for r in done})
    disagreements = sum("disagreement" in r for r in done)
    move_limit = sum(r.get("move_limit", False) for r in done)

    print()
    print(f"A: {args.engine_a} {' '.join(args.args_a)}".rstrip())
    print(f"B: {args.engine_b} {' '.join(args.args_b)}".rstrip())
    print(f"games     {n} finished, {errors} errors, {distinct} distinct, "
          f"{time.time() - start:.0f} s")
    if n:
        print(f"A score   {score:g}/{n} = {100 * p:.1f}%  "
              f"(95% CI {100 * lo:.1f}-{100 * hi:.1f}%)")
        print(f"Elo A-B   {elo(p):+.0f}  (95% CI {elo(lo):+.0f} to {elo(hi):+.0f})")
        if paired:
            print(f"pairs     {n_pairs} complete, {decisive} decisive, "
                  f"{n_pairs - decisive} split 1-1 (CI is over pairs)")
            if decisive < 10:
                print(f"warning   only {decisive} decisive pairs: the engines "
                      "mostly play alike, so the interval says little about "
                      "a strength difference; play more games")
        for c, s in by_color.items():
            if s["games"]:
                print(f"A {c:5}   {s['score']:g}/{s['games']}")
    if disagreements:
        print(f"scoring   A and B disagreed on {disagreements} games (B's count used)")
    if move_limit:
        print(f"move cap  {move_limit} games stopped at {args.max_moves} moves")

    if args.json:
        summary = {"engine_a": args.engine_a, "engine_b": args.engine_b,
                   "args_a": args.args_a, "args_b": args.args_b,
                   "size": args.size, "komi": args.komi,
                   "level": args.level, "level_b": args.level_b,
                   "opening": args.opening, "seed": args.seed,
                   "games": n, "errors": errors, "distinct": distinct,
                   "pairs": n_pairs if paired else None,
                   "decisive_pairs": decisive if paired else None,
                   "score": score, "ci95": [lo, hi],
                   "elo": elo(p) if n else None,
                   "by_color": by_color, "records": records}
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=1)

    if errors:
        return 1
    if args.min_score is not None and (n == 0 or p < args.min_score):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Check that two GNU Go builds play the same moves.

Usage:
    python compare_engines.py <engine-a> <engine-b> [--moves N] [--sizes 9,13,19]
                              [--seed S] [--level L]

Each engine may be a native executable or an Emscripten build (gnugo.js,
run under node). Both play the same self-play game from the same seed:
engine A chooses each move with genmove, then the move is played on
engine B, after B's own genmove is compared. Builds that compile the same
sources should agree move for move; a difference points to undefined
behavior or a platform-dependent computation.

Exits 0 when all games agree, 1 on the first disagreement.
"""

import os
import subprocess
import sys


class Engine:
    def __init__(self, path, seed, level):
        path = os.path.abspath(path)
        cmd = [path, "--mode", "gtp", "--quiet", "--seed", str(seed),
               "--level", str(level)]
        if path.endswith(".js"):
            cmd.insert(0, "node")
        self.name = os.path.basename(path)
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL,
                                     text=True, bufsize=1)

    def send(self, command):
        self.proc.stdin.write(command + "\n")
        self.proc.stdin.flush()
        lines = []
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError(f"{self.name} exited during '{command}'")
            line = line.rstrip("\r\n")
            if not line and lines:
                break
            if line or lines:
                lines.append(line)
        text = "\n".join(lines)
        if not text.startswith("="):
            raise RuntimeError(f"{self.name}: '{command}' failed: {text}")
        return text[1:].strip()

    def close(self):
        try:
            self.send("quit")
        except (RuntimeError, OSError):
            pass
        self.proc.wait(timeout=10)


def play_game(path_a, path_b, size, moves, seed, level):
    a = Engine(path_a, seed, level)
    b = Engine(path_b, seed, level)
    try:
        for e in (a, b):
            e.send(f"boardsize {size}")
            e.send("clear_board")
            e.send("komi 6.5")
        color = "black"
        passes = 0
        for n in range(1, moves + 1):
            move_a = a.send(f"reg_genmove {color}")
            move_b = b.send(f"reg_genmove {color}")
            if move_a.upper() != move_b.upper():
                print(f"  {size}x{size}: move {n} ({color}) differs: "
                      f"{a.name}={move_a} {b.name}={move_b}")
                return False
            if move_a.lower() == "resign":
                break
            for e in (a, b):
                e.send(f"play {color} {move_a}")
            passes = passes + 1 if move_a.upper() == "PASS" else 0
            if passes == 2:
                break
            color = "white" if color == "black" else "black"
        hash_a, hash_b = a.send("showboard"), b.send("showboard")
        if hash_a != hash_b:
            print(f"  {size}x{size}: final boards differ")
            return False
        print(f"  {size}x{size}: {n} moves identical")
        return True
    finally:
        a.close()
        b.close()


def main(argv):
    args = [x for x in argv if not x.startswith("--")]
    opts = {}
    i = 0
    while i < len(argv):
        if argv[i].startswith("--") and i + 1 < len(argv):
            opts[argv[i][2:]] = argv[i + 1]
            args = [x for x in args if x != argv[i + 1]]
            i += 2
        else:
            i += 1
    if len(args) != 2:
        print(__doc__)
        return 2
    moves = int(opts.get("moves", 60))
    sizes = [int(s) for s in opts.get("sizes", "9,13,19").split(",")]
    seed = int(opts.get("seed", 1))
    level = int(opts.get("level", 10))

    print(f"Comparing {args[0]} and {args[1]} (seed {seed}, level {level})")
    ok = all(play_game(args[0], args[1], size, moves, seed, level)
             for size in sizes)
    print("all games identical" if ok else "ENGINES DISAGREE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

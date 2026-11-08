# GNU Go

[![CI](https://github.com/abbychau/GNUgo/actions/workflows/ci.yml/badge.svg)](https://github.com/abbychau/GNUgo/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/abbychau/GNUgo)](https://github.com/abbychau/GNUgo/releases/latest)
[![License: GPL v3+](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](COPYING)

GNU Go 3.8, the Go-playing program of the GNU project, with a CMake
build, a WebAssembly port that runs in web pages, and automated tests
on Linux, macOS, Windows and the browser build.

- **Play in the browser:** <https://abbychau.github.io/GNUgo/>
- **What's different from GNU Go 3.8:** <https://abbychau.github.io/GNUgo/differences.html>
- **Manual:** <https://abbychau.github.io/GNUgo/manual/>
- **Downloads:** [latest release](https://github.com/abbychau/GNUgo/releases/latest)

## Download

Each release has ready-to-run builds:

| File | Contents |
|---|---|
| `gnugo-windows-x64.zip` | `gnugo.exe` for Windows |
| `gnugo-linux-x64.tar.gz` | `gnugo` for Linux (x86-64) |
| `gnugo-macos-arm64.tar.gz` | `gnugo` for macOS (Apple silicon) |
| `gnugo-wasm.zip` | WebAssembly engine, JavaScript API and the demo page |
| `gnugo-wasm-npm.tgz` | The same as an npm package with TypeScript types |

## Build

You need CMake 3.16 or newer and a C compiler. Python 3 is needed for
the tests.

```sh
cmake --preset release            # or: cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build --preset release    #     cmake --build build --config Release --parallel
ctest --preset release            # run the regression tests
```

The program is `build/src/interface/gnugo`
(`build\src\interface\Release\gnugo.exe` with Visual Studio).
`cmake --install build` installs it with its man page.

[BUILDING.md](BUILDING.md) covers Windows, macOS, the WebAssembly build,
the sanitizer build and compile-time options.

## Use

**Graphical clients.** GNU Go speaks the Go Text Protocol (GTP). In a
GTP client such as [Sabaki](https://sabaki.yichuanshen.de/) or
[GoGui](https://github.com/Remi-Coulom/gogui), add an engine with the
command `gnugo --mode gtp` (for example `gnugo --mode gtp --level 10`).

**Terminal.** Run `gnugo` to play on an ASCII board. Type `help` for the
commands. At the end of the game pass twice, and GNU Go guides you
through marking dead stones and counting.

**Web pages and Node.js.** The WebAssembly build runs the engine in a
Web Worker behind a small Promise-based API:

```js
import { GnuGo } from "./gnugo.js";
const go = await GnuGo.create();
await go.boardsize(19);
await go.play("black", "D4");
const reply = await go.genmove("white");   // e.g. "Q16"
```

See [wasm/README.md](wasm/README.md) for the full API, SGF support, time
limits and how to use the npm package.

**Emacs.** Load `contrib/gnugo.el` (`M-x load-file`, or
`(autoload 'gnugo "gnugo" "GNU Go" t)` in your init file) and start a
game with `M-x gnugo`.

**Go Modem Protocol.** Older clients such as CGoban 1 talk to GNU Go
over GMP. GMP cannot send the komi, so pass it on the command line,
e.g. `gnugo --komi 6.5`.

### Common options

Run `gnugo --help` or `man gnugo` for the full list.

| Option | Meaning |
|---|---|
| `--mode ascii\|gtp\|gmp` | Playing mode. The default is ASCII on a terminal, otherwise GMP. |
| `--level N` | Strength and speed, 0 to 10. Level 10 is the default. |
| `--boardsize N` | Board size, 1 to 19 (default 19). |
| `--komi K`, `--handicap N` | Komi and fixed handicap (0 to 9 stones). |
| `--chinese-rules`, `--japanese-rules` | Area or territory scoring. Japanese is the default. |
| `-M`, `--cache-size MB` | Memory for the reading cache (default 8 MB). |
| `-l FILE`, `-L MOVE` | Load an SGF file, stopping before move MOVE (a number or a point). |
| `-o FILE` | Write the game to an SGF file. |
| `--printsgf FILE` | Write a diagram of the position (useful with `-l` and `-L`). |
| `--monte-carlo` | Experimental Monte Carlo move generation (9x9 or smaller). |
| `--quiet` | Don't print the copyright and other messages. |

## Tests

The regression suites in `tests/` are GTP scripts with expected
answers. The 11 main suites run under CTest on every CI build:

```sh
ctest --test-dir build -j8                                   # -C Release for Visual Studio
python tests/run_tests.py build/src/interface/gnugo blunder.tst
python tests/run_tests.py build/src/interface/gnugo --key -j8 --baseline
```

A suite fails on any unexpected failure, an engine crash, or if it does
worse than `tests/baseline.json`. CI also builds with
UndefinedBehaviorSanitizer and checks that the native and WebAssembly
builds choose identical moves. See [tests/README](tests/README).

## Source layout

| Path | Contents |
|---|---|
| `src/engine/` | The Go engine: reading, owl, influence, pattern matching, Monte Carlo, move generation |
| `src/interface/` | Front ends (ASCII, GMP, GTP, solo, test) and the WebAssembly API (`wasm_api.c`) |
| `src/sgf/` | Smart Game Format library |
| `src/utils/` | Portability and utility functions |
| `patterns/` | The pattern databases (`.db`, `.dtr`, `.dbz`, `.sgf`) and the generators (mkpat, joseki, dfa, ...) that compile them into C at build time |
| `pages/` | Extra pages of the GitHub Pages site |
| `wasm/` | Browser files: Web Worker, JavaScript API, TypeScript types, demo page, npm metadata |
| `tests/` | Regression suites (`.tst`), their game records, `run_tests.py` and `baseline.json` |
| `tests/tools/` | Native-vs-WebAssembly move comparison and the WebAssembly smoke test |
| `doc/` | Texinfo manual, man page, and the original project's AUTHORS, THANKS, TODO and ChangeLog |
| `contrib/` | Emacs mode, board images, a Perl module, GTP examples, and the original regression tools (`contrib/regress/`) |
| `.github/workflows/` | CI, GitHub Pages and releases |

The pattern database is the heart of the program. Edit the `.db` files,
not the generated C files.

## Documentation

- `man gnugo` and `gnugo --help` for using the program.
- The Texinfo manual in `doc/` documents both use and the engine's
  algorithms. Read it [online](https://abbychau.github.io/GNUgo/manual/)
  or build it with `cmake --build build --target manual` (needs
  `makeinfo`).
- [NEWS](NEWS) lists the changes in each version.
  [doc/TODO](doc/TODO) has ideas for contributors (from the original
  project), [doc/ChangeLog](doc/ChangeLog) is its detailed history up
  to 3.8, and [doc/AUTHORS](doc/AUTHORS) and [doc/THANKS](doc/THANKS)
  credit its authors and helpers.

The original GNU Go project is at
<https://www.gnu.org/software/gnugo/> (mailing list: gnugo@gnu.org).

## Copyright and license

All files Copyright 1999, 2000, 2001, 2002, 2003, 2004, 2005, 2006,
2007, 2008 and 2009 by the Free Software Foundation except as noted below.

All files are under the GNU General Public License, version 3 or (at
your option) any later version, which may be found in the file
[COPYING](COPYING), with the following exceptions.

- The files `src/interface/gtp.c` and `gtp.h` are copyright 2001 by the
  Free Software Foundation. In the interests of promoting the Go Text
  Protocol these two files are licensed under a less restrictive license
  than the GPL and are free for unrestricted use. The GTP license
  appears in each file.
- The files `gmp.c` and `gmp.h` are copyright Bill Shubert. These are
  free for unrestricted use.
- The files `tests/golois/*` and the tests `vie.tst`, `connect.tst`,
  `capture.tst` and `global.tst` are copyright Tristan Cazenave and are
  used with his permission.
- The SGF files in `tests/games/handtalk` are copyright Jessie Annala
  and are used with permission.
- The SGF files in `tests/games/mertin13x13` are copyright Stefan
  Mertin and are used with permission.
- The remaining SGF files are either copyright by the FSF or are in the
  public domain.

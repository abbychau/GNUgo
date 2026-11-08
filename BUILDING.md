# Building GNU Go

GNU Go is built with CMake (3.16 or newer; 3.25 or newer for the
presets) and a C compiler. Python 3 is needed for the regression tests,
and `makeinfo` (package `texinfo`) for the HTML manual.

- [Presets](#presets)
- [GNU/Linux and other Unix systems](#gnulinux-and-other-unix-systems)
- [Windows](#windows)
- [macOS](#macos)
- [WebAssembly](#webassembly)
- [UndefinedBehaviorSanitizer](#undefinedbehaviorsanitizer)
- [Tests](#tests)
- [Manual](#manual)
- [Compile-time options](#compile-time-options)

## Presets

`CMakePresets.json` defines the common builds. Each preset has a
configure, build and test step:

```sh
cmake --preset release
cmake --build --preset release
ctest --preset release
```

| Preset | Build directory | What it is |
|---|---|---|
| `release` | `build/` | Optimized native build |
| `debug` | `build-debug/` | Native build with debugging information |
| `ubsan` | `build-ubsan/` | UndefinedBehaviorSanitizer, gcc or clang only |
| `wasm` | `build-wasm/` | WebAssembly with Emscripten (Linux, macOS) |
| `wasm-windows` | `build-wasm/` | WebAssembly with Emscripten on Windows (needs GNU make) |

`cmake --list-presets` shows the presets available on your system.

## GNU/Linux and other Unix systems

Without presets:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
```

The program is `build/src/interface/gnugo`. You can run it from there
or install it with

```sh
sudo cmake --install build      # --prefix DIR to install elsewhere
```

which puts `gnugo` in `/usr/local/bin` and the man page in
`/usr/local/share/man/man6`.

To use make or Ninja instead of the default generator, add for example
`-G "Unix Makefiles"` or `-G Ninja` when configuring.

## Windows

With Visual Studio (2019 or newer, with the "Desktop development with
C++" workload), open a Developer Command Prompt in the source folder:

```bat
cmake -S . -B build
cmake --build build --config Release
```

The program is `build\src\interface\Release\gnugo.exe`. The presets work
too (`cmake --preset release`). Visual Studio can also open the source
folder directly with *File > Open > Folder*: it reads `CMakeLists.txt`
and `CMakePresets.json`.

Other toolchains work through CMake generators, for example
`-G "MinGW Makefiles"` for MinGW-w64 gcc with `mingw32-make`, or
`-G "NMake Makefiles"`.

## macOS

Install the Xcode command line tools (`xcode-select --install`) and
CMake (for example `brew install cmake`), then build as on Linux.

Socket support for GTP over TCP/IP (`--gtp-connect`, `--gtp-listen`) is
not detected automatically. To enable it, change
`#undef ENABLE_SOCKET_SUPPORT` to `#define ENABLE_SOCKET_SUPPORT 1` in
`config.h.cmake` before configuring.

## WebAssembly

The WebAssembly build runs GNU Go in web pages and under Node.js. It
needs the [Emscripten SDK](https://emscripten.org/docs/getting_started/downloads.html)
(tested with 7.0.0) and Node.js.

```sh
source ~/emsdk/emsdk_env.sh     # Windows: emsdk_env.bat
cmake --preset wasm             # Windows: --preset wasm-windows
cmake --build --preset wasm
ctest --preset wasm
```

Without presets, use `emcmake cmake -S . -B build-wasm -DCMAKE_BUILD_TYPE=Release`
(on Windows add `-G "MinGW Makefiles"`).

The pattern generators are compiled with Emscripten too and run under
Node.js during the build, so no native compiler is needed. The result
is in `build-wasm/web/`: the engine (`gnugo-core.js`, `gnugo-core.wasm`),
the Web Worker, the JavaScript API, TypeScript types, the demo page and
`package.json`. Serve that folder over HTTP to try the demo, for
example `python -m http.server -d build-wasm/web`. See
[wasm/README.md](wasm/README.md) for the API.

`build-wasm/src/interface/gnugo.js` is the ordinary command-line
program, runnable with `node build-wasm/src/interface/gnugo.js`.

## UndefinedBehaviorSanitizer

```sh
cmake --preset ubsan
cmake --build --preset ubsan
ctest --preset ubsan
```

Any undefined behavior aborts the engine, so the affected suite fails.
Set `GNUGO_STDERR=/tmp/ubsan.log` to keep the sanitizer reports. CI runs
this build on every push.

## Tests

`ctest` runs the 11 main regression suites in parallel (add
`-C Release` for Visual Studio builds). A suite fails on any unexpected
failure, an engine crash, or fewer passes / more known failures than
`tests/baseline.json`. To run suites directly:

```sh
python tests/run_tests.py build/src/interface/gnugo owl.tst
python tests/run_tests.py build/src/interface/gnugo --key -j8 --baseline
python tests/run_tests.py build/src/interface/gnugo --all -j8   # every suite
```

After a change that improves results, record the new counts with
`--key --update-baseline` and commit `tests/baseline.json`.

`tests/tools/compare_engines.py` plays seeded games with two builds and
reports the first move where they differ; CI uses it to check that the
native and WebAssembly builds play identically.

## Manual

```sh
cmake --build build --target manual
```

writes the HTML manual to `build/manual/index.html` and the Info manual
to `build/doc/gnugo.info`. The target is only defined when CMake finds
`makeinfo`. The manual is also
[online](https://abbychau.github.io/GNUgo/manual/).

## Compile-time options

The defaults and experimental features are set in `config.h.cmake`.
Edit it and reconfigure.

| Macro | Default | Meaning |
|---|---|---|
| `DEFAULT_LEVEL` | 10 | Default strength, 0 to 10. Level 10 is much more accurate than level 8 and takes about 1.6 times as long. |
| `DEFAULT_MEMORY` | -1 (8 MB) | Size of the reading cache in megabytes. |
| `CHINESE_RULES` | 0 | Use area scoring by default. |
| `RESIGNATION_ALLOWED` | 1 | Let GNU Go resign hopeless games. |
| `OWL_NODE_LIMIT`, `SEMEAI_NODE_LIMIT` | 1000, 500 | Search limits of the life-and-death and semeai readers. |
| `COSMIC_GNUGO` | 0 | Center-oriented influence. |
| `USE_BREAK_IN`, `EXPERIMENTAL_CONNECTIONS`, `ALTERNATE_CONNECTIONS` | 1 | Break-in and connection reading. |
| `EXPERIMENTAL_OWL_EXT`, `LARGE_SCALE`, `OWL_THREATS`, `ORACLE` | 0 | Experimental code: possibly stronger, slower and less tested. |
| `ENABLE_SOCKET_SUPPORT` | off | GTP over TCP/IP. |

Most can also be changed at run time: `--level`, `--cache-size`,
`--chinese-rules`, `--never-resign`, `--owl-node-limit` and so on (see
`gnugo --help`).

A larger cache often gives a modest speed-up, but a cache larger than
the free memory makes the system swap and slows everything down.

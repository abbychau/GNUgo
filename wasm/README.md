# GNU Go for the web (WebAssembly)

## Build

Requires the [Emscripten SDK](https://emscripten.org/docs/getting_started/downloads.html), CMake and a make tool.

```sh
source ~/emsdk/emsdk_env.sh          # Windows: emsdk_env.bat
emcmake cmake -S . -B build-wasm -DCMAKE_BUILD_TYPE=Release   # add -G "MinGW Makefiles" on Windows
cmake --build build-wasm -j8
```

The pattern generators (mkpat, joseki, ...) are compiled with Emscripten
too and run under node during the build, so no native compiler is needed.

Output in `build-wasm/web/`:

| File | Purpose |
|---|---|
| `gnugo-core.js`, `gnugo-core.wasm` | Emscripten module (`createGnuGoModule()`) |
| `gnugo-worker.js` | Web Worker hosting the engine |
| `gnugo.js` | ES module API (`GnuGo` class) |
| `index.html` | Demo: play against GNU Go |

Serve the folder over HTTP (e.g. `python -m http.server -d build-wasm/web`);
`file://` will not work because workers and wasm need a real origin.

## API

```js
import { GnuGo } from "./gnugo.js";
const go = await GnuGo.create();        // optional: { seed, workerUrl }
await go.boardsize(19);
await go.komi(6.5);
await go.level(10);                     // 0..10
await go.play("black", "D4");
const reply = await go.genmove("white"); // "Q16", "PASS" or "resign"
const score = await go.finalScore();     // "B+3.5"
const text = await go.command("estimate_score"); // any GTP command
```

`command()` rejects with `GtpError` for `?` responses. In C, the module
exports `gnugo_wasm_init(seed, memory_mb)` and `gnugo_wasm_gtp(line)`
(see `src/interface/wasm_api.c`) for use without the worker.

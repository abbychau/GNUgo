# GNU Go for the web (WebAssembly)

## Build

Requires the [Emscripten SDK](https://emscripten.org/docs/getting_started/downloads.html), CMake 3.25+ and Node.js
(on Windows also GNU make).

```sh
source ~/emsdk/emsdk_env.sh     # Windows: emsdk_env.bat
cmake --preset wasm             # Windows: --preset wasm-windows
cmake --build --preset wasm
ctest --preset wasm             # regression suites under node + smoke test
```

The pattern generators (mkpat, joseki, ...) are compiled with Emscripten
too and run under node during the build, so no native compiler is needed.

Output in `build-wasm/web/`:

| File | Purpose |
|---|---|
| `gnugo-core.js`, `gnugo-core.wasm` | Emscripten ES module; default export `createGnuGoModule()` |
| `gnugo-worker.js` | Module Web Worker hosting the engine |
| `gnugo.js` | ES module API (`GnuGo` class) |
| `index.html` | Demo: play against GNU Go |
| `gnugo.d.ts`, `package.json` | TypeScript types and npm package metadata |

Serve the folder over HTTP (e.g. `python -m http.server -d build-wasm/web`);
`file://` will not work because workers and wasm need a real origin.

## Use as a package

`build-wasm/web` is also an npm package (`@abbychau/gnugo-wasm`, with
TypeScript types in `gnugo.d.ts`). Tagged GitHub releases attach it as
`gnugo-wasm-npm.tgz`:

```sh
npm install ./gnugo-wasm-npm.tgz
```

It is also published to [GitHub Packages](https://github.com/abbychau/GNUgo/packages).
GitHub's npm registry needs a personal access token with the
`read:packages` scope, even for public packages. Add to `.npmrc`:

```
@abbychau:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=YOUR_TOKEN
```

and run `npm install @abbychau/gnugo-wasm`.

The engine runs in a worker that loads `gnugo-core.js` and
`gnugo-core.wasm` next to it, so serve these three files together. With
a bundler, copy `gnugo-worker.js`, `gnugo-core.js` and `gnugo-core.wasm`
from the package to your static/public folder and pass their location:

```js
import { GnuGo } from "@abbychau/gnugo-wasm";
const go = await GnuGo.create({ workerUrl: "/gnugo/gnugo-worker.js" });
```

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

`command()` rejects with `GtpError` for `?` responses.

### Time limits and stopping a search

```js
await go.timePerMove(5);   // soft budget: GNU Go lowers its level when moves run long
                           // (0 = no limit)

const pending = go.genmove("black");
await go.cancel();         // hard stop: pending rejects with GtpError { cancelled: true }
                           // and the engine is restarted with the same position
```

`cancel()` replaces the worker and replays the commands that changed the
game state (board size, komi, level, time settings, moves, undo,
handicap), so the game continues where it was. `go.busy` tells whether
a command is running.

### SGF

```js
const toMove = await go.loadSgf(sgfText);      // whole game; "black" | "white"
await go.loadSgf(sgfText, 42);                 // stop before move 42
const text = await go.toSgf();                 // setup + moves in order
const record = go.gameRecord();                // { size, komi, setup, moves, ... }
```

`toSgf()` is built from the commands sent through this object: moves,
passes, handicap and undo are all reflected. After `loadSgf()`, the
loaded position becomes setup stones. `positionSgf()` returns GNU Go's
own `printsgf` snapshot of the current position.

### Without the worker

`gnugo-core.js` can also be used directly, e.g. in Node.js. The module
exports the C functions `gnugo_wasm_init(seed, memory_mb)` and
`gnugo_wasm_gtp(line)` (see `src/interface/wasm_api.c`):

```js
import createGnuGoModule from "./gnugo-core.js";
const m = await createGnuGoModule({ print: () => {} });
m.ccall("gnugo_wasm_init", "number", ["number", "number"], [42, -1]);
const gtp = m.cwrap("gnugo_wasm_gtp", "string", ["string"]);
gtp("genmove black");   // "= D4\n\n"
```

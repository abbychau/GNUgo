#!/usr/bin/env node
/* Smoke test for the WebAssembly module (gnugo-core.js/.wasm).
 *
 * Usage: node tests/wasm_smoke.cjs build-wasm/web/gnugo-core.js
 *
 * Loads the module the same way gnugo-worker.js does, plays a few moves
 * over GTP and checks the responses. Exits non-zero on failure.
 */
"use strict";
const path = require("path");

const modulePath = path.resolve(process.argv[2] || "build-wasm/web/gnugo-core.js");
const createGnuGoModule = require(modulePath);

function check(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exit(1);
  }
  console.log("ok  ", msg);
}

createGnuGoModule({ print: () => {}, printErr: () => {} }).then((m) => {
  check(m.ccall("gnugo_wasm_init", "number", ["number", "number"], [42, -1]) === 1, "init");
  const gtp = m.cwrap("gnugo_wasm_gtp", "string", ["string"]);

  check(/^= 3\.8/.test(gtp("version")), "version is 3.8");
  check(gtp("boardsize 9") === "= \n\n", "boardsize 9");
  check(gtp("play black E5") === "= \n\n", "play black E5");
  check(gtp("play black E5").startsWith("? illegal move"), "occupied point is illegal");
  check(gtp("foo").startsWith("? unknown command"), "unknown command fails");

  for (const color of ["white", "black", "white", "black"]) {
    const r = gtp(`genmove ${color}`);
    check(/^= ([A-HJ-T]\d{1,2}|PASS)\n\n$/i.test(r), `genmove ${color} -> ${r.trim()}`);
  }

  const stones = gtp("list_stones black").trim().split(/\s+/).length - 1;
  check(stones === 3, `black has 3 stones (got ${stones})`);
  check(/^= [BW]\+\d+(\.\d)?\n\n$/.test(gtp("final_score")), "final_score");

  check(gtp("boardsize 19") === "= \n\n", "boardsize 19");
  check(/^= [A-HJ-T]\d{1,2}\n\n$/.test(gtp("genmove black")), "genmove on 19x19");
  console.log("all wasm smoke tests passed");
});

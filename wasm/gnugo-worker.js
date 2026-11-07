/* Web Worker hosting the GNU Go WebAssembly engine.
 *
 * The engine is synchronous and CPU heavy (genmove may take seconds on
 * 19x19), so it runs off the main thread. Protocol:
 *
 *   main -> worker: { id, cmd }            one GTP command line
 *   worker -> main: { id, response }       raw GTP response text
 *   worker -> main: { type: "ready" }      after the engine is initialized
 *   worker -> main: { type: "error", message }
 *
 * Optional query string on the worker URL: ?seed=<uint>
 */

/* global importScripts, createGnuGoModule */
importScripts("gnugo-core.js");

const params = new URLSearchParams(self.location.search);
const seed = Number(params.get("seed") ?? Math.floor(Math.random() * 0x7fffffff)) >>> 0;

let gtp = null;
const pending = [];

function handle({ id, cmd }) {
  let response;
  try {
    response = gtp(String(cmd));
  } catch (e) {
    response = `? internal error: ${e && e.message ? e.message : e}\n\n`;
  }
  self.postMessage({ id, response });
}

createGnuGoModule({
  print: () => {},              // engine chatter on stdout is not GTP output
  printErr: (t) => console.warn("[gnugo]", t),
}).then((Module) => {
  Module.ccall("gnugo_wasm_init", "number", ["number", "number"], [seed, -1]);
  gtp = Module.cwrap("gnugo_wasm_gtp", "string", ["string"]);
  self.postMessage({ type: "ready" });
  while (pending.length) handle(pending.shift());
}).catch((e) => {
  self.postMessage({ type: "error", message: String(e && e.message ? e.message : e) });
});

self.onmessage = (ev) => {
  if (gtp) handle(ev.data);
  else pending.push(ev.data);
};

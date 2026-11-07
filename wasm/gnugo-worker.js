/* Web Worker hosting the GNU Go WebAssembly engine.
 *
 * The engine is synchronous and CPU heavy (genmove may take seconds on
 * 19x19), so it runs off the main thread. Protocol:
 *
 *   main -> worker: { id, cmd }                    one GTP command line
 *   worker -> main: { id, response }               raw GTP response text
 *
 *   main -> worker: { id, writeFile, data }        write a text file into
 *   worker -> main: { id, ok: true }               the in-memory file system
 *   main -> worker: { id, readFile }               read it back
 *   worker -> main: { id, data }                   (e.g. for loadsgf/printsgf)
 *
 *   worker -> main: { id, error }                  file operation failed
 *   worker -> main: { type: "ready" }              after the engine is initialized
 *   worker -> main: { type: "error", message }     the engine failed to load
 *
 * Optional query string on the worker URL: ?seed=<uint>
 *
 * This is a module worker: start it with new Worker(url, { type: "module" }).
 */

import createGnuGoModule from "./gnugo-core.js";

const params = new URLSearchParams(self.location.search);
const seed = Number(params.get("seed") ?? Math.floor(Math.random() * 0x7fffffff)) >>> 0;

let Module = null;
let gtp = null;
const pending = [];

function handle(msg) {
  const { id } = msg;
  try {
    if (msg.writeFile !== undefined) {
      Module.FS.writeFile(msg.writeFile, String(msg.data));
      self.postMessage({ id, ok: true });
    } else if (msg.readFile !== undefined) {
      self.postMessage({ id, data: Module.FS.readFile(msg.readFile, { encoding: "utf8" }) });
    } else {
      self.postMessage({ id, response: gtp(String(msg.cmd)) });
    }
  } catch (e) {
    const message = e && e.message ? e.message : String(e);
    if (msg.cmd !== undefined) self.postMessage({ id, response: `? internal error: ${message}\n\n` });
    else self.postMessage({ id, error: message });
  }
}

createGnuGoModule({
  print: () => {},              // engine chatter on stdout is not GTP output
  printErr: (t) => console.warn("[gnugo]", t),
}).then((m) => {
  Module = m;
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

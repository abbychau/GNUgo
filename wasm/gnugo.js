/* GNU Go for the browser: a small Promise-based wrapper around the
 * WebAssembly engine running in a Web Worker.
 *
 *   import { GnuGo } from "./gnugo.js";
 *   const go = await GnuGo.create();          // loads gnugo-worker.js next to this file
 *   await go.boardsize(9);
 *   await go.play("black", "E5");
 *   const move = await go.genmove("white");   // e.g. "D4", "PASS", "resign"
 *   const raw = await go.command("showboard");
 *
 * Any GTP command GNU Go understands is available via command().
 * Commands are serialized: the engine processes one at a time.
 */

export class GtpError extends Error {
  constructor(command, message) {
    super(`${command}: ${message}`);
    this.name = "GtpError";
    this.command = command;
    this.gtpMessage = message;
  }
}

export class GnuGo {
  /**
   * @param {object} [options]
   * @param {string|URL} [options.workerUrl] URL of gnugo-worker.js
   * @param {number} [options.seed] random seed (unsigned int)
   */
  static create(options = {}) {
    const base = options.workerUrl
      ? new URL(options.workerUrl, location.href)
      : new URL("./gnugo-worker.js", import.meta.url);
    if (options.seed !== undefined) base.searchParams.set("seed", String(options.seed >>> 0));
    const worker = new Worker(base);
    return new Promise((resolve, reject) => {
      const onMessage = (ev) => {
        if (ev.data && ev.data.type === "ready") {
          worker.removeEventListener("message", onMessage);
          resolve(new GnuGo(worker));
        } else if (ev.data && ev.data.type === "error") {
          worker.removeEventListener("message", onMessage);
          worker.terminate();
          reject(new Error(ev.data.message));
        }
      };
      worker.addEventListener("message", onMessage);
      worker.addEventListener("error", (e) => reject(e.error || new Error(e.message)), { once: true });
    });
  }

  constructor(worker) {
    this._worker = worker;
    this._nextId = 1;
    this._waiting = new Map();
    worker.addEventListener("message", (ev) => {
      const { id, response } = ev.data || {};
      const entry = this._waiting.get(id);
      if (!entry) return;
      this._waiting.delete(id);
      entry.resolve(response);
    });
  }

  /** Send a raw GTP line; resolves with the full raw response text. */
  raw(cmd) {
    if (!this._worker) return Promise.reject(new Error("GnuGo engine terminated"));
    const id = this._nextId++;
    return new Promise((resolve, reject) => {
      this._waiting.set(id, { resolve, reject });
      this._worker.postMessage({ id, cmd });
    });
  }

  /** Send a GTP command; resolves with the response body, rejects with GtpError on failure. */
  async command(cmd) {
    const text = await this.raw(cmd);
    const ok = text.startsWith("=");
    // Strip "=" / "?" status (and optional id), and the trailing blank line.
    const body = text.replace(/^[=?]\d*\s?/, "").replace(/\s+$/, "");
    if (!ok) throw new GtpError(cmd, body);
    return body;
  }

  /* ---- Convenience helpers ---- */

  version() { return this.command("version"); }
  boardsize(n) { return this.command(`boardsize ${n | 0}`); }
  clearBoard() { return this.command("clear_board"); }
  komi(k) { return this.command(`komi ${Number(k)}`); }
  /** Strength 0..10 (default 10). Lower is faster and weaker. */
  level(n) { return this.command(`level ${n | 0}`); }
  fixedHandicap(n) { return this.command(`fixed_handicap ${n | 0}`).then(splitVertices); }
  play(color, vertex) { return this.command(`play ${color} ${vertex}`); }
  /** Returns e.g. "D4", "PASS" or "resign". */
  genmove(color) { return this.command(`genmove ${color}`); }
  undo() { return this.command("undo"); }
  finalScore() { return this.command("final_score"); }
  showboard() { return this.command("showboard"); }
  listStones(color) { return this.command(`list_stones ${color}`).then(splitVertices); }
  captures(color) { return this.command(`captures ${color}`).then(Number); }
  /** Stones GNU Go considers dead at the end of the game. */
  deadStones() { return this.command("final_status_list dead").then(splitVertices); }
  isLegal(color, vertex) { return this.command(`is_legal ${color} ${vertex}`).then((s) => s === "1"); }
  /** Best move suggestions with values: [{ vertex, value }]. */
  topMoves(color) {
    return this.command(`top_moves_${color[0].toLowerCase() === "b" ? "black" : "white"}`).then((s) => {
      const t = splitVertices(s), out = [];
      for (let i = 0; i + 1 < t.length; i += 2) out.push({ vertex: t[i], value: Number(t[i + 1]) });
      return out;
    });
  }

  /** Stop the worker. Pending commands are rejected. */
  terminate() {
    if (!this._worker) return;
    this._worker.terminate();
    this._worker = null;
    for (const { reject } of this._waiting.values()) reject(new Error("GnuGo engine terminated"));
    this._waiting.clear();
  }
}

function splitVertices(s) {
  return s.split(/\s+/).filter(Boolean);
}

/* Coordinate helpers: GTP letters skip "I". (x, y) are 0-based from the top-left. */
const LETTERS = "ABCDEFGHJKLMNOPQRSTUVWXYZ";
export function toVertex(x, y, size) {
  return `${LETTERS[x]}${size - y}`;
}
export function fromVertex(v, size) {
  const m = /^([A-HJ-Z])(\d+)$/i.exec(v);
  if (!m) return null;
  return { x: LETTERS.indexOf(m[1].toUpperCase()), y: size - Number(m[2]) };
}

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
 *
 * Long searches can be stopped with cancel(): the worker is replaced by
 * a fresh one and the game state is rebuilt by replaying the commands
 * that changed it, so the position is kept and the cancelled command
 * rejects with a GtpError whose `cancelled` property is true.
 */

export class GtpError extends Error {
  constructor(command, message, { cancelled = false } = {}) {
    super(`${command}: ${message}`);
    this.name = "GtpError";
    this.command = command;
    this.gtpMessage = message;
    this.cancelled = cancelled;
  }
}

/* Commands whose effect must be replayed to rebuild the engine state. */
const STATE_COMMANDS = new Set([
  "boardsize", "clear_board", "komi", "level", "play", "undo", "gg-undo",
  "fixed_handicap", "place_free_handicap", "set_free_handicap",
  "time_settings", "orientation", "random_seed",
]);

function spawn(url) {
  const worker = new Worker(url);
  return new Promise((resolve, reject) => {
    const onMessage = (ev) => {
      if (ev.data && ev.data.type === "ready") {
        cleanup();
        resolve(worker);
      } else if (ev.data && ev.data.type === "error") {
        cleanup();
        worker.terminate();
        reject(new Error(ev.data.message));
      }
    };
    const onError = (e) => {
      cleanup();
      worker.terminate();
      reject(e.error || new Error(e.message || "worker failed to load"));
    };
    const cleanup = () => {
      worker.removeEventListener("message", onMessage);
      worker.removeEventListener("error", onError);
    };
    worker.addEventListener("message", onMessage);
    worker.addEventListener("error", onError);
  });
}

export class GnuGo {
  /**
   * @param {object} [options]
   * @param {string|URL} [options.workerUrl] URL of gnugo-worker.js
   * @param {number} [options.seed] random seed (unsigned int)
   */
  static async create(options = {}) {
    const url = options.workerUrl
      ? new URL(options.workerUrl, location.href)
      : new URL("./gnugo-worker.js", import.meta.url);
    if (options.seed !== undefined) url.searchParams.set("seed", String(options.seed >>> 0));
    const worker = await spawn(url);
    return new GnuGo(worker, url);
  }

  constructor(worker, url) {
    this._url = url;
    this._nextId = 1;
    this._waiting = new Map();
    this._history = [];        // state-changing commands, for replay after cancel()
    this._ready = Promise.resolve();
    this._attach(worker);
  }

  _attach(worker) {
    this._worker = worker;
    worker.addEventListener("message", (ev) => {
      const { id, response } = ev.data || {};
      const entry = this._waiting.get(id);
      if (!entry) return;
      this._waiting.delete(id);
      entry.resolve(response);
    });
  }

  _send(cmd) {
    const id = this._nextId++;
    return new Promise((resolve, reject) => {
      this._waiting.set(id, { resolve, reject, cmd });
      this._worker.postMessage({ id, cmd });
    });
  }

  /** Send a raw GTP line; resolves with the full raw response text. */
  async raw(cmd) {
    await this._ready;
    if (!this._worker) throw new Error("GnuGo engine terminated");
    const text = await this._send(cmd);
    if (text.startsWith("=")) this._record(cmd, text);
    return text;
  }

  _record(cmd, text) {
    const parts = cmd.trim().replace(/^\d+\s+/, "").split(/\s+/);
    const name = parts[0];
    if (name === "genmove") {
      // Replay the engine's chosen move as a plain play command.
      const move = text.replace(/^=\d*\s?/, "").trim();
      if (move && move.toLowerCase() !== "resign") this._history.push(`play ${parts[1]} ${move}`);
    } else if (name === "fixed_handicap" || name === "place_free_handicap") {
      // Replay the actual stones so the result does not depend on the engine's choice.
      const stones = text.replace(/^=\d*\s?/, "").trim();
      if (stones) this._history.push(`set_free_handicap ${stones}`);
    } else if (name === "clear_board") {
      this._history = this._history.filter((c) => !/^(play|undo|gg-undo|set_free_handicap)\b/.test(c));
      this._history.push(cmd);
    } else if (STATE_COMMANDS.has(name)) {
      this._history.push(cmd);
    }
  }

  /** Send a GTP command; resolves with the response body, rejects with GtpError on failure. */
  async command(cmd) {
    const text = await this.raw(cmd);
    const ok = text.startsWith("=");
    // Strip "=" / "?" status (and optional id), and the trailing blank line.
    const body = text.replace(/^[=?]\d*[ \t]*/, "").replace(/\s+$/, "");
    if (!ok) throw new GtpError(cmd, body);
    return body;
  }

  /** True while a command is being processed by the engine. */
  get busy() {
    return this._waiting.size > 0;
  }

  /**
   * Abort the command(s) in progress (typically a long genmove). Pending
   * promises reject with GtpError { cancelled: true }. The board, komi,
   * level and time settings are restored in a fresh worker. Resolves when
   * the engine accepts commands again.
   */
  cancel() {
    if (!this._worker) return Promise.reject(new Error("GnuGo engine terminated"));
    if (this._waiting.size === 0) return this._ready;
    this._worker.terminate();
    this._worker = null;
    for (const { reject, cmd } of this._waiting.values())
      reject(new GtpError(cmd, "cancelled", { cancelled: true }));
    this._waiting.clear();

    const history = this._history.slice();
    this._ready = (async () => {
      const worker = await spawn(this._url);
      this._attach(worker);
      for (const cmd of history) await this._send(cmd);
    })();
    return this._ready;
  }

  /* ---- Convenience helpers ---- */

  version() { return this.command("version"); }
  boardsize(n) { return this.command(`boardsize ${n | 0}`); }
  clearBoard() { return this.command("clear_board"); }
  komi(k) { return this.command(`komi ${Number(k)}`); }
  /** Strength 0..10 (default 10). Lower is faster and weaker. */
  level(n) { return this.command(`level ${n | 0}`); }
  /**
   * Soft time budget per move in seconds (0 = no limit). GNU Go lowers its
   * level when moves take longer than the budget and raises it again when
   * there is time to spare. Use cancel() for a hard stop.
   */
  timePerMove(seconds) {
    const s = Math.max(0, Math.round(seconds));
    // Canadian byo-yomi of 4 stones per 4*s seconds: GNU Go's level
    // adjustment then aims at roughly half the budget per move, leaving
    // headroom for slow positions. "0 1 0" means no time limit in GTP.
    return this.command(s > 0 ? `time_settings 0 ${4 * s} 4` : "time_settings 0 1 0");
  }
  fixedHandicap(n) { return this.command(`fixed_handicap ${n | 0}`).then(splitVertices); }
  play(color, vertex) { return this.command(`play ${color} ${vertex}`); }
  /** Returns e.g. "D4", "PASS" or "resign". */
  genmove(color) { return this.command(`genmove ${color}`); }
  undo() { return this.command("undo"); }
  finalScore() { return this.command("final_score"); }
  /** Quick score estimate, e.g. "W+4.5 (upper bound: -2.5, lower: -6.5)". */
  estimateScore() { return this.command("estimate_score"); }
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
    for (const { reject, cmd } of this._waiting.values())
      reject(new GtpError(cmd, "terminated", { cancelled: true }));
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

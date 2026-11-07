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
  "time_settings", "orientation", "random_seed", "loadsgf",
]);

function spawn(url) {
  const worker = new Worker(url, { type: "module" });
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
    // Game record for toSgf(): setup stones plus the moves in order.
    this._game = { size: 19, komi: null, handicap: 0, setup: { B: [], W: [] }, moves: [] };
    this._ready = Promise.resolve();
    this._attach(worker);
  }

  _attach(worker) {
    this._worker = worker;
    worker.addEventListener("message", (ev) => {
      const msg = ev.data || {};
      const entry = this._waiting.get(msg.id);
      if (!entry) return;
      this._waiting.delete(msg.id);
      if (msg.error !== undefined) entry.reject(new Error(msg.error));
      else entry.resolve(msg);
    });
  }

  /* Send a message ({ cmd } or a file operation) and resolve with the reply. */
  _post(msg) {
    const id = this._nextId++;
    return new Promise((resolve, reject) => {
      this._waiting.set(id, { resolve, reject, cmd: msg.cmd ?? msg.writeFile ?? msg.readFile });
      this._worker.postMessage({ id, ...msg });
    });
  }

  /* Replay one history entry: a GTP command string or a file write. */
  _replay(entry) {
    return typeof entry === "string" ? this._post({ cmd: entry }) : this._post(entry);
  }

  /** Send a raw GTP line; resolves with the full raw response text. */
  async raw(cmd) {
    await this._ready;
    if (!this._worker) throw new Error("GnuGo engine terminated");
    const { response } = await this._post({ cmd });
    if (response.startsWith("=")) this._record(cmd, response);
    return response;
  }

  /** Write a text file into the engine's in-memory file system. */
  async writeFile(path, data) {
    await this._ready;
    if (!this._worker) throw new Error("GnuGo engine terminated");
    await this._post({ writeFile: path, data: String(data) });
    this._history.push({ writeFile: path, data: String(data) });
  }

  /** Read a text file from the engine's in-memory file system. */
  async readFile(path) {
    await this._ready;
    if (!this._worker) throw new Error("GnuGo engine terminated");
    return (await this._post({ readFile: path })).data;
  }

  _record(cmd, text) {
    const parts = cmd.trim().replace(/^\d+\s+/, "").split(/\s+/);
    const name = parts[0];
    this._track(name, parts, text.replace(/^=\d*[ \t]*/, "").trim());
    if (name === "genmove") {
      // Replay the engine's chosen move as a plain play command.
      const move = text.replace(/^=\d*\s?/, "").trim();
      if (move && move.toLowerCase() !== "resign") this._history.push(`play ${parts[1]} ${move}`);
    } else if (name === "fixed_handicap" || name === "place_free_handicap") {
      // Replay the actual stones so the result does not depend on the engine's choice.
      const stones = text.replace(/^=\d*\s?/, "").trim();
      if (stones) this._history.push(`set_free_handicap ${stones}`);
    } else if (name === "clear_board") {
      this._history = this._history.filter(
        (c) => typeof c !== "string" || !/^(play|undo|gg-undo|set_free_handicap|loadsgf)\b/.test(c));
      this._history.push(cmd);
    } else if (STATE_COMMANDS.has(name)) {
      this._history.push(cmd);
    }
  }

  /* Keep the game record used by toSgf() in step with a successful command. */
  _track(name, parts, body) {
    const g = this._game;
    const color = (c) => (c && c[0].toLowerCase() === "w" ? "W" : "B");
    switch (name) {
      case "boardsize":
        g.size = Number(parts[1]);
        // fall through: a new board size also clears the board
      case "clear_board":
        g.handicap = 0; g.setup = { B: [], W: [] }; g.moves = [];
        break;
      case "komi":
        g.komi = Number(parts[1]);
        break;
      case "play":
        g.moves.push({ color: color(parts[1]), vertex: parts[2].toUpperCase() });
        break;
      case "genmove":
        if (body.toLowerCase() !== "resign") g.moves.push({ color: color(parts[1]), vertex: body.toUpperCase() });
        break;
      case "undo":
      case "gg-undo":
        for (let n = name === "undo" ? 1 : Number(parts[1] || 1); n > 0; n--) g.moves.pop();
        break;
      case "fixed_handicap":
      case "place_free_handicap":
      case "set_free_handicap": {
        const stones = name === "set_free_handicap" ? parts.slice(1) : body.split(/\s+/).filter(Boolean);
        g.setup.B = stones.map((s) => s.toUpperCase());
        g.handicap = stones.length;
        break;
      }
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
      for (const entry of history) await this._replay(entry);
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

  /**
   * Load a game from SGF text. Plays the main line to the end, or stops
   * before `until`: a move number (42 plays moves 1..41) or the vertex of
   * the first move not to play (e.g. "D4"). Board
   * size, komi and handicap come from the SGF. Resolves with the color to
   * move: "black" or "white".
   */
  async loadSgf(text, until) {
    await this.writeFile("/game.sgf", text);
    const arg = until === undefined || until === null ? "" : ` ${until}`;
    const toMove = await this.command(`loadsgf /game.sgf${arg}`);
    // The loaded position becomes the setup of the game record; moves
    // played from here on are recorded as moves.
    const snap = parseSgfRoot(await this.positionSgf(), this._game.size);
    this._game = { ...snap, moves: [], toMove: toMove[0] === "w" ? "W" : "B" };
    return toMove;
  }

  /**
   * A copy of the game record: { size, komi, handicap, setup: { B, W },
   * moves: [{ color: "B"|"W", vertex }], toMove? }. Vertices are GTP
   * coordinates ("D4", "PASS"). Useful for saving and restoring games.
   */
  gameRecord() {
    return JSON.parse(JSON.stringify(this._game));
  }

  /**
   * The game as SGF text: board size, komi, handicap/setup stones and
   * every move in order (undone moves are dropped). After loadSgf(), the
   * loaded position is written as setup stones.
   */
  toSgf() {
    const g = this._game;
    const pt = (v) => sgfPoint(v, g.size);
    let s = `(;GM[1]FF[4]CA[UTF-8]AP[GNU Go:3.8]SZ[${g.size}]`;
    if (g.komi !== null) s += `KM[${g.komi}]`;
    if (g.handicap) s += `HA[${g.handicap}]`;
    if (g.setup.B.length) s += "AB" + g.setup.B.map((v) => `[${pt(v)}]`).join("");
    if (g.setup.W.length) s += "AW" + g.setup.W.map((v) => `[${pt(v)}]`).join("");
    if (g.toMove && (g.setup.B.length || g.setup.W.length)) s += `PL[${g.toMove}]`;
    s += "\n";
    g.moves.forEach((m, i) => {
      s += `;${m.color}[${pt(m.vertex)}]` + ((i + 1) % 10 === 0 ? "\n" : "");
    });
    return Promise.resolve(s.replace(/\n?$/, ")\n"));
  }

  /** The current position only (setup stones, no move order), as written by GNU Go's printsgf. */
  async positionSgf() {
    await this.command("printsgf /position.sgf");
    return this.readFile("/position.sgf");
  }
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

/* SGF point ("dd") for a GTP vertex ("D16"); "" for a pass. */
function sgfPoint(vertex, size) {
  const p = fromVertex(vertex, size);
  if (!p) return "";
  return String.fromCharCode(97 + p.x) + String.fromCharCode(97 + p.y);
}

/* GTP vertex for an SGF point. */
function fromSgfPoint(pt, size) {
  if (!pt || pt.length < 2) return null;
  return toVertex(pt.charCodeAt(0) - 97, pt.charCodeAt(1) - 97, size);
}

/* Read size, komi, handicap and setup stones from a root node such as
 * the one GNU Go's printsgf writes. */
function parseSgfRoot(text, fallbackSize) {
  const one = (id) => (new RegExp(`\\b${id}\\[([^\\]]*)\\]`).exec(text) || [])[1];
  const many = (id) => {
    const m = new RegExp(`\\b${id}((?:\\s*\\[[^\\]]*\\])+)`).exec(text);
    return m ? [...m[1].matchAll(/\[([^\]]*)\]/g)].map((x) => x[1]) : [];
  };
  const size = Number(one("SZ")) || fallbackSize;
  const komi = one("KM");
  return {
    size,
    komi: komi === undefined ? null : Number(komi),
    handicap: Number(one("HA")) || 0,
    setup: {
      B: many("AB").map((p) => fromSgfPoint(p, size)).filter(Boolean),
      W: many("AW").map((p) => fromSgfPoint(p, size)).filter(Boolean),
    },
  };
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

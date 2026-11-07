/* Type definitions for the GNU Go WebAssembly API (gnugo.js). */

export type Color = "black" | "white" | "b" | "w" | "B" | "W";

/** A GTP vertex such as "D4", or "PASS". */
export type Vertex = string;

export interface CreateOptions {
  /** URL of gnugo-worker.js. Defaults to the file next to gnugo.js. */
  workerUrl?: string | URL;
  /** Random seed (unsigned 32-bit). Defaults to a random value. */
  seed?: number;
}

export interface MoveSuggestion {
  vertex: Vertex;
  value: number;
}

export interface GameMove {
  color: "B" | "W";
  vertex: Vertex;
}

export interface GameRecord {
  size: number;
  komi: number | null;
  handicap: number;
  setup: { B: Vertex[]; W: Vertex[] };
  moves: GameMove[];
  /** Side to move in a loaded SGF position. */
  toMove?: "B" | "W";
}

/** Rejection for a failed GTP command ("? ..." response) or a cancelled one. */
export class GtpError extends Error {
  readonly command: string;
  readonly gtpMessage: string;
  /** True when the command was stopped by cancel() or terminate(). */
  readonly cancelled: boolean;
}

export class GnuGo {
  /** Start the engine in a Web Worker. Resolves once it accepts commands. */
  static create(options?: CreateOptions): Promise<GnuGo>;

  /** True while a command is being processed. */
  readonly busy: boolean;

  /** Send any GTP command; resolves with the response body. */
  command(cmd: string): Promise<string>;
  /** Send a GTP line; resolves with the raw response ("= ...\n\n" or "? ...\n\n"). */
  raw(cmd: string): Promise<string>;

  /** Stop the running command; the game state is restored in a fresh worker. */
  cancel(): Promise<void>;
  /** Stop the worker for good. */
  terminate(): void;

  version(): Promise<string>;
  boardsize(n: number): Promise<string>;
  clearBoard(): Promise<string>;
  komi(k: number | string): Promise<string>;
  /** Strength 0..10 (default 10). */
  level(n: number | string): Promise<string>;
  /** Soft time budget per move in seconds; 0 = no limit. */
  timePerMove(seconds: number): Promise<string>;
  fixedHandicap(n: number): Promise<Vertex[]>;
  play(color: Color, vertex: Vertex): Promise<string>;
  /** The engine's move: a vertex, "PASS" or "resign". */
  genmove(color: Color): Promise<string>;
  undo(): Promise<string>;
  finalScore(): Promise<string>;
  estimateScore(): Promise<string>;
  showboard(): Promise<string>;
  listStones(color: Color): Promise<Vertex[]>;
  captures(color: Color): Promise<number>;
  deadStones(): Promise<Vertex[]>;
  isLegal(color: Color, vertex: Vertex): Promise<boolean>;
  topMoves(color: Color): Promise<MoveSuggestion[]>;

  /**
   * Load a game from SGF text, stopping before `until` (move number or
   * vertex) if given. Resolves with the color to move.
   */
  loadSgf(text: string, until?: number | Vertex): Promise<"black" | "white">;
  /** The game (setup and moves in order) as SGF text. */
  toSgf(): Promise<string>;
  /** The current position only, as written by GNU Go's printsgf. */
  positionSgf(): Promise<string>;
  /** A copy of the game record, e.g. to save and restore a game. */
  gameRecord(): GameRecord;

  /** Write/read files in the engine's in-memory file system. */
  writeFile(path: string, data: string): Promise<void>;
  readFile(path: string): Promise<string>;
}

/** GTP vertex for 0-based board coordinates (x from the left, y from the top). */
export function toVertex(x: number, y: number, size: number): Vertex;
/** Board coordinates for a GTP vertex, or null for a pass/invalid vertex. */
export function fromVertex(vertex: Vertex, size: number): { x: number; y: number } | null;

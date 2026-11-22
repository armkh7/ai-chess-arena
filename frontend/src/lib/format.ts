import type { Color, GameStatus, ModelInfo, MoveLabel } from "./types";

/** "openai/gpt-oss-120b" -> provider "openai", name "gpt-oss-120b". */
export function modelParts(id: string) {
  const [first, ...rest] = id.split("/");
  const name = (rest.length ? rest.join("/") : first).replace(/:free$/, "");
  return { provider: rest.length ? first : "", name, free: id.endsWith(":free") };
}

export const colorName = (color: Color) => (color === "white" ? "White" : "Black");

// Forced mates are stored as ±(100000 - moves to mate), like the backend.
const MATE = 100_000;
export const isMate = (cp: number) => Math.abs(cp) > MATE - 1000;

/** +1.3, -0.4, M3 (White mates in 3), -M2 (Black mates in 2). */
export function formatEval(cp: number): string {
  if (isMate(cp)) return `${cp > 0 ? "" : "-"}M${MATE - Math.abs(cp)}`;
  const pawns = cp / 100;
  return `${pawns > 0 ? "+" : ""}${pawns.toFixed(1)}`;
}

/** White's winning chance in %, the same curve Lichess and the backend use. */
export function whiteWinPercent(cp: number): number {
  if (isMate(cp)) return cp > 0 ? 100 : 0;
  const capped = Math.max(-1000, Math.min(1000, cp));
  return 50 + 50 * (2 / (1 + Math.exp(-0.00368208 * capped)) - 1);
}

/**
 * Rough cost of one player's side of a game. The 2026-11-22 benchmark averaged ~470 prompt
 * tokens a move (more as the move list grows) and 50-1,700 reply tokens depending on the model.
 */
export function costPerGame(model: ModelInfo, moves: number): number {
  return moves * (550 * model.prompt_price + 800 * model.completion_price);
}

export function formatCost(usd: number): string {
  if (usd === 0) return "Free";
  if (usd < 0.001) return "<$0.001";
  return `$${usd.toFixed(usd < 0.1 ? 3 : 2)}`;
}

export const LABELS: Record<MoveLabel, { text: string; glyph: string; className: string }> = {
  best: { text: "Best move", glyph: "★", className: "text-emerald-400" },
  good: { text: "Good", glyph: "", className: "text-zinc-300" },
  inaccuracy: { text: "Inaccuracy", glyph: "?!", className: "text-yellow-400" },
  mistake: { text: "Mistake", glyph: "?", className: "text-orange-400" },
  blunder: { text: "Blunder", glyph: "??", className: "text-red-400" },
};

export const STATUS_TEXT: Record<GameStatus, string> = {
  queued: "Waiting for a free slot",
  running: "Playing",
  analyzing: "Stockfish is reviewing the game",
  judging: "The judge agent is reviewing the game",
  finished: "Finished",
  error: "Crashed",
  interrupted: "Interrupted (server restarted)",
};

/** Why the game ended, in plain words. */
export function endingText(termination: string | null, winner: Color | null): string {
  const loser = winner ? colorName(winner === "white" ? "black" : "white") : "A player";
  switch (termination) {
    case "checkmate":
      return "Checkmate";
    case "stalemate":
      return "Stalemate";
    case "insufficient_material":
      return "Draw: not enough pieces left to mate";
    case "threefold_repetition":
    case "fivefold_repetition":
      return "Draw by repetition";
    case "fifty_moves":
    case "seventyfive_moves":
      return "Draw: 50 moves without a capture or pawn move";
    case "move_limit":
      return "Move limit reached: position about equal, draw";
    case "adjudication":
      return "Move limit reached: Stockfish judged the position won";
    case "forfeit_illegal_moves":
      return `${loser} forfeited: too many illegal moves`;
    case "timeout":
      return `${loser} lost on time`;
    case "api_error":
      return "Stopped: the model provider failed";
    default:
      return "";
  }
}

/** "1-0" -> "White won", "1/2-1/2" -> "Draw", "*" -> "No result". */
export function resultText(result: string): string {
  if (result === "1-0") return "White won";
  if (result === "0-1") return "Black won";
  if (result === "1/2-1/2") return "Draw";
  return "No result";
}

export function formatSeconds(ms: number): string {
  return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)} s`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// The backend's JSON shapes (see backend/app/game/models.py and backend/app/api/schemas.py).
// The API strips every cost field (costs are for the site owner), so none appear here.

export type Color = "white" | "black";
export type ReasoningEffort = "low" | "medium" | "high";
export type MoveLabel = "best" | "good" | "inaccuracy" | "mistake" | "blunder";
export type GameStatus =
  "queued" | "running" | "analyzing" | "judging" | "finished" | "error" | "interrupted";

/** Whether visitors can start games (paused when the arena's AI credit runs low). */
export interface ArenaStatus {
  games_paused: boolean;
}

export interface ModelInfo {
  id: string;
  name: string;
  context_length: number | null;
  is_free: boolean;
}

export interface Attempt {
  raw_reply: string;
  move_text: string | null;
  reasoning: string | null;
  error: string | null; // why it was rejected; null if accepted
  latency_ms: number;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  finish_reason: string | null;
  timed_out: boolean;
}

export interface MoveRecord {
  ply: number; // half-move index, starting at 1
  move_number: number;
  color: Color;
  san: string;
  uci: string;
  fen_before: string;
  fen_after: string;
  reasoning: string | null;
  attempts: Attempt[];
}

// Evaluations are centipawns from White's point of view; forced mates are ±(100000 - moves).
export interface MoveAnalysis {
  ply: number;
  color: Color;
  eval_before: number;
  eval_after: number;
  best_san: string | null;
  best_uci: string | null;
  cp_loss: number;
  win_before: number;
  win_after: number;
  accuracy: number;
  label: MoveLabel;
}

export interface PlayerAnalysis {
  accuracy: number | null;
  acpl: number;
  counts: Partial<Record<MoveLabel, number>>;
}

export interface GameAnalysis {
  engine: string;
  depth: number;
  final_eval: number;
  white: PlayerAnalysis;
  black: PlayerAnalysis;
  moves: MoveAnalysis[];
}

// The judge agent (backend/app/judge): its visible steps and its report.

export type Grade = "A" | "B" | "C" | "D" | "F";

export interface JudgeStep {
  kind: "thinking" | "tool";
  text: string; // the model's thinking, or the purpose it gave for the tool call
  tool: string | null;
  title: string | null; // e.g. "Move 7... Qe4+"
}

export interface KeyMoment {
  ply: number;
  title: string;
  what_happened: string;
  reasoning_check: string;
  reasoning_matched: boolean;
}

export interface PlayerVerdict {
  strengths: string;
  weaknesses: string;
  reasoning_quality: string;
  grade: Grade;
}

export interface JudgeReport {
  headline: string;
  summary: string;
  key_moments: KeyMoment[];
  white: PlayerVerdict;
  black: PlayerVerdict;
}

export interface JudgeResult {
  model: string;
  steps: JudgeStep[];
  report: JudgeReport | null;
  error: string | null;
  input_tokens: number;
  output_tokens: number;
  seconds: number;
}

export interface GameRecord {
  id: string;
  white_model: string;
  black_model: string;
  show_legal_moves: boolean;
  max_full_moves: number;
  reasoning_effort: string | null;
  move_time_limit: number | null;
  started_at: string;
  finished_at: string | null;
  result: string; // "1-0", "0-1", "1/2-1/2" or "*"
  termination: string | null;
  winner: Color | null;
  error: string | null;
  moves: MoveRecord[];
  failed_attempts: Attempt[];
  failed_color: Color | null;
  analysis: GameAnalysis | null;
  judge: JudgeResult | null;
  pgn: string;
}

export interface GameDetail {
  status: GameStatus;
  error: string | null;
  game: GameRecord;
}

export interface GameSummary {
  id: string;
  status: GameStatus;
  white_model: string;
  black_model: string;
  result: string;
  termination: string | null;
  winner: Color | null;
  moves: number;
  white_accuracy: number | null;
  black_accuracy: number | null;
  created_at: string;
  finished_at: string | null;
}

export interface GamePage {
  games: GameSummary[];
  total: number;
}

export interface NewGameRequest {
  white: string;
  black: string;
  max_moves?: number;
  reasoning_effort?: ReasoningEffort;
}

export interface GameCreated {
  id: string;
  status: GameStatus;
  stream_url: string;
}

// Live stream events (GET /games/{id}/stream)

export interface GameInfo {
  id: string;
  status: GameStatus;
  white_model: string;
  black_model: string;
  max_moves: number;
  show_legal_moves: boolean;
  reasoning_effort: string | null;
  move_time_limit: number | null;
}

export interface GameEnd {
  status: GameStatus;
  result: string;
  termination: string | null;
  winner: Color | null;
  error: string | null;
  // The final turn's failed tries (a forfeit or API error), so the page needs only the stream.
  failed_color: Color | null;
  failed_attempts: Attempt[];
}

/** Sent with the "analyzing" / "judging" status: the game is over, the review isn't. */
export interface GameOutcome {
  result: string;
  termination: string;
  winner: Color | null;
}

// GET /leaderboard (backend/app/leaderboard.py)
export interface LeaderboardRow {
  rank: number;
  model: string;
  rating: number;
  games: number;
  wins: number;
  draws: number;
  losses: number;
  accuracy: number | null; // average Stockfish accuracy, %
  grade: string | null; // average judge grade, A-F
  honest: number | null; // % of judged key moments where its explanation matched the move
  provisional: boolean; // fewer than 5 games
}

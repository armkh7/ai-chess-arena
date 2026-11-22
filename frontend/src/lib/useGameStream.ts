"use client";

// Follows one game over Server-Sent Events. The server first sends everything so far, then
// each new event, so the same code shows a live game and replays a finished one.

import { useEffect, useReducer } from "react";
import { api } from "./api";
import type {
  Attempt,
  Color,
  GameAnalysis,
  GameEnd,
  GameInfo,
  GameOutcome,
  GameStatus,
  JudgeResult,
  JudgeStep,
  MoveRecord,
} from "./types";

export interface Waiting {
  seconds: number;
  retry: number;
}

export interface GameState {
  connection: "connecting" | "open" | "failed";
  info: GameInfo | null;
  status: GameStatus | null;
  moves: MoveRecord[];
  // The side to move: its rejected tries this turn, a rate-limit wait, when its turn began.
  rejected: Attempt[];
  waiting: Waiting | null;
  turnStartedAt: number | null;
  analysis: GameAnalysis | null;
  outcome: GameOutcome | null; // the result, as soon as the game is over
  judgeSteps: JudgeStep[]; // the judge agent's steps so far
  judge: JudgeResult | null; // its final result
  end: GameEnd | null;
}

type Action =
  | { type: "open" }
  | { type: "failed" }
  | { type: "game"; data: GameInfo; at: number }
  | { type: "status"; data: { status: GameStatus } & Partial<GameOutcome>; at: number }
  | { type: "move"; data: MoveRecord; at: number }
  | { type: "rejected"; data: { color: Color; attempt: Attempt }; at: number }
  | { type: "rate_limited"; data: Waiting & { model: string }; at: number }
  | { type: "analysis"; data: GameAnalysis; at: number }
  | { type: "judge_step"; data: JudgeStep; at: number }
  | { type: "judge"; data: JudgeResult; at: number }
  | { type: "end"; data: GameEnd; at: number };

const initial: GameState = {
  connection: "connecting",
  info: null,
  status: null,
  moves: [],
  rejected: [],
  waiting: null,
  turnStartedAt: null,
  analysis: null,
  outcome: null,
  judgeSteps: [],
  judge: null,
  end: null,
};

function reducer(state: GameState, action: Action): GameState {
  switch (action.type) {
    case "open":
      return { ...state, connection: "open" };
    case "failed":
      return { ...state, connection: "failed" };
    case "game": // the first event; after a reconnect the history comes again, so start over
      return { ...initial, connection: "open", info: action.data, status: action.data.status };
    case "status": {
      const { status, result, termination, winner } = action.data;
      return {
        ...state,
        status,
        turnStartedAt: status === "running" ? action.at : state.turnStartedAt,
        outcome:
          result && termination ? { result, termination, winner: winner ?? null } : state.outcome,
      };
    }
    case "move":
      return {
        ...state,
        moves: [...state.moves, action.data],
        rejected: [],
        waiting: null,
        turnStartedAt: action.at,
      };
    case "rejected":
      return { ...state, rejected: [...state.rejected, action.data.attempt], waiting: null };
    case "rate_limited":
      return { ...state, waiting: { seconds: action.data.seconds, retry: action.data.retry } };
    case "analysis":
      return { ...state, analysis: action.data };
    case "judge_step":
      return { ...state, judgeSteps: [...state.judgeSteps, action.data] };
    case "judge":
      return { ...state, judge: action.data, judgeSteps: action.data.steps };
    case "end":
      return { ...state, end: action.data, status: action.data.status, waiting: null };
  }
}

const EVENTS = [
  "game",
  "status",
  "move",
  "rejected",
  "rate_limited",
  "analysis",
  "judge_step",
  "judge",
] as const;

export function useGameStream(id: string): GameState {
  const [state, dispatch] = useReducer(reducer, initial);

  useEffect(() => {
    const source = new EventSource(api.streamUrl(id));
    source.onopen = () => dispatch({ type: "open" });
    for (const type of EVENTS) {
      source.addEventListener(type, (event) => {
        const data = JSON.parse((event as MessageEvent<string>).data);
        dispatch({ type, data, at: Date.now() } as Action);
      });
    }
    source.addEventListener("end", (event) => {
      dispatch({
        type: "end",
        data: JSON.parse((event as MessageEvent<string>).data),
        at: Date.now(),
      });
      source.close(); // otherwise the browser reconnects and replays the game
    });
    // A dropped connection reconnects by itself; CLOSED means it gave up (e.g. 404).
    source.onerror = () => {
      if (source.readyState === EventSource.CLOSED) dispatch({ type: "failed" });
    };
    return () => source.close();
  }, [id]);

  return state;
}

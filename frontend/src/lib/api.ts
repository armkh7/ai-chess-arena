// Calls to the FastAPI backend, straight from the browser.

import type {
  ArenaStatus,
  GameCreated,
  GameDetail,
  GamePage,
  LeaderboardRow,
  ModelInfo,
  NewGameRequest,
} from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init });
  } catch {
    throw new Error("Can't reach the arena server. Is it running?");
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // not JSON: keep the status text
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  models: () => request<ModelInfo[]>("/models"),
  games: (limit = 20, offset = 0) => request<GamePage>(`/games?limit=${limit}&offset=${offset}`),
  game: (id: string) => request<GameDetail>(`/games/${encodeURIComponent(id)}`),
  startGame: (body: NewGameRequest) =>
    request<GameCreated>("/games", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  streamUrl: (id: string) => `${API_URL}/games/${encodeURIComponent(id)}/stream`,
  leaderboard: () => request<LeaderboardRow[]>("/leaderboard"),
  status: () => request<ArenaStatus>("/status"),
};

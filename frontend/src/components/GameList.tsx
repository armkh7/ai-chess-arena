"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ModelName } from "@/components/ModelName";
import { api } from "@/lib/api";
import { endingText, formatDate, STATUS_TEXT } from "@/lib/format";
import type { Color, GamePage, GameStatus, GameSummary } from "@/lib/types";

const ACTIVE: GameStatus[] = ["queued", "running", "analyzing", "judging"];

/** Newest games first. Refreshes every 5 s while any of them is still going. */
export function GameList({ limit = 20 }: { limit?: number }) {
  const [page, setPage] = useState<GamePage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const next = await api.games(limit);
        if (cancelled) return;
        setPage(next);
        setError(null);
        if (next.games.some((g) => ACTIVE.includes(g.status))) timer = setTimeout(load, 5000);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    }
    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [limit]);

  if (error) return <p className="text-sm text-red-400">Couldn&apos;t load games: {error}</p>;
  if (!page) return <p className="text-sm text-zinc-500">Loading games…</p>;
  if (!page.games.length)
    return <p className="text-sm text-zinc-500">No games yet. Start one above.</p>;

  return (
    <ul className="divide-y divide-zinc-800/80 overflow-hidden rounded-xl border border-zinc-800">
      {page.games.map((game) => (
        <li key={game.id}>
          <GameRow game={game} />
        </li>
      ))}
    </ul>
  );
}

function GameRow({ game }: { game: GameSummary }) {
  const active = ACTIVE.includes(game.status);
  const ending = active ? STATUS_TEXT[game.status] : endingText(game.termination, game.winner);
  return (
    <Link
      href={`/games/${game.id}`}
      className="flex items-center gap-4 px-4 py-3 transition hover:bg-zinc-900/70"
    >
      <div className="min-w-0 flex-1 space-y-1">
        <Player color="white" model={game.white_model} accuracy={game.white_accuracy} />
        <Player color="black" model={game.black_model} accuracy={game.black_accuracy} />
        <p className="truncate text-xs text-zinc-500">
          {ending || STATUS_TEXT[game.status]} · {Math.ceil(game.moves / 2)} moves ·{" "}
          {formatDate(game.created_at)}
        </p>
      </div>
      <Result game={game} active={active} />
    </Link>
  );
}

function Player({
  color,
  model,
  accuracy,
}: {
  color: Color;
  model: string;
  accuracy: number | null;
}) {
  return (
    <div className="flex min-w-0 items-center gap-2">
      <span
        className={`size-2.5 shrink-0 rounded-full border border-zinc-500 ${color === "white" ? "bg-zinc-100" : "bg-zinc-950"}`}
      />
      <ModelName id={model} />
      {accuracy !== null && (
        <span
          className="ml-auto shrink-0 text-xs tabular-nums text-zinc-500"
          title="Stockfish accuracy"
        >
          {accuracy.toFixed(1)}%
        </span>
      )}
    </div>
  );
}

function Result({ game, active }: { game: GameSummary; active: boolean }) {
  if (active) {
    return (
      <span className="flex items-center gap-1.5 rounded-full bg-red-500/15 px-2.5 py-1 text-xs font-semibold text-red-400">
        <span className="size-1.5 animate-pulse rounded-full bg-red-400" />
        LIVE
      </span>
    );
  }
  // Each side's score in its own span: "½" glyphs crowd the dash when written as one string.
  const [white, black] =
    game.result === "1/2-1/2"
      ? ["½", "½"]
      : game.result === "*"
        ? ["*", "*"]
        : game.result.split("-");
  return (
    <span className="flex items-center gap-1.5 rounded-md bg-zinc-800 px-2.5 py-1 text-sm font-semibold tabular-nums">
      <span>{white}</span>
      <span className="text-zinc-500">–</span>
      <span>{black}</span>
    </span>
  );
}

"use client";

import {
  ArrowRight,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  Pause,
  Play,
  SkipBack,
  SkipForward,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Board } from "@/components/game/Board";
import { EvalBar } from "@/components/game/EvalBar";
import { JudgePanel } from "@/components/game/JudgePanel";
import { MoveDetails, RejectedTries, Thinking } from "@/components/game/MoveDetails";
import { MoveList } from "@/components/game/MoveList";
import { PlayerStrip } from "@/components/game/PlayerStrip";
import { colorName, endingText, resultText, STATUS_TEXT } from "@/lib/format";
import type { Color, MoveAnalysis } from "@/lib/types";
import { useGameStream } from "@/lib/useGameStream";

const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const AUTOPLAY_MS = 1000;

export function GameView({ id }: { id: string }) {
  const game = useGameStream(id);
  const [selected, setSelected] = useState<number | null>(null); // null = follow the latest move
  const [flipped, setFlipped] = useState(false);

  const total = game.moves.length;
  // While the game is on, the board always shows the latest move; replay controls come after.
  const live = game.status === "queued" || game.status === "running";
  const ply = selected === null || live ? total : Math.min(selected, total);
  const now = useNow(live ? 1000 : null);

  // Slide the pieces only for one-move steps (a live move, ← / →, Play). Opening a game and
  // jumps (⏮ ⏭, clicking a far move) show the new position at once.
  const [shown, setShown] = useState({ ply, animate: false });
  if (shown.ply !== ply) setShown({ ply, animate: Math.abs(ply - shown.ply) === 1 });
  const animate = shown.ply === ply ? shown.animate : Math.abs(ply - shown.ply) === 1;

  const go = useCallback(
    (target: number) => setSelected(target >= total ? null : Math.max(0, target)),
    [total],
  );

  // Autoplay: one move per second until the last move. Any manual step pauses it.
  const [playing, setPlaying] = useState(false);
  const autoplaying = playing && ply < total;
  useEffect(() => {
    if (!autoplaying) return;
    const timer = setTimeout(() => go(ply + 1), AUTOPLAY_MS);
    return () => clearTimeout(timer);
  }, [autoplaying, go, ply]);

  const jump = useCallback(
    (target: number) => {
      setPlaying(false);
      go(target);
    },
    [go],
  );
  const togglePlay = useCallback(() => {
    if (autoplaying) return setPlaying(false);
    if (ply >= total) go(0); // at the end: replay from the start
    setPlaying(true);
  }, [autoplaying, go, ply, total]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (live || !total || event.altKey || event.ctrlKey || event.metaKey) return;
      if (event.key === " ") {
        event.preventDefault();
        togglePlay();
        return;
      }
      const keys: Record<string, number> = {
        ArrowLeft: ply - 1,
        ArrowRight: ply + 1,
        Home: 0,
        End: total,
      };
      if (!(event.key in keys)) return;
      event.preventDefault();
      jump(keys[event.key]);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [jump, togglePlay, live, ply, total]);

  const analysis = useMemo(
    () => new Map<number, MoveAnalysis>((game.analysis?.moves ?? []).map((m) => [m.ply, m])),
    [game.analysis],
  );

  if (game.connection === "failed" && !game.info) {
    return (
      <div className="space-y-3 rounded-2xl border border-ui-800 p-6">
        <p>This game doesn&apos;t exist, or the arena server can&apos;t be reached.</p>
        <Link
          href="/"
          className="inline-flex items-center gap-1 text-sm text-accent-400 hover:underline"
        >
          Start a new game <ArrowRight className="size-4" aria-hidden />
        </Link>
      </div>
    );
  }
  if (!game.info) return <p className="text-ui-400">Loading game…</p>;

  const info = game.info;
  const move = ply > 0 ? game.moves[ply - 1] : undefined;
  const fen = move?.fen_after ?? START_FEN;
  const evaluation = game.analysis
    ? ply === 0
      ? (analysis.get(1)?.eval_before ?? 0)
      : (analysis.get(ply)?.eval_after ?? null)
    : null;

  const toMove: Color = total % 2 === 0 ? "white" : "black";
  const thinking = game.status === "running";
  const thinkingSeconds =
    thinking && now !== null && game.turnStartedAt !== null
      ? Math.max(0, Math.round((now - game.turnStartedAt) / 1000))
      : null;
  const orientation: Color = flipped ? "black" : "white";
  const [top, bottom]: Color[] = flipped ? ["white", "black"] : ["black", "white"];
  const outcome = game.end ?? game.outcome; // the result, as soon as the game is over
  const result = outcome?.result ?? null;
  const reviewing = game.status === "analyzing" || game.status === "judging";
  const showJudge = game.status === "judging" || game.judge !== null || game.judgeSteps.length > 0;
  const failed = game.end?.failed_attempts.length ? game.end : null; // a forfeit's last tries

  const strip = (color: Color) => (
    <PlayerStrip
      color={color}
      model={color === "white" ? info.white_model : info.black_model}
      score={score(result, color)}
      analysis={game.analysis ? game.analysis[color] : null}
      thinking={thinking && toMove === color}
      thinkingSeconds={thinkingSeconds}
    />
  );

  const showMove = (target: number) => {
    jump(target);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,34rem)_minmax(0,1fr)]">
        <section className="min-w-0">
          {strip(top)}
          <div className="flex gap-2">
            <EvalBar cp={evaluation} orientation={orientation} />
            <div className="min-w-0 flex-1">
              <Board fen={fen} lastMove={move?.uci} orientation={orientation} animate={animate} />
            </div>
          </div>
          {strip(bottom)}
          {live ? (
            <div className="mt-2 flex items-center">
              <FlipButton onClick={() => setFlipped((f) => !f)} />
            </div>
          ) : (
            <div className="mt-2 flex items-center gap-1">
              <NavButton label="First move" onClick={() => jump(0)} disabled={ply === 0}>
                <SkipBack className="size-4" />
              </NavButton>
              <NavButton
                label="Previous move (←)"
                onClick={() => jump(ply - 1)}
                disabled={ply === 0}
              >
                <ChevronLeft className="size-5" />
              </NavButton>
              <button
                type="button"
                onClick={togglePlay}
                disabled={total === 0}
                title={autoplaying ? "Pause (space)" : "Play the moves (space)"}
                className="mx-1 inline-flex items-center gap-1.5 whitespace-nowrap rounded-md bg-accent-400 px-4 py-1.5 text-sm font-semibold text-ui-950 transition hover:bg-accent-300 disabled:opacity-30"
              >
                {autoplaying ? (
                  <Pause className="size-4" fill="currentColor" aria-hidden />
                ) : (
                  <Play className="size-4" fill="currentColor" aria-hidden />
                )}
                {autoplaying ? "Pause" : "Play"}
              </button>
              <NavButton
                label="Next move (→)"
                onClick={() => jump(ply + 1)}
                disabled={ply >= total}
              >
                <ChevronRight className="size-5" />
              </NavButton>
              <NavButton label="Last move" onClick={() => jump(total)} disabled={ply >= total}>
                <SkipForward className="size-4" />
              </NavButton>
              <span className="ml-2 hidden whitespace-nowrap text-xs tabular-nums text-ui-400 sm:inline">
                {ply} / {total}
              </span>
              <FlipButton onClick={() => setFlipped((f) => !f)} />
            </div>
          )}
        </section>

        <aside className="flex min-w-0 flex-col gap-4">
          <div className="rounded-xl border border-ui-800 bg-ui-900/40 p-4">
            {outcome ? (
              <>
                <p className="text-lg font-semibold">{resultText(outcome.result)}</p>
                <p className="text-sm text-ui-400">
                  {game.end && game.end.status !== "finished"
                    ? STATUS_TEXT[game.end.status]
                    : endingText(outcome.termination, outcome.winner)}
                </p>
                {game.end?.error && <p className="mt-1 text-sm text-red-400">{game.end.error}</p>}
                {reviewing && game.status && (
                  <p className="mt-2 flex items-center gap-2 text-sm text-agent-300">
                    <span className="size-2 animate-pulse rounded-full bg-agent-400" />
                    {STATUS_TEXT[game.status]}…
                  </p>
                )}
              </>
            ) : (
              <p className="flex items-center gap-2 font-medium">
                {live && <span className="size-2 animate-pulse rounded-full bg-red-400" />}
                {game.status ? STATUS_TEXT[game.status] : "Connecting…"}
                {game.status === "running" && (
                  <span className="text-sm font-normal text-ui-400">
                    · move {Math.floor(total / 2) + 1}
                  </span>
                )}
              </p>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ui-400">
              {info.move_time_limit && <span>{info.move_time_limit} s per move</span>}
              {info.reasoning_effort && <span>{info.reasoning_effort} reasoning effort</span>}
              {game.analysis && (
                <span>
                  {game.analysis.engine}, depth {game.analysis.depth}
                </span>
              )}
            </div>
          </div>

          <div className="rounded-xl border border-ui-800 bg-ui-900/40">
            <MoveList
              moves={game.moves}
              analysis={analysis}
              current={ply}
              onSelect={live ? undefined : jump}
            />
          </div>

          <div className="space-y-4 rounded-xl border border-ui-800 bg-ui-900/40 p-4">
            {move ? (
              <MoveDetails move={move} analysis={analysis.get(move.ply)} />
            ) : (
              <p className="text-sm text-ui-400">
                Starting position. Press Play, use the arrow keys, or click a move.
              </p>
            )}
            {ply === total && thinking && (
              <div className="border-t border-ui-800 pt-4">
                <Thinking
                  color={toMove}
                  seconds={thinkingSeconds}
                  rejected={game.rejected}
                  waiting={game.waiting}
                />
              </div>
            )}
            {ply === total && failed?.failed_color && (
              <div className="border-t border-ui-800 pt-4">
                <RejectedTries
                  attempts={failed.failed_attempts}
                  title={`${colorName(failed.failed_color)}'s last tries`}
                />
              </div>
            )}
          </div>
        </aside>
      </div>
      {showJudge && (
        <JudgePanel
          steps={game.judgeSteps}
          judge={game.judge}
          judging={game.status === "judging"}
          models={{ white: info.white_model, black: info.black_model }}
          onShowMove={showMove}
        />
      )}
    </div>
  );
}

function NavButton(props: {
  label: string;
  onClick: () => void;
  disabled: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      title={props.label}
      aria-label={props.label}
      onClick={props.onClick}
      disabled={props.disabled}
      className="inline-flex items-center justify-center rounded-md px-2.5 py-1.5 text-ui-300 transition hover:bg-ui-800 disabled:opacity-30 disabled:hover:bg-transparent sm:px-3"
    >
      {props.children}
    </button>
  );
}

/** "Flip board" on wider screens, an icon on phones. */
function FlipButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title="Flip board"
      aria-label="Flip board"
      className="ml-auto inline-flex items-center gap-1.5 whitespace-nowrap rounded-md px-3 py-1.5 text-sm text-ui-400 transition hover:bg-ui-800 hover:text-ui-100"
    >
      <ArrowUpDown className="size-4" aria-hidden />
      <span className="hidden sm:inline">Flip board</span>
    </button>
  );
}

/** "1-0" -> White "1", Black "0". Null while the game is on or without a result. */
function score(result: string | null, color: Color): string | null {
  if (result === "1/2-1/2") return "½";
  if (result === "1-0") return color === "white" ? "1" : "0";
  if (result === "0-1") return color === "black" ? "1" : "0";
  return null;
}

/** The current time, updated every `intervalMs` (null = stopped). Null until the first tick. */
function useNow(intervalMs: number | null): number | null {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    if (intervalMs === null) return;
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}

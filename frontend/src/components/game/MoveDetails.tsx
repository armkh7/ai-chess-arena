import { Star, Timer } from "lucide-react";
import { colorName, formatEval, formatSeconds, LABELS } from "@/lib/format";
import type { Attempt, Color, MoveAnalysis, MoveRecord } from "@/lib/types";
import type { Waiting } from "@/lib/useGameStream";

/** One move: the model's reasoning, Stockfish's verdict, and any rejected tries. */
export function MoveDetails({ move, analysis }: { move: MoveRecord; analysis?: MoveAnalysis }) {
  const rejected = move.attempts.slice(0, -1);
  const accepted = move.attempts.at(-1);
  const label = analysis ? LABELS[analysis.label] : null;
  const missed =
    analysis?.best_san && ["inaccuracy", "mistake", "blunder"].includes(analysis.label);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-mono text-lg font-semibold">
          {move.move_number}
          {move.color === "white" ? "." : "..."} {move.san}
        </span>
        {label && (
          <span className={`inline-flex items-center gap-1 text-sm font-medium ${label.className}`}>
            {analysis?.label === "best" ? (
              <Star className="size-3.5" fill="currentColor" aria-hidden />
            ) : (
              label.glyph && `${label.glyph} `
            )}
            {label.text}
          </span>
        )}
        {analysis && (
          <span
            className="ml-auto font-mono text-sm text-ui-400"
            title="Stockfish evaluation after the move"
          >
            {formatEval(analysis.eval_after)}
          </span>
        )}
      </div>

      {missed && (
        <p className="text-sm text-ui-400">
          Stockfish preferred <span className="font-mono text-ui-200">{analysis.best_san}</span>.
        </p>
      )}

      {move.reasoning ? (
        <blockquote className="border-l-2 border-accent-400/60 pl-3 leading-relaxed text-ui-200">
          {move.reasoning}
        </blockquote>
      ) : (
        <p className="text-sm italic text-ui-400">No reasoning given.</p>
      )}

      {rejected.length > 0 && <RejectedTries attempts={rejected} />}

      {accepted && (
        <p className="text-xs text-ui-400">
          {colorName(move.color)} answered in {formatSeconds(accepted.latency_ms)}
          {accepted.completion_tokens !== null && ` · ${accepted.completion_tokens} tokens`}
        </p>
      )}
    </div>
  );
}

/** The side to move, while the model is working on its reply. */
export function Thinking(props: {
  color: Color;
  seconds: number | null;
  rejected: Attempt[];
  waiting: Waiting | null;
}) {
  const { color, seconds, rejected, waiting } = props;
  return (
    <div className="space-y-3">
      <p className="flex items-center gap-2 text-sm text-ui-300">
        <span className="size-2 animate-pulse rounded-full bg-accent-400" />
        {colorName(color)} is thinking{seconds !== null && ` · ${seconds} s`}
      </p>
      {waiting && (
        <p className="text-sm text-ui-400">
          The model&apos;s provider is busy: waiting {waiting.seconds} s, then trying again (retry{" "}
          {waiting.retry}).
        </p>
      )}
      {rejected.length > 0 && <RejectedTries attempts={rejected} />}
    </div>
  );
}

export function RejectedTries({
  attempts,
  title = "Rejected tries",
}: {
  attempts: Attempt[];
  title?: string;
}) {
  return (
    <div className="space-y-1.5">
      <p className="text-xs font-medium uppercase tracking-wide text-ui-400">{title}</p>
      <ul className="space-y-1 text-sm">
        {attempts.map((attempt, i) => (
          <li key={i} className="flex gap-2 text-ui-400">
            <span className="shrink-0 font-mono text-red-400">
              {attempt.timed_out ? (
                <Timer className="mt-0.5 size-4" aria-label="Too slow" />
              ) : (
                (attempt.move_text ?? "—")
              )}
            </span>
            <span className="min-w-0 break-words">{attempt.error}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

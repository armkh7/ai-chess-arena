import { ModelName } from "@/components/ModelName";
import { LABELS } from "@/lib/format";
import type { Color, MoveLabel, PlayerAnalysis } from "@/lib/types";

const SHOWN: MoveLabel[] = ["blunder", "mistake", "inaccuracy"];

/** One player above or below the board: model, result, accuracy, "thinking". */
export function PlayerStrip(props: {
  color: Color;
  model: string;
  score: string | null; // "1", "0", "½" once the game is over
  analysis: PlayerAnalysis | null;
  thinking: boolean;
  thinkingSeconds: number | null;
}) {
  const { color, model, score, analysis, thinking, thinkingSeconds } = props;
  return (
    <div className="flex min-h-11 items-center gap-3 py-1.5">
      <span
        className={`size-3.5 shrink-0 rounded-full border border-zinc-400 ${color === "white" ? "bg-white" : "bg-zinc-900"}`}
        aria-label={color}
      />
      <ModelName id={model} />
      {thinking && (
        <span className="flex shrink-0 items-center gap-1.5 text-xs text-accent-400">
          <span className="size-1.5 animate-pulse rounded-full bg-accent-400" />
          thinking{thinkingSeconds !== null && ` ${thinkingSeconds}s`}
        </span>
      )}
      <div className="ml-auto flex shrink-0 items-center gap-3 text-sm">
        {analysis && analysis.accuracy !== null && (
          <span className="flex items-center gap-2 text-ui-400">
            {SHOWN.map((label) =>
              analysis.counts[label] ? (
                <span key={label} className={LABELS[label].className} title={LABELS[label].text}>
                  {analysis.counts[label]}
                  {LABELS[label].glyph}
                </span>
              ) : null,
            )}
            <span className="font-medium text-ui-200">{analysis.accuracy.toFixed(1)}%</span>
          </span>
        )}
        {score !== null && (
          <span className="w-6 rounded bg-ui-800 text-center font-mono font-semibold">{score}</span>
        )}
      </div>
    </div>
  );
}

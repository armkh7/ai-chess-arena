import { formatEval, whiteWinPercent } from "@/lib/format";
import type { Color } from "@/lib/types";

/** Stockfish's evaluation as a bar: the white part is White's winning chance. */
export function EvalBar({ cp, orientation }: { cp: number | null; orientation: Color }) {
  const whiteOnBottom = orientation === "white";
  const white = cp === null ? 50 : whiteWinPercent(cp);
  const whiteAhead = (cp ?? 0) >= 0;
  return (
    <div
      className={`relative w-6 shrink-0 overflow-hidden rounded bg-zinc-800 ring-1 ring-zinc-600 ${cp === null ? "opacity-40" : ""}`}
      title={
        cp === null
          ? "Stockfish evaluates every move when the game ends"
          : `Stockfish evaluation: ${formatEval(cp)}`
      }
    >
      <div
        className={`absolute inset-x-0 bg-white transition-[height] duration-300 ${whiteOnBottom ? "bottom-0" : "top-0"}`}
        style={{ height: `${white}%` }}
      />
      {cp !== null && (
        <span
          className={`absolute inset-x-0 text-center text-[11px] font-semibold ${
            whiteAhead === whiteOnBottom ? "bottom-1" : "top-1"
          } ${whiteAhead ? "text-zinc-900" : "text-zinc-100"}`}
        >
          {formatEval(cp).replace("+", "")}
        </span>
      )}
    </div>
  );
}

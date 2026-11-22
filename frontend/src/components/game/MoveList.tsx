"use client";

import { useEffect, useRef } from "react";
import { LABELS } from "@/lib/format";
import type { MoveAnalysis, MoveRecord } from "@/lib/types";

/** Moves in pairs (1. e4 e5). Click one to show that position (once the game is over). */
export function MoveList(props: {
  moves: MoveRecord[];
  analysis: Map<number, MoveAnalysis>;
  current: number; // ply on the board, 0 = start
  onSelect?: (ply: number) => void; // undefined while the game is live: moves aren't clickable
}) {
  const { moves, analysis, current, onSelect } = props;
  const box = useRef<HTMLDivElement>(null);

  // Keep the current move in view without scrolling the whole page.
  useEffect(() => {
    const el = box.current?.querySelector<HTMLElement>('[data-current="true"]');
    const container = box.current;
    if (!el || !container) return;
    const top = el.offsetTop;
    if (top < container.scrollTop) container.scrollTop = top - 8;
    else if (top + el.offsetHeight > container.scrollTop + container.clientHeight)
      container.scrollTop = top + el.offsetHeight - container.clientHeight + 8;
  }, [current, moves.length]);

  if (!moves.length) {
    return <p className="p-4 text-sm text-zinc-500">No moves yet.</p>;
  }

  const rows: [MoveRecord, MoveRecord | undefined][] = [];
  for (let i = 0; i < moves.length; i += 2) rows.push([moves[i], moves[i + 1]]);

  return (
    <div ref={box} className="relative max-h-64 overflow-y-auto p-2 lg:max-h-80">
      <div className="grid grid-cols-[2.5rem_1fr_1fr] gap-y-0.5 font-mono text-sm">
        {rows.map(([white, black]) => (
          <Row
            key={white.ply}
            white={white}
            black={black}
            analysis={analysis}
            current={current}
            onSelect={onSelect}
          />
        ))}
      </div>
    </div>
  );
}

function Row(props: {
  white: MoveRecord;
  black?: MoveRecord;
  analysis: Map<number, MoveAnalysis>;
  current: number;
  onSelect?: (ply: number) => void;
}) {
  const { white, black, ...rest } = props;
  return (
    <>
      <span className="py-1 pr-2 text-right text-zinc-600">{white.move_number}.</span>
      <Cell move={white} {...rest} />
      {black ? <Cell move={black} {...rest} /> : <span />}
    </>
  );
}

function Cell({
  move,
  analysis,
  current,
  onSelect,
}: { move: MoveRecord } & Omit<Parameters<typeof Row>[0], "white" | "black">) {
  const label = analysis.get(move.ply)?.label;
  const style = label ? LABELS[label] : null;
  const active = move.ply === current;
  const retries = move.attempts.length - 1;
  return (
    <button
      type="button"
      data-current={active}
      onClick={onSelect && (() => onSelect(move.ply))}
      disabled={!onSelect}
      className={`flex items-center gap-1 rounded px-2 py-1 text-left transition ${
        active ? "bg-amber-400/20 text-zinc-50" : "text-zinc-300 enabled:hover:bg-zinc-800"
      }`}
    >
      {move.san}
      {style?.glyph && label !== "best" && <span className={style.className}>{style.glyph}</span>}
      {retries > 0 && (
        <span className="ml-auto text-[10px] text-red-400/80" title={`${retries} rejected tries`}>
          ×{retries}
        </span>
      )}
    </button>
  );
}

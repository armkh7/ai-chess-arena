"use client";

import type { CSSProperties } from "react";
import { Chessboard } from "react-chessboard";
import type { Color } from "@/lib/types";

const LAST_MOVE: CSSProperties = { backgroundColor: "rgba(250, 204, 21, 0.4)" };

/** A read-only board: the position, with the last move's squares highlighted. */
export function Board({
  fen,
  lastMove,
  orientation,
}: {
  fen: string;
  lastMove?: string;
  orientation: Color;
}) {
  const squareStyles: Record<string, CSSProperties> = {};
  if (lastMove) {
    squareStyles[lastMove.slice(0, 2)] = LAST_MOVE;
    squareStyles[lastMove.slice(2, 4)] = LAST_MOVE;
  }
  return (
    <Chessboard
      options={{
        id: "arena-board",
        position: fen,
        boardOrientation: orientation,
        allowDragging: false,
        animationDurationInMs: 200,
        squareStyles,
        darkSquareStyle: { backgroundColor: "#7c8c6b" },
        lightSquareStyle: { backgroundColor: "#e7e3d4" },
        boardStyle: { borderRadius: "6px", overflow: "hidden" },
      }}
    />
  );
}

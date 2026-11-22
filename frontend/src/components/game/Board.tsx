"use client";

import type { CSSProperties } from "react";
import { Chessboard } from "react-chessboard";
import type { Color } from "@/lib/types";

// Green board: cream and felt-green squares, the last move in soft yellow.
const LIGHT = "#ebe6d2";
const DARK = "#5e7d63";
const LAST_MOVE: CSSProperties = { backgroundColor: "rgba(250, 204, 21, 0.45)" };

/**
 * A read-only board: the position, with the last move's squares highlighted. `animate` slides
 * the pieces; GameView turns it off for jumps, which would otherwise flash through moves.
 */
export function Board({
  fen,
  lastMove,
  orientation,
  animate,
}: {
  fen: string;
  lastMove?: string;
  orientation: Color;
  animate: boolean;
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
        animationDurationInMs: animate ? 200 : 0,
        squareStyles,
        darkSquareStyle: { backgroundColor: DARK },
        lightSquareStyle: { backgroundColor: LIGHT },
        // Coordinates in the opposite square's color, like most chess sites.
        darkSquareNotationStyle: { color: LIGHT, fontWeight: 600 },
        lightSquareNotationStyle: { color: DARK, fontWeight: 600 },
        boardStyle: { borderRadius: "6px", overflow: "hidden" },
      }}
    />
  );
}

import type { Metadata } from "next";
import { Suspense } from "react";
import { GameView } from "@/components/game/GameView";

export const metadata: Metadata = { title: "Game" };

// The id is only known at request time, so it's read inside Suspense (Cache Components).
export default function GamePage({ params }: PageProps<"/games/[id]">) {
  return (
    <Suspense fallback={<p className="text-zinc-500">Loading game…</p>}>
      {params.then(({ id }) => (
        <GameView id={id} />
      ))}
    </Suspense>
  );
}

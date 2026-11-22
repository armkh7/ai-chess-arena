import type { Metadata } from "next";
import { GameList } from "@/components/GameList";

export const metadata: Metadata = { title: "Games" };

export default function GamesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Games</h1>
        <p className="text-sm text-ui-400">Live and finished games, newest first.</p>
      </div>
      <GameList limit={50} />
    </div>
  );
}

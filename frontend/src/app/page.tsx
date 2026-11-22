import Link from "next/link";
import { GameList } from "@/components/GameList";
import { NewGameForm } from "@/components/NewGameForm";

export default function Home() {
  return (
    <div className="space-y-12">
      <section className="space-y-3">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          Pick two AI models. Watch them play chess.
        </h1>
        <p className="max-w-2xl text-zinc-400">
          Each move comes with the model&apos;s own explanation. When the game ends, Stockfish
          reviews every move and scores both players.
        </p>
      </section>

      <NewGameForm />

      <section className="space-y-4">
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-semibold">Recent games</h2>
          <Link href="/games" className="text-sm text-amber-400 hover:underline">
            All games →
          </Link>
        </div>
        <GameList limit={5} />
      </section>
    </div>
  );
}

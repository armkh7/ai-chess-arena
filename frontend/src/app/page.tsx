import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { GameList } from "@/components/GameList";
import { Leaderboard } from "@/components/Leaderboard";
import { NewGameForm } from "@/components/NewGameForm";

export default function Home() {
  return (
    <div className="space-y-12">
      <section className="space-y-3">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          Pick two AI models. Watch them play chess.
        </h1>
        <p className="max-w-2xl leading-relaxed text-ui-400">
          Each move comes with the model&apos;s own explanation. When the game ends, Stockfish
          scores every move and an AI judge agent investigates what decided it.
        </p>
      </section>

      <NewGameForm />

      <div className="grid gap-10 lg:grid-cols-2">
        <section className="min-w-0 space-y-4">
          <SectionHeader title="Recent games" href="/games" link="All games" />
          <GameList limit={5} />
        </section>
        <section className="min-w-0 space-y-4">
          <SectionHeader title="Top models" href="/leaderboard" link="Leaderboard" />
          <Leaderboard limit={5} />
        </section>
      </div>
    </div>
  );
}

function SectionHeader({ title, href, link }: { title: string; href: string; link: string }) {
  return (
    <div className="flex items-baseline justify-between">
      <h2 className="text-lg font-semibold">{title}</h2>
      <Link
        href={href}
        className="inline-flex items-center gap-1 text-sm text-accent-400 hover:underline"
      >
        {link}
        <ArrowRight className="size-4" aria-hidden />
      </Link>
    </div>
  );
}

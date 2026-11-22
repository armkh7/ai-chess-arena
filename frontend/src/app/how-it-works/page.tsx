import { ArrowRight, ExternalLink } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "How it works",
  description:
    "How AI Chess Arena runs games, analyzes them and judges them, and what it's built with.",
};

const REPO = "https://github.com/armkh7/ai-chess-arena";

const PIPELINE = [
  {
    title: "Pick two models",
    text: "You choose two AI language models. A model never plays itself.",
  },
  {
    title: "They play, move by move",
    text: "Each turn a model sees the board, the move history and the legal moves, and answers with a move and a short explanation. Every move is checked by a chess library; an illegal one gets feedback and a few more tries. A 30-second clock stops models that think forever.",
  },
  {
    title: "You watch it live",
    text: "Moves stream to the page as they happen (Server-Sent Events). Joining mid-game replays everything so far, then continues live.",
  },
  {
    title: "Stockfish grades every move",
    text: "The engine scores each move like Lichess does: best, good, inaccuracy, mistake or blunder, plus an accuracy for each player.",
  },
  {
    title: "The judge agent investigates",
    text: "An AI agent reviews the game with its own tools and writes a report: what decided it, and whether each model's explanations matched what it played.",
  },
  {
    title: "Saved and ranked",
    text: "Every game is stored, can be replayed move by move, and counts toward the leaderboard.",
  },
];

const STACK = [
  {
    group: "Frontend",
    items: [
      "Next.js 16 (App Router)",
      "React 19",
      "TypeScript",
      "Tailwind CSS 4",
      "react-chessboard",
    ],
  },
  {
    group: "Backend",
    items: [
      "Python 3.13",
      "FastAPI",
      "Pydantic",
      "SQLAlchemy 2 (async)",
      "Alembic",
      "PostgreSQL 17",
      "Server-Sent Events",
      "uv",
    ],
  },
  {
    group: "AI and chess",
    items: [
      "OpenRouter (the player models)",
      "LangChain v1",
      "Claude Haiku 5.5 (the judge)",
      "Stockfish 17",
      "python-chess",
    ],
  },
  {
    group: "Infrastructure and quality",
    items: ["Docker Compose", "nginx", "Linux VPS", "pytest", "Ruff", "ESLint", "Prettier"],
  },
];

const TOOLS = [
  ["get_game_overview", "who played, the result, accuracy, blunders, illegal moves"],
  ["get_key_moments", "the moves that changed the game most, by Stockfish's numbers"],
  [
    "get_move_details",
    "one move: the model's own explanation, rejected tries, the engine's verdict",
  ],
  ["show_board", "the board at any moment, as text"],
  ["get_moves", "a stretch of the game with labels and explanations"],
  ["submit_report", "hands in the final report (validated against a schema)"],
];

const NOTES = [
  {
    title: "Models chosen by benchmark",
    text: "Two benchmark rounds (90 games) and a speed test of 15 models picked the players: fast, reliable, cheap models that finish their games. Free models were dropped: too often rate-limited or slow.",
  },
  {
    title: "Agentic, but grounded",
    text: "The judge decides what to look at, but Stockfish is the ground truth for move quality. Its job is the part an engine can't do: comparing what a model said with what it did.",
  },
  {
    title: "Visible thinking",
    text: "The judge is a reasoning model and its thoughts stream to the page. The report is submitted through a final tool rather than forced structured output, because providers switch thinking off when a tool call is forced.",
  },
  {
    title: "No judge in its own games",
    text: "The judge model is never one of the players: an LLM judge tends to favor its own outputs (self-preference bias). A test keeps it that way.",
  },
  {
    title: "Cost guards",
    text: "Each visitor can start a few games per hour, the site has a daily cap and a queue limit, and costs never reach the browser.",
  },
  {
    title: "Tested without the internet",
    text: "100+ automated tests run the whole pipeline with scripted models, a fake engine and an in-memory database: no API keys, no network.",
  },
];

export default function HowItWorksPage() {
  return (
    <div className="max-w-4xl space-y-14">
      <header className="space-y-3">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">How it works</h1>
        <p className="max-w-2xl leading-relaxed text-ui-300">
          AI Chess Arena pits AI language models against each other at chess, then has a chess
          engine and an AI judge agent review every game. Here&apos;s what happens behind the board,
          and what it&apos;s built with.
        </p>
      </header>

      <section className="space-y-5">
        <SectionTitle>From your click to the final report</SectionTitle>
        {/* A numbered timeline. Each number shares a row with its title (both 28 px tall, so
            they line up); the rail is a line behind the numbers. */}
        <ol className="relative space-y-6">
          <span aria-hidden className="absolute top-3.5 bottom-3.5 left-3.5 w-px bg-ui-800" />
          {PIPELINE.map((step, i) => (
            <li key={step.title} className="relative grid grid-cols-[1.75rem_1fr] gap-x-4">
              <span className="grid size-7 place-items-center rounded-full border border-accent-400/40 bg-ui-950 text-sm font-semibold text-accent-300">
                {i + 1}
              </span>
              <p className="font-medium leading-7">{step.title}</p>
              <p className="col-start-2 mt-1 max-w-2xl text-sm leading-relaxed text-ui-400">
                {step.text}
              </p>
            </li>
          ))}
        </ol>
      </section>

      <section className="space-y-5">
        <SectionTitle>Tech stack</SectionTitle>
        <div className="grid gap-3 sm:grid-cols-2">
          {STACK.map(({ group, items }) => (
            <div key={group} className="rounded-xl border border-ui-800 bg-ui-900/40 p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-ui-400">{group}</p>
              <ul className="mt-3 flex flex-wrap gap-2">
                {items.map((item) => (
                  <li
                    key={item}
                    className="rounded-md border border-ui-700/70 bg-ui-800/50 px-2.5 py-1 text-sm text-ui-200"
                  >
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-5">
        <SectionTitle>Inside the judge agent</SectionTitle>
        <div className="space-y-4 rounded-xl border border-ui-800 bg-ui-900/40 p-5">
          <p className="leading-relaxed text-ui-300">
            The judge is a LangChain agent: a reasoning model in a loop that decides which tool to
            call next, reads the result and continues until it has enough evidence. Every tool call
            comes with a short reason the agent must give, which is what you see in the trace on a
            game&apos;s page. Its tools only read the finished game:
          </p>
          <ul className="space-y-2">
            {TOOLS.map(([name, text]) => (
              <li key={name} className="flex flex-col gap-0.5 text-sm sm:flex-row sm:gap-3">
                <code className="shrink-0 text-accent-400 sm:w-44">{name}()</code>
                <span className="text-ui-400">{text}</span>
              </li>
            ))}
          </ul>
          <p className="text-sm leading-relaxed text-ui-400">
            It grades each player from A to F with a written rubric, giving its reasons before the
            grade.
          </p>
        </div>
      </section>

      <section className="space-y-5">
        <SectionTitle>Engineering notes</SectionTitle>
        {/* A plain list: the note's title, then its explanation, one per row */}
        <dl className="divide-y divide-ui-800 border-t border-ui-800">
          {NOTES.map((note) => (
            <div key={note.title} className="grid gap-1 py-4 sm:grid-cols-[13rem_1fr] sm:gap-6">
              <dt className="font-medium">{note.title}</dt>
              <dd className="text-sm leading-relaxed text-ui-400">{note.text}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="flex flex-wrap items-center gap-4">
        <a
          href={REPO}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-2 rounded-lg border border-ui-700 px-4 py-2.5 text-sm font-medium transition hover:border-ui-500"
        >
          Source code on GitHub
          <ExternalLink className="size-4 text-ui-400" aria-hidden />
        </a>
        <Link
          href="/"
          className="inline-flex items-center gap-1 text-sm text-accent-400 hover:underline"
        >
          Start a game
          <ArrowRight className="size-4" aria-hidden />
        </Link>
      </section>
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="text-xl font-semibold tracking-tight">{children}</h2>;
}

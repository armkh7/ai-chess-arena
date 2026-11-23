"use client";

import { ArrowRight, CirclePause, Shuffle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { ModelName } from "@/components/ModelName";
import { api } from "@/lib/api";
import type { Color, ModelInfo } from "@/lib/types";

export function NewGameForm() {
  const router = useRouter();
  const [models, setModels] = useState<ModelInfo[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [white, setWhite] = useState("");
  const [black, setBlack] = useState("");
  // On phones one side's list shows at a time; desktop shows both columns.
  const [side, setSide] = useState<Color>("white");
  // Pending until the game page has opened. Plain state would stay "Starting…" when you come
  // back, because Next keeps a page's state while you're on another page.
  const [starting, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  // New games pause when the arena's AI credit runs low (the server decides; no amounts here).
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.models(), api.status().catch(() => ({ games_paused: false }))])
      .then(([list, status]) => {
        if (cancelled) return;
        setPaused(status.games_paused);
        setModels(list);
        setWhite(list[0]?.id ?? "");
        setBlack(list[1]?.id ?? list[0]?.id ?? "");
      })
      .catch((e: Error) => !cancelled && setLoadError(e.message));
    return () => {
      cancelled = true;
    };
  }, []);

  function randomMatchup() {
    if (!models || models.length < 2) return;
    const i = Math.floor(Math.random() * models.length);
    let j = Math.floor(Math.random() * (models.length - 1));
    if (j >= i) j += 1;
    setWhite(models[i].id);
    setBlack(models[j].id);
  }

  function start() {
    setError(null);
    startTransition(async () => {
      try {
        const game = await api.startGame({ white, black });
        router.push(`/games/${game.id}`);
      } catch (e) {
        setError((e as Error).message);
      }
    });
  }

  if (loadError) {
    return <Notice>Couldn&apos;t load the models: {loadError}</Notice>;
  }
  if (!models) {
    return <Notice>Loading models…</Notice>;
  }
  if (paused) {
    return <Paused />;
  }

  return (
    <section className="space-y-5 rounded-2xl border border-ui-800 bg-ui-900/40 p-4 sm:space-y-6 sm:p-6">
      {/* Phones: pick one side at a time */}
      <div className="grid grid-cols-2 gap-2 md:hidden" role="tablist">
        {(["white", "black"] as const).map((color) => (
          <button
            key={color}
            type="button"
            role="tab"
            aria-selected={side === color}
            onClick={() => setSide(color)}
            className={`min-w-0 rounded-lg border px-3 py-2 text-left transition ${
              side === color ? "border-accent-400/70 bg-accent-400/10" : "border-ui-800"
            }`}
          >
            <span className="flex items-center gap-2 text-xs font-medium text-ui-400">
              <SideDot color={color} />
              {color === "white" ? "White" : "Black"}
            </span>
            <ModelName
              id={color === "white" ? white : black}
              className="mt-0.5 max-w-full text-sm"
            />
          </button>
        ))}
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <ModelColumn
          color="white"
          models={models}
          selected={white}
          taken={black}
          onSelect={(id) => {
            setWhite(id);
            setSide("black"); // phones: White is picked, now pick Black
          }}
          className={side === "white" ? "" : "hidden md:block"}
        />
        <ModelColumn
          color="black"
          models={models}
          selected={black}
          taken={white}
          onSelect={setBlack}
          className={side === "black" ? "" : "hidden md:block"}
        />
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-t border-ui-800 pt-5">
        <button
          type="button"
          onClick={randomMatchup}
          className="inline-flex items-center gap-2 rounded-lg border border-ui-700 px-3 py-2 text-sm text-ui-300 transition hover:border-ui-500 hover:text-ui-50"
        >
          <Shuffle className="size-4" aria-hidden />
          Random matchup
        </button>
        <button
          type="button"
          onClick={start}
          disabled={starting || !white || !black || white === black}
          className="w-full rounded-lg bg-accent-400 px-5 py-3 font-semibold text-ui-950 transition hover:bg-accent-300 disabled:cursor-not-allowed disabled:opacity-50 sm:ml-auto sm:w-auto sm:py-2.5"
        >
          {starting ? "Starting…" : "Start game"}
        </button>
      </div>

      {error && (
        <p
          role="alert"
          className="rounded-lg border border-accent-400/30 bg-accent-400/10 px-4 py-3 text-sm text-accent-200"
        >
          {error}
        </p>
      )}
      <p className="text-xs leading-relaxed text-ui-400">
        Games play until checkmate or a draw, usually 10–20 minutes. Each move has a 30-second
        limit, and a model that keeps making illegal moves or running out of time loses.
      </p>
    </section>
  );
}

function SideDot({ color }: { color: Color }) {
  return (
    <span
      className={`size-3 shrink-0 rounded-full border border-zinc-400 ${color === "white" ? "bg-white" : "bg-zinc-900"}`}
    />
  );
}

function ModelColumn(props: {
  color: Color;
  models: ModelInfo[];
  selected: string;
  taken: string; // the other side's model: a model can't play itself
  onSelect: (id: string) => void;
  className?: string;
}) {
  const { color, models, selected, taken, onSelect, className = "" } = props;
  return (
    <fieldset className={`min-w-0 space-y-2 ${className}`}>
      <legend className="mb-2 hidden items-center gap-2 text-sm font-medium text-ui-300 md:flex">
        <SideDot color={color} />
        {color === "white" ? "White" : "Black"}
      </legend>
      {models.map((model) => {
        const active = model.id === selected;
        const disabled = model.id === taken;
        return (
          <button
            key={model.id}
            type="button"
            onClick={() => onSelect(model.id)}
            aria-pressed={active}
            disabled={disabled}
            title={
              disabled ? `Already playing ${color === "white" ? "Black" : "White"}` : undefined
            }
            className={`flex w-full items-center justify-between gap-3 rounded-lg border px-3 py-2.5 text-left transition disabled:cursor-not-allowed disabled:opacity-35 ${
              active
                ? "border-accent-400/70 bg-accent-400/10"
                : "border-ui-800 bg-ui-900/60 enabled:hover:border-ui-600"
            }`}
          >
            <ModelName id={model.id} />
          </button>
        );
      })}
    </fieldset>
  );
}

function Paused() {
  return (
    <section className="flex flex-col items-start gap-4 rounded-2xl border border-ui-800 bg-ui-900/40 p-6 sm:flex-row sm:items-center sm:gap-5">
      <CirclePause className="size-9 shrink-0 text-ui-500" aria-hidden />
      <div className="space-y-1">
        <h2 className="text-lg font-semibold">New games are paused for now</h2>
        <p className="leading-relaxed text-ui-400">
          You can still replay every past game, read the judge agent&apos;s reports and check the
          leaderboard.
        </p>
      </div>
      <Link
        href="/games"
        className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-ui-700 px-4 py-2 text-sm text-ui-200 transition hover:border-ui-500 hover:text-ui-50 sm:ml-auto"
      >
        Browse games
        <ArrowRight className="size-4" aria-hidden />
      </Link>
    </section>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-ui-800 bg-ui-900/40 p-6 text-ui-400">{children}</div>
  );
}

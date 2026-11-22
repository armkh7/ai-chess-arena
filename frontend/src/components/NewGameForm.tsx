"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { ModelName } from "@/components/ModelName";
import { api } from "@/lib/api";
import { costPerGame, formatCost } from "@/lib/format";
import type { Color, ModelInfo } from "@/lib/types";

// Games play to the end; a typical one is 40-60 moves per side. Only used for the estimate.
const TYPICAL_MOVES = 50;

export function NewGameForm() {
  const router = useRouter();
  const [models, setModels] = useState<ModelInfo[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [white, setWhite] = useState("");
  const [black, setBlack] = useState("");
  // Pending until the game page has opened. Plain state would stay "Starting…" when you come
  // back, because Next keeps a page's state while you're on another page.
  const [starting, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .models()
      .then((list) => {
        if (cancelled) return;
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

  const byId = new Map(models.map((m) => [m.id, m]));
  const cost = [white, black].reduce((sum, id) => {
    const model = byId.get(id);
    return model ? sum + costPerGame(model, TYPICAL_MOVES) : sum;
  }, 0);

  return (
    <section className="space-y-6 rounded-2xl border border-zinc-800 bg-zinc-900/40 p-5 sm:p-6">
      <div className="grid gap-6 md:grid-cols-2">
        <ModelColumn
          color="white"
          models={models}
          selected={white}
          taken={black}
          onSelect={setWhite}
        />
        <ModelColumn
          color="black"
          models={models}
          selected={black}
          taken={white}
          onSelect={setBlack}
        />
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-4 border-t border-zinc-800 pt-5">
        <button
          type="button"
          onClick={randomMatchup}
          className="rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-300 transition hover:border-zinc-500 hover:text-zinc-50"
        >
          Random matchup
        </button>

        <div className="ml-auto flex items-center gap-4">
          <p className="text-sm text-zinc-400">
            Estimated cost <span className="font-medium text-zinc-200">{formatCost(cost)}</span>
          </p>
          <button
            type="button"
            onClick={start}
            disabled={starting || !white || !black || white === black}
            className="rounded-lg bg-amber-400 px-5 py-2.5 font-semibold text-zinc-950 transition hover:bg-amber-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {starting ? "Starting…" : "Start game"}
          </button>
        </div>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}
      <p className="text-xs text-zinc-500">
        Games play until checkmate or a draw, usually 10–20 minutes. Each move has a 30-second
        limit, and a model that keeps making illegal moves or running out of time loses.
      </p>
    </section>
  );
}

function ModelColumn(props: {
  color: Color;
  models: ModelInfo[];
  selected: string;
  taken: string; // the other side's model: a model can't play itself
  onSelect: (id: string) => void;
}) {
  const { color, models, selected, taken, onSelect } = props;
  return (
    <fieldset className="space-y-2">
      <legend className="mb-2 flex items-center gap-2 text-sm font-medium text-zinc-300">
        <span
          className={`size-3 rounded-full border border-zinc-500 ${color === "white" ? "bg-zinc-100" : "bg-zinc-950"}`}
        />
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
                ? "border-amber-400/70 bg-amber-400/10"
                : "border-zinc-800 bg-zinc-900/60 enabled:hover:border-zinc-600"
            }`}
          >
            <ModelName id={model.id} />
            {!model.is_free && (
              <span className="shrink-0 text-xs tabular-nums text-zinc-500">
                ~{formatCost(costPerGame(model, TYPICAL_MOVES))}
              </span>
            )}
          </button>
        );
      })}
    </fieldset>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 text-zinc-400">
      {children}
    </div>
  );
}

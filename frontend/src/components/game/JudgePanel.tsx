"use client";

import { useState } from "react";
import { ModelName } from "@/components/ModelName";
import type { Color, Grade, JudgeResult, JudgeStep, KeyMoment, PlayerVerdict } from "@/lib/types";

const GRADE_STYLE: Record<Grade, string> = {
  A: "bg-emerald-400/15 text-emerald-300 ring-emerald-400/40",
  B: "bg-lime-400/15 text-lime-300 ring-lime-400/40",
  C: "bg-yellow-400/15 text-yellow-300 ring-yellow-400/40",
  D: "bg-orange-400/15 text-orange-300 ring-orange-400/40",
  F: "bg-red-400/15 text-red-300 ring-red-400/40",
};

const TOOL_ICON: Record<string, string> = {
  get_game_overview: "📋",
  get_key_moments: "📈",
  get_move_details: "🔍",
  show_board: "♟",
  get_moves: "📜",
  submit_report: "📝",
};

/**
 * The judge agent at work, then its report. While it runs, each thought and tool call
 * appears as it happens; finished games replay the same trace.
 */
export function JudgePanel(props: {
  steps: JudgeStep[];
  judge: JudgeResult | null;
  judging: boolean;
  models: Record<Color, string>;
  onShowMove: (ply: number) => void;
}) {
  const { steps, judge, judging, models, onShowMove } = props;
  const report = judge?.report;

  return (
    <section className="overflow-hidden rounded-2xl border border-violet-400/25 bg-gradient-to-b from-violet-500/[0.07] to-transparent">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-violet-400/15 px-5 py-3">
        <span className="text-lg">⚖️</span>
        <h2 className="font-semibold">Judge agent</h2>
        <span className="text-xs text-zinc-500">
          LangChain agent · {judge?.model ?? "reasoning model"} · reads the game with tools
        </span>
        <span className="ml-auto text-xs text-zinc-400">
          {judging ? (
            <span className="flex items-center gap-2 text-violet-300">
              <span className="size-2 animate-pulse rounded-full bg-violet-400" />
              Reviewing the game…
            </span>
          ) : judge ? (
            `${steps.length} steps · ${judge.seconds.toFixed(0)} s · $${judge.cost_usd.toFixed(4)}`
          ) : null}
        </span>
      </header>

      <div className="grid gap-0 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <Trace steps={steps} judging={judging} />
        <div className="border-t border-violet-400/15 p-5 lg:border-t-0 lg:border-l">
          {report ? (
            <Report report={report} models={models} onShowMove={onShowMove} />
          ) : judge?.error ? (
            <p className="text-sm text-red-400">The judge couldn&apos;t finish: {judge.error}</p>
          ) : (
            <div className="flex h-full min-h-40 flex-col items-center justify-center gap-2 text-center text-sm text-zinc-500">
              <span className="text-2xl">🧑‍⚖️</span>
              The judge is gathering evidence: it compares what each model said about its moves with
              what the moves did and what Stockfish thinks.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function Trace({ steps, judging }: { steps: JudgeStep[]; judging: boolean }) {
  return (
    <div className="p-5">
      <p className="mb-3 text-xs font-medium uppercase tracking-wide text-zinc-500">Agent trace</p>
      <ol className="relative space-y-3 border-l border-zinc-800 pl-5">
        {steps.map((step, i) =>
          step.kind === "thinking" ? (
            <Thought key={i} text={step.text} />
          ) : (
            <ToolCall key={i} step={step} />
          ),
        )}
        {judging && (
          <li className="relative text-sm text-violet-300">
            <Dot className="animate-pulse bg-violet-400" />
            thinking…
          </li>
        )}
        {!judging && !steps.length && <li className="text-sm text-zinc-500">No steps.</li>}
      </ol>
    </div>
  );
}

function Thought({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const long = text.length > 220;
  return (
    <li className="relative">
      <Dot className="bg-zinc-600" />
      <button
        type="button"
        onClick={() => long && setOpen((o) => !o)}
        className={`text-left text-sm italic leading-relaxed text-zinc-400 ${long ? "cursor-pointer hover:text-zinc-300" : "cursor-default"}`}
        title={long ? (open ? "Show less" : "Show the full thought") : undefined}
      >
        <span className="mr-1 not-italic">💭</span>
        {open || !long ? text : `${text.slice(0, 220).trimEnd()}…`}
      </button>
    </li>
  );
}

function ToolCall({ step }: { step: JudgeStep }) {
  return (
    <li className="relative">
      <Dot className="bg-violet-400" />
      <p className="flex flex-wrap items-baseline gap-x-2 text-sm">
        <span>{TOOL_ICON[step.tool ?? ""] ?? "🔧"}</span>
        <span className="font-medium text-zinc-100">{step.title}</span>
        <code className="text-[11px] text-violet-300/70">{step.tool}()</code>
      </p>
      {step.text && <p className="mt-0.5 text-sm text-zinc-400">{step.text}</p>}
    </li>
  );
}

function Dot({ className }: { className: string }) {
  return (
    <span
      className={`absolute top-1.5 -left-[25px] size-2 rounded-full ring-4 ring-zinc-950 ${className}`}
    />
  );
}

function Report(props: {
  report: NonNullable<JudgeResult["report"]>;
  models: Record<Color, string>;
  onShowMove: (ply: number) => void;
}) {
  const { report, models, onShowMove } = props;
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h3 className="text-xl font-semibold leading-snug tracking-tight">{report.headline}</h3>
        <p className="leading-relaxed text-zinc-300">{report.summary}</p>
      </div>

      <div className="space-y-3">
        <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">Key moments</p>
        {report.key_moments.map((moment) => (
          <Moment key={moment.ply} moment={moment} onShowMove={onShowMove} />
        ))}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <Verdict color="white" model={models.white} verdict={report.white} />
        <Verdict color="black" model={models.black} verdict={report.black} />
      </div>
    </div>
  );
}

function Moment({ moment, onShowMove }: { moment: KeyMoment; onShowMove: (ply: number) => void }) {
  return (
    <div className="space-y-1.5 rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
      <div className="flex items-baseline gap-3">
        <p className="font-medium">{moment.title}</p>
        <button
          type="button"
          onClick={() => onShowMove(moment.ply)}
          className="ml-auto shrink-0 text-xs text-amber-400 hover:underline"
        >
          Show on board
        </button>
      </div>
      <p className="text-sm leading-relaxed text-zinc-300">{moment.what_happened}</p>
      <p className="flex gap-2 text-sm leading-relaxed text-zinc-400">
        <span
          className={`shrink-0 font-semibold ${moment.reasoning_matched ? "text-emerald-400" : "text-red-400"}`}
          title={
            moment.reasoning_matched
              ? "The explanation matched the move"
              : "The explanation didn't match the move"
          }
        >
          {moment.reasoning_matched ? "✓" : "✗"}
        </span>
        {moment.reasoning_check}
      </p>
    </div>
  );
}

function Verdict({
  color,
  model,
  verdict,
}: {
  color: Color;
  model: string;
  verdict: PlayerVerdict;
}) {
  return (
    <div className="space-y-2 rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
      <div className="flex items-center gap-3">
        <span
          className={`grid size-10 shrink-0 place-items-center rounded-lg text-xl font-bold ring-1 ${GRADE_STYLE[verdict.grade]}`}
        >
          {verdict.grade}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs text-zinc-500">{color === "white" ? "White" : "Black"}</p>
          <ModelName id={model} className="max-w-full" />
        </div>
      </div>
      <Line label="Strengths" text={verdict.strengths} />
      <Line label="Weaknesses" text={verdict.weaknesses} />
      <Line label="Its explanations" text={verdict.reasoning_quality} />
    </div>
  );
}

function Line({ label, text }: { label: string; text: string }) {
  return (
    <p className="text-sm leading-relaxed text-zinc-400">
      <span className="font-medium text-zinc-300">{label}: </span>
      {text}
    </p>
  );
}

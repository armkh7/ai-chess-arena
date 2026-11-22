"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ModelName } from "@/components/ModelName";
import { api } from "@/lib/api";
import type { LeaderboardRow } from "@/lib/types";

const GRADE_COLOR: Record<string, string> = {
  A: "text-emerald-300",
  B: "text-lime-300",
  C: "text-yellow-300",
  D: "text-orange-300",
  F: "text-red-300",
};

/** The leaderboard table. `limit` shows only the top rows (the home page card). */
export function Leaderboard({ limit }: { limit?: number }) {
  const [rows, setRows] = useState<LeaderboardRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .leaderboard()
      .then((data) => !cancelled && setRows(data))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, []);

  if (error)
    return <p className="text-sm text-red-400">Couldn&apos;t load the leaderboard: {error}</p>;
  if (!rows) return <p className="text-sm text-ui-400">Loading the leaderboard…</p>;
  if (!rows.length)
    return (
      <p className="rounded-xl border border-ui-800 p-4 text-sm text-ui-400">
        No ranked games yet. Finished games will appear here.
      </p>
    );

  const shown = limit ? rows.slice(0, limit) : rows;
  const compact = limit !== undefined;

  return (
    <div className="overflow-hidden rounded-xl border border-ui-800">
      <table className="w-full text-sm">
        <thead className="bg-ui-900/60 text-left text-xs uppercase tracking-wide text-ui-400">
          <tr>
            <th className="w-10 py-2.5 pl-4 font-medium">#</th>
            <th className="py-2.5 pl-2 font-medium">Model</th>
            <th className="py-2.5 pr-4 text-right font-medium">Rating</th>
            <th className="hidden py-2.5 pr-4 text-right font-medium sm:table-cell">W-D-L</th>
            {!compact && (
              <>
                <th className="hidden py-2.5 pr-4 text-right font-medium md:table-cell">
                  Accuracy
                </th>
                <th className="hidden py-2.5 pr-4 text-right font-medium md:table-cell">Grade</th>
                <th className="hidden py-2.5 pr-4 text-right font-medium lg:table-cell">Honest</th>
              </>
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-ui-800/80">
          {shown.map((row) => (
            <tr key={row.model} className="transition hover:bg-ui-900/50">
              <td className="py-3 pl-4 tabular-nums text-ui-400">{row.rank}</td>
              <td className="max-w-0 py-3 pl-2">
                <ModelName id={row.model} className="max-w-full" />
                <p className="text-xs text-ui-400 sm:hidden">
                  {row.wins}-{row.draws}-{row.losses}
                </p>
              </td>
              <td className="py-3 pr-4 text-right font-semibold tabular-nums">
                <span className="inline-flex items-center justify-end gap-1.5">
                  {row.provisional && (
                    <span
                      className="rounded bg-ui-800 px-1.5 py-px text-[11px] font-medium uppercase tracking-wide text-ui-300"
                      title={`New: ${row.games} of 5 games played, the rating is still a rough guess`}
                    >
                      new
                    </span>
                  )}
                  <span className={row.provisional ? "text-ui-300" : ""}>{row.rating}</span>
                </span>
              </td>
              <td className="hidden py-3 pr-4 text-right tabular-nums text-ui-300 sm:table-cell">
                {row.wins}-{row.draws}-{row.losses}
              </td>
              {!compact && (
                <>
                  <td className="hidden py-3 pr-4 text-right tabular-nums text-ui-300 md:table-cell">
                    {row.accuracy !== null ? `${row.accuracy.toFixed(1)}%` : "–"}
                  </td>
                  <td
                    className={`hidden py-3 pr-4 text-right font-semibold md:table-cell ${row.grade ? GRADE_COLOR[row.grade] : "text-ui-500"}`}
                  >
                    {row.grade ?? "–"}
                  </td>
                  <td className="hidden py-3 pr-4 text-right tabular-nums text-ui-300 lg:table-cell">
                    {row.honest !== null ? `${row.honest}%` : "–"}
                  </td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {compact && rows.length > shown.length && (
        <Link
          href="/leaderboard"
          className="flex items-center gap-1 border-t border-ui-800 px-4 py-2.5 text-sm text-accent-400 hover:bg-ui-900/50"
        >
          See all {rows.length} models
          <ArrowRight className="size-4" aria-hidden />
        </Link>
      )}
    </div>
  );
}

import { modelParts } from "@/lib/format";

/** "gpt-oss-120b  openai" with a FREE badge for free models. */
export function ModelName({ id, className = "" }: { id: string; className?: string }) {
  const { provider, name, free } = modelParts(id);
  return (
    <span className={`inline-flex min-w-0 items-baseline gap-1.5 ${className}`} title={id}>
      <span className="truncate font-medium text-zinc-100">{name}</span>
      {provider && <span className="shrink-0 text-xs text-zinc-500">{provider}</span>}
      {free && (
        <span className="shrink-0 rounded bg-emerald-500/15 px-1.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-400">
          free
        </span>
      )}
    </span>
  );
}

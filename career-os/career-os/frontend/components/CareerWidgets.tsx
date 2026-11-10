import Link from "next/link";
import type { JobWithMatch } from "@/lib/api";

export default function CareerWidgets({
  jobs,
  loading,
  loadError,
}: {
  jobs: JobWithMatch[];
  loading: boolean;
  loadError: boolean;
}) {
  const latest = jobs.find((item) => item.match) ?? null;
  const match = latest?.match ?? null;
  const progress = match ? Math.max(0, Math.min(100, match.score)) : 0;
  const matched = match?.matched_requirements.slice(0, 3) ?? [];
  const missing = match?.missing_requirements.slice(0, 2) ?? [];
  const jobTitle = latest?.job.title?.trim() || "Untitled job";
  const company = latest?.job.company?.trim();

  return (
    <aside>
      <section className="animate-rise-in rounded-3xl border border-line bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-indigo-100 hover:shadow-md">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-slate-900">Latest match insights</h2>
            <p className="mt-1 truncate text-xs text-muted">
              {match ? `${jobTitle}${company ? ` · ${company}` : ""}` : "Your most recent analysis"}
            </p>
          </div>
          {match && (
            <span className="shrink-0 rounded-full bg-indigo-50 px-2.5 py-1 text-[10px] font-semibold text-indigo-700">
              Latest
            </span>
          )}
        </div>

        {loading ? (
          <div className="mt-5 space-y-4" aria-label="Loading match insights">
            <div className="h-8 w-24 animate-pulse rounded-lg bg-slate-100" />
            <div className="h-2 animate-pulse rounded-full bg-slate-100" />
            <div className="h-4 w-4/5 animate-pulse rounded bg-slate-100" />
            <div className="h-4 w-3/5 animate-pulse rounded bg-slate-100" />
          </div>
        ) : match ? (
          <>
            <div className="mt-5 flex items-end gap-2">
              <span className="text-3xl font-bold tracking-tight tabular-nums text-slate-900">
                {match.score}%
              </span>
              <span className="pb-1 text-xs text-muted">match score</span>
            </div>
            <div
              className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100"
              role="progressbar"
              aria-label="Latest match score"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={progress}
            >
              <div
                className="h-full rounded-full bg-blue-600 transition-[width] duration-700 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>

            <div className="mt-5 space-y-3">
              {matched.map((item) => (
                <p key={item} className="flex items-start gap-2 text-xs leading-5 text-slate-600">
                  <span className="mt-0.5 text-emerald-600" aria-hidden="true">✓</span>
                  <span>{item}</span>
                </p>
              ))}
              {missing.map((item) => (
                <p key={item} className="flex items-start gap-2 text-xs leading-5 text-slate-500">
                  <span className="mt-0.5 text-amber-500" aria-hidden="true">○</span>
                  <span>{item}</span>
                </p>
              ))}
              {matched.length === 0 && missing.length === 0 && (
                <p className="text-xs leading-5 text-muted">{match.reasoning}</p>
              )}
            </div>
          </>
        ) : (
          <p className="mt-5 text-xs leading-5 text-muted">
            {loadError
              ? "Match insights could not be loaded. Try refreshing the pipeline."
              : "Analyze a job to see the skills that match and the gaps to work on."}
          </p>
        )}

        <Link
          href={match ? "/pipeline" : "/jobs"}
          className="mt-5 inline-flex items-center gap-1 rounded text-xs font-semibold text-indigo-600 transition-colors hover:text-indigo-800"
        >
          {match ? "Browse pipeline" : "Find jobs"} <span aria-hidden="true">→</span>
        </Link>
      </section>
    </aside>
  );
}

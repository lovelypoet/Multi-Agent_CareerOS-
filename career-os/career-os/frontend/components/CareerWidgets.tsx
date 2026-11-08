import Link from "next/link";
import type { DashboardSummary, JobWithMatch } from "@/lib/api";

export default function CareerWidgets({
  summary,
  jobs,
}: {
  summary: DashboardSummary | null;
  jobs: JobWithMatch[];
}) {
  const latestMatch = jobs.find((item) => item.match)?.match ?? null;
  const score = summary?.avg_score ?? null;
  const progress = score === null ? 0 : Math.max(0, Math.min(100, score));
  const matched = latestMatch?.matched_requirements.slice(0, 3) ?? [];
  const missing = latestMatch?.missing_requirements.slice(0, 1) ?? [];

  return (
    <aside className="space-y-5">
      <section className="rounded-3xl border border-line bg-white p-5 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-slate-900">ATS Score</h2>
            <p className="mt-1 text-xs text-muted">Automated resume analysis</p>
          </div>
          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-semibold text-slate-500">
            Coming soon
          </span>
        </div>

        <div className="mt-5 flex items-center gap-4">
          <div
            className="grid h-24 w-24 shrink-0 place-items-center rounded-full border-[7px] border-slate-100 text-2xl font-bold text-slate-400"
            aria-label="ATS score unavailable"
          >
            —
          </div>
          <div className="space-y-2.5 text-xs text-slate-400">
            {["Keywords", "Formatting", "Readability"].map((item) => (
              <p key={item} className="flex items-center gap-2">
                <span className="grid h-4 w-4 place-items-center rounded-full bg-slate-100 text-[10px]">
                  ·
                </span>
                {item} <span className="text-[10px]">Coming soon</span>
              </p>
            ))}
          </div>
        </div>

        <p className="mt-4 text-xs leading-5 text-muted">
          CareerOS does not calculate an ATS score yet. You can still save and update your resume.
        </p>
        <Link
          href="/resume"
          className="mt-4 flex w-full items-center justify-center rounded-xl bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white transition-colors hover:bg-indigo-700"
        >
          Improve my resume
        </Link>
      </section>

      <section className="rounded-3xl border border-line bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Momentum</h2>
            <p className="mt-1 text-xs text-muted">Your recent matches</p>
          </div>
          <span className="text-xs font-medium text-indigo-600">Live</span>
        </div>

        <div className="mt-5 flex items-end gap-2">
          <span className="text-3xl font-bold tracking-tight text-slate-900">
            {score === null ? "—" : `${(score / 10).toFixed(1)}/10`}
          </span>
          <span className="pb-1 text-xs text-muted">average score</span>
        </div>
        <div
          className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100"
          role="progressbar"
          aria-label="Average match score"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={progress}
        >
          <div
            className="h-full rounded-full bg-blue-600 transition-all"
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
          {!latestMatch && (
            <p className="text-xs leading-5 text-muted">
              Analyze a job to see your strengths and skills to improve here.
            </p>
          )}
        </div>

        <Link
          href="/#pipeline"
          className="mt-5 inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-700"
        >
          View full details <span aria-hidden="true">→</span>
        </Link>
      </section>
    </aside>
  );
}

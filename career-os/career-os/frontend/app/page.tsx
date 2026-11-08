"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import CareerWidgets from "@/components/CareerWidgets";
import EmailNotifications from "@/components/EmailNotifications";
import ErrorNotice from "@/components/ErrorNotice";
import HistoryList from "@/components/HistoryList";
import JobSearch from "@/components/JobSearch";
import MatchCard from "@/components/MatchCard";
import PendingDots from "@/components/PendingDots";
import {
  analyzeJob,
  ApiError,
  getDashboardSummary,
  listJobs,
  type ApplicationStatus,
  type DashboardSummary,
  type JobWithMatch,
  type MatchResult,
} from "@/lib/api";

function MetricCard({
  value,
  label,
  detail,
  accent = false,
}: {
  value: string;
  label: string;
  detail?: string;
  accent?: boolean;
}) {
  return (
    <article className="rounded-2xl border border-line bg-white p-4 shadow-sm sm:p-5">
      <p className={`text-2xl font-bold tracking-tight ${accent ? "text-indigo-600" : "text-slate-900"}`}>
        {value}
      </p>
      <p className="mt-1 text-xs font-medium text-slate-600">{label}</p>
      {detail && <p className="mt-1 text-[10px] text-muted">{detail}</p>}
    </article>
  );
}

function errorMessage(error: unknown): { code: string; message: string } {
  if (error instanceof ApiError) {
    if (error.code === "RESUME_NOT_FOUND") {
      return {
        code: error.code,
        message: "Save your resume before starting an analysis.",
      };
    }
    if (error.code === "AGENT_FAILED" || error.code === "AGENT_UNAVAILABLE") {
      return {
        code: error.code,
        message: "The analysis could not be completed. Your job was saved; you can try again.",
      };
    }
  }
  return {
    code: "UNKNOWN",
    message: "Something went wrong. Check your connection to the server and try again.",
  };
}

export default function PipelinePage() {
  const [description, setDescription] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<MatchResult | null>(null);
  const [analysisError, setAnalysisError] = useState<{ code: string; message: string } | null>(null);
  const [jobs, setJobs] = useState<JobWithMatch[] | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const refreshDashboard = useCallback(async () => {
    setLoadError(null);
    try {
      const [nextJobs, nextSummary] = await Promise.all([listJobs(), getDashboardSummary()]);
      setJobs(nextJobs);
      setSummary(nextSummary);
    } catch {
      setLoadError("Could not load your pipeline. Check the server and try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshDashboard();
  }, [refreshDashboard]);

  const canAnalyze = description.trim().length > 0 && !analyzing;
  const submittedCount = jobs?.filter((item) => item.application_status === "applied").length;
  const latestListCount = jobs?.length ?? 0;

  async function handleAnalyze() {
    if (!canAnalyze) return;

    setAnalyzing(true);
    setAnalysisError(null);
    setResult(null);

    try {
      const response = await analyzeJob(description.trim());
      setResult(response.match);
      await refreshDashboard();
    } catch (error) {
      setAnalysisError(errorMessage(error));
      await refreshDashboard();
    } finally {
      setAnalyzing(false);
    }
  }

  function handleStatusChange(jobId: number, status: ApplicationStatus) {
    setJobs((current) =>
      current?.map((item) =>
        item.job.id === jobId ? { ...item, application_status: status } : item,
      ) ?? null,
    );
    setSummary((current) => {
      if (!current) return current;
      const previous = jobs?.find((item) => item.job.id === jobId)?.application_status;
      const adjustment = Number(status === "approved") - Number(previous === "approved");
      return { ...current, approved_count: current.approved_count + adjustment };
    });
  }

  return (
    <div className="grid items-start gap-6 2xl:grid-cols-[minmax(0,1fr)_320px]">
      <div className="min-w-0 space-y-7">
        <header id="overview" className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-indigo-600">
              Your job search
            </p>
            <h1 className="mt-2 text-3xl font-bold tracking-tight text-slate-900">Pipeline</h1>
            <p className="mt-2 text-sm text-muted">
              Review your jobs, analyses, and next steps.
            </p>
          </div>
          <Link
            href="/resume"
            className="rounded-xl border border-line bg-white px-4 py-2.5 text-xs font-semibold text-slate-700 shadow-sm transition hover:border-indigo-200 hover:text-indigo-700"
          >
            Manage resume
          </Link>
        </header>

        <section aria-label="Pipeline metrics" className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          <MetricCard
            value={summary ? String(summary.jobs_today) : "—"}
            label="Jobs today"
            accent
          />
          <MetricCard
            value={summary ? String(summary.approved_count) : "—"}
            label="Ready to apply"
            detail="Approved jobs"
          />
          <MetricCard
            value={submittedCount === undefined ? "—" : String(submittedCount)}
            label="Applications sent"
            detail={`Among ${latestListCount} recent jobs`}
          />
          <MetricCard value="—" label="Interviews" detail="Tracking coming soon" />
        </section>

        <section id="pipeline" className="scroll-mt-6">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-slate-900">Jobs in your pipeline</h2>
              <p className="mt-1 text-xs text-muted">
                Your saved jobs, sorted by date added.
              </p>
            </div>
            <span className="rounded-full bg-indigo-50 px-3 py-1 text-[11px] font-semibold text-indigo-700">
              {jobs ? `${jobs.length} recent jobs` : "Loading…"}
            </span>
          </div>

          {loadError && (
            <div role="alert" className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-red-100 bg-red-50 p-4 text-sm text-red-800">
              <span>{loadError}</span>
              <button
                type="button"
                onClick={() => void refreshDashboard()}
                className="font-semibold underline underline-offset-2"
              >
                Try again
              </button>
            </div>
          )}

          {loading ? (
            <div className="rounded-2xl border border-line bg-white p-8 text-sm text-muted shadow-sm">
              <PendingDots label="Loading your pipeline" />
            </div>
          ) : jobs ? (
            <HistoryList items={jobs} onStatusChange={handleStatusChange} />
          ) : null}

          <div className="mt-4 text-center">
            <a
              href="#job-search"
              className="text-xs font-semibold text-indigo-600 transition hover:text-indigo-800"
            >
              Find more jobs <span aria-hidden="true">→</span>
            </a>
          </div>
        </section>

        <section id="job-search" className="scroll-mt-6 rounded-2xl border border-line bg-white p-5 shadow-sm sm:p-6">
          <JobSearch />
        </section>

        <section className="rounded-2xl border border-line bg-white p-5 shadow-sm sm:p-6">
          <h2 className="text-base font-semibold text-slate-900">Analyze a job</h2>
          <p className="mt-1 text-xs leading-5 text-muted">
            Paste a job description to compare its requirements with your resume and check for potential warning signs.
          </p>

          <label htmlFor="job-description" className="sr-only">
            Job description
          </label>
          <textarea
            id="job-description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            disabled={analyzing}
            rows={8}
            placeholder="Paste the full job description here…"
            className="mt-4 w-full rounded-xl border border-line bg-slate-50/70 p-4 text-sm text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-indigo-400 focus:bg-white disabled:opacity-60"
          />

          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => void handleAnalyze()}
              disabled={!canAnalyze}
              className="rounded-xl bg-indigo-600 px-5 py-2.5 text-xs font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {analyzing ? <PendingDots label="Analyzing" /> : "Analyze job match"}
            </button>
            {analyzing && <span className="text-xs text-muted">This may take a few seconds.</span>}
          </div>
        </section>

        {analysisError && (
          <ErrorNotice
            code={analysisError.code}
            message={analysisError.message}
            onRetry={() => void handleAnalyze()}
          />
        )}

        {result && <MatchCard match={result} />}

        <EmailNotifications />
      </div>

      <div className="space-y-5 2xl:sticky 2xl:top-6">
        <CareerWidgets summary={summary} jobs={jobs ?? []} />
      </div>
    </div>
  );
}

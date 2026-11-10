"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import CareerWidgets from "@/components/CareerWidgets";
import EmailNotifications from "@/components/EmailNotifications";
import HistoryList from "@/components/HistoryList";
import Icon from "@/components/Icon";
import PendingDots from "@/components/PendingDots";
import {
  getDashboardSummary,
  listJobs,
  type DashboardSummary,
  type JobWithMatch,
} from "@/lib/api";

function MetricCard({
  value,
  label,
  detail,
  index,
}: {
  value: string;
  label: string;
  detail?: string;
  index: number;
}) {
  return (
    <article
      className="animate-rise-in rounded-2xl border border-line bg-white p-4 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-indigo-100 hover:shadow-md sm:p-5"
      style={{ animationDelay: `${index * 60}ms` }}
    >
      <p className="text-2xl font-bold tracking-tight text-indigo-600">{value}</p>
      <p className="mt-1 text-xs font-medium text-slate-600">{label}</p>
      {detail && <p className="mt-1 text-[10px] text-muted">{detail}</p>}
    </article>
  );
}

export default function DashboardPage() {
  const [jobs, setJobs] = useState<JobWithMatch[] | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  const refreshDashboard = useCallback(async () => {
    setLoadError(false);
    try {
      const [nextJobs, nextSummary] = await Promise.all([listJobs(), getDashboardSummary()]);
      setJobs(nextJobs);
      setSummary(nextSummary);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshDashboard();
  }, [refreshDashboard]);

  const submittedCount = jobs?.filter((item) => item.application_status === "applied").length;
  const recentJobs = jobs?.slice(0, 3) ?? [];

  return (
    <div className="animate-rise-in grid items-start gap-6 2xl:grid-cols-[minmax(0,1fr)_320px]">
      <div className="min-w-0 space-y-7">
        <header className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-indigo-600">
              CareerOS overview
            </p>
            <h1 className="mt-2 text-3xl font-bold tracking-tight text-slate-900">Dashboard</h1>
            <p className="mt-2 text-sm text-muted">A clear view of your job search progress.</p>
          </div>
          <Link
            href="/jobs"
            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white shadow-sm transition hover:bg-indigo-700"
          >
            <Icon name="search" />
            Find jobs
          </Link>
        </header>

        <section aria-label="Job search metrics" className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <MetricCard
            value={summary ? String(summary.jobs_today) : "—"}
            label="Jobs today"
            index={0}
          />
          <MetricCard
            value={summary ? String(summary.approved_count) : "—"}
            label="Ready to apply"
            detail="Approved jobs"
            index={1}
          />
          <MetricCard
            value={submittedCount === undefined ? "—" : String(submittedCount)}
            label="Applied jobs"
            detail={`Among ${jobs?.length ?? 0} recent jobs`}
            index={2}
          />
        </section>

        <section className="rounded-2xl border border-line bg-white p-5 shadow-sm sm:p-6">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-slate-900">Recent pipeline activity</h2>
              <p className="mt-1 text-xs text-muted">Your latest saved opportunities.</p>
            </div>
            <Link
              href="/pipeline"
              className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-800"
            >
              Open pipeline <Icon name="arrow" className="h-3.5 w-3.5" />
            </Link>
          </div>

          {loadError && (
            <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-100 bg-red-50 p-4 text-sm text-red-800">
              <span>Could not load your dashboard. Check the server and try again.</span>
              <button type="button" onClick={() => void refreshDashboard()} className="font-semibold underline">
                Try again
              </button>
            </div>
          )}
          {loading ? (
            <div className="rounded-xl bg-slate-50 p-6 text-sm text-muted">
              <PendingDots label="Loading your dashboard" />
            </div>
          ) : !loadError && jobs?.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/70 p-6 text-center">
              <p className="font-semibold text-slate-800">Your pipeline is empty</p>
              <p className="mt-1 text-sm text-muted">Find a job to start building your pipeline.</p>
              <Link href="/jobs" className="mt-3 inline-flex text-sm font-semibold text-indigo-600 hover:text-indigo-800">
                Explore jobs <span className="ml-1" aria-hidden="true">→</span>
              </Link>
            </div>
          ) : recentJobs.length > 0 ? (
            <HistoryList items={recentJobs} />
          ) : null}
        </section>

        <EmailNotifications />
      </div>

      <div className="2xl:sticky 2xl:top-6">
        <CareerWidgets jobs={jobs ?? []} loading={loading} loadError={loadError} />
      </div>
    </div>
  );
}

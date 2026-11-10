"use client";

import { useCallback, useEffect, useState } from "react";
import HistoryList from "@/components/HistoryList";
import Icon from "@/components/Icon";
import PendingDots from "@/components/PendingDots";
import { listJobs, type ApplicationStatus, type JobWithMatch } from "@/lib/api";

export default function PipelinePage() {
  const [jobs, setJobs] = useState<JobWithMatch[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  const refreshJobs = useCallback(async () => {
    setLoadError(false);
    try {
      setJobs(await listJobs());
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshJobs();
  }, [refreshJobs]);

  function handleStatusChange(jobId: number, status: ApplicationStatus) {
    setJobs((current) =>
      current?.map((item) =>
        item.job.id === jobId ? { ...item, application_status: status } : item,
      ) ?? null,
    );
  }

  return (
    <div className="animate-rise-in mx-auto max-w-5xl space-y-7">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-indigo-600">Track</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight text-slate-900">Pipeline</h1>
          <p className="mt-2 text-sm text-muted">
            Review matches from ITviec and Remote OK; source links open the original posting.
          </p>
        </div>
        {!loading && jobs && (
          <span className="rounded-full bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-700">
            {jobs.length} {jobs.length === 1 ? "job" : "jobs"}
          </span>
        )}
      </header>

      {loadError && (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-red-100 bg-red-50 p-4 text-sm text-red-800">
          <span>Could not load your pipeline. Check the server and try again.</span>
          <button
            type="button"
            onClick={() => void refreshJobs()}
            className="inline-flex items-center gap-2 font-semibold underline underline-offset-2"
          >
            <Icon name="refresh" />
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
    </div>
  );
}

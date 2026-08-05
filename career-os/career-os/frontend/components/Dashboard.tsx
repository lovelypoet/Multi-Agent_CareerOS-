"use client";

import { useEffect, useState } from "react";
import { type DashboardSummary, getDashboardSummary } from "@/lib/api";

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-card border border-line bg-surface p-5 shadow-card">
      <p className="font-display text-caption font-semibold uppercase tracking-wide text-muted">
        {label}
      </p>
      <p className="mt-2 font-display text-section-lg font-bold tabular-nums">{value}</p>
    </div>
  );
}

export default function Dashboard() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);

  useEffect(() => {
    getDashboardSummary()
      .then(setSummary)
      .catch(() => setSummary(null));
  }, []);

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <StatTile label="Job hôm nay" value={summary ? String(summary.jobs_today) : "—"} />
      <StatTile label="Đã approve" value={summary ? String(summary.approved_count) : "—"} />
      <StatTile
        label="Điểm trung bình"
        value={summary ? (summary.avg_score === null ? "—" : `${(summary.avg_score / 10).toFixed(1)}/10`) : "—"}
      />
    </div>
  );
}

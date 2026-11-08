"use client";

import { useMemo, useState } from "react";
import type { ApplicationStatus, JobWithMatch } from "@/lib/api";
import AgentRunsDetail from "./AgentRunsDetail";
import CoverLetterPanel from "./CoverLetterPanel";
import ScamAssessmentDetail from "./ScamAssessmentDetail";
import ScamWarningBadge from "./ScamWarningBadge";
import SourceBadge from "./SourceBadge";
import StatusButtons from "./StatusButtons";
import VerdictBadge from "./VerdictBadge";

type SortOrder = "newest" | "score";

const STATUS_STYLE: Record<ApplicationStatus, { label: string; className: string }> = {
  pending: { label: "To review", className: "bg-slate-100 text-slate-600" },
  approved: { label: "Ready to apply", className: "bg-orange-50 text-orange-700" },
  rejected: { label: "Rejected", className: "bg-slate-100 text-slate-500" },
  applied: { label: "Applied", className: "bg-blue-50 text-blue-700" },
};

function formatRelativeDate(iso: string) {
  const days = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000));
  if (days === 0) return "Added today";
  if (days === 1) return "Added yesterday";
  if (days < 7) return `Added ${days} days ago`;
  return `Added ${new Date(iso).toLocaleDateString("en-US", { day: "numeric", month: "short" })}`;
}

function excerpt(text: string, max = 150) {
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length > max ? `${clean.slice(0, max)}…` : clean;
}

export default function HistoryList({
  items,
  onStatusChange,
}: {
  items: JobWithMatch[];
  onStatusChange?: (jobId: number, status: ApplicationStatus) => void;
}) {
  const [sortOrder, setSortOrder] = useState<SortOrder>("newest");
  const [expandedJobId, setExpandedJobId] = useState<number | null>(null);
  const [expandedScamDetailJobId, setExpandedScamDetailJobId] = useState<number | null>(null);
  const [expandedScamReviewJobId, setExpandedScamReviewJobId] = useState<number | null>(null);

  const sortedItems = useMemo(() => {
    if (sortOrder === "newest") return items;
    return [...items].sort((a, b) => (b.match?.score ?? -1) - (a.match?.score ?? -1));
  }, [items, sortOrder]);

  if (items.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-8 text-center shadow-sm">
        <p className="font-semibold text-slate-800">Your pipeline is empty</p>
        <p className="mt-2 text-sm text-muted">
          Search for a job or paste a description to get started.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-3 flex justify-end">
        <label htmlFor="history-sort" className="sr-only">
          Sort jobs
        </label>
        <select
          id="history-sort"
          value={sortOrder}
          onChange={(event) => setSortOrder(event.target.value as SortOrder)}
          className="rounded-xl border border-line bg-white px-3 py-2 text-xs font-semibold text-slate-600 outline-none focus:border-indigo-400"
        >
          <option value="newest">Newest</option>
          <option value="score">Best match</option>
        </select>
      </div>

      <ul className="space-y-3">
        {sortedItems.map(({ job, match, application_status, analysis_status, scam, scam_check_status }) => {
          const isExpanded = expandedJobId === job.id;
          const isScamDetailExpanded = expandedScamDetailJobId === job.id;
          const isScamReviewExpanded = expandedScamReviewJobId === job.id;
          const showScamWarning = scam_check_status === "analyzed" && scam?.is_suspicious === true;
          const company = job.company?.trim() || "Company not specified";
          const initials = company
            .split(/\s+/)
            .filter(Boolean)
            .slice(0, 2)
            .map((word) => word[0])
            .join("")
            .toUpperCase();
          const statusStyle = STATUS_STYLE[application_status];

          return (
            <li
              key={job.id}
              className="rounded-2xl border border-line bg-white p-4 shadow-sm transition-all hover:shadow-md sm:p-5"
            >
              <div className="flex items-start gap-3">
                <div
                  aria-hidden="true"
                  className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-slate-900 text-sm font-bold text-white"
                >
                  {initials || "C"}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-semibold text-slate-900">
                      {job.title ?? "Untitled job"}
                    </h3>
                    <SourceBadge source={job.source} />
                  </div>
                  <p className="mt-0.5 text-sm text-slate-600">{company}</p>
                  <p className="mt-1 text-[11px] text-muted">{formatRelativeDate(job.created_at)}</p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-2">
                  <span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${statusStyle.className}`}>
                    {statusStyle.label}
                  </span>
                  {match ? (
                    <span className="flex items-center gap-2">
                      <span className="text-sm font-bold tabular-nums text-slate-800">
                        {(match.score / 10).toFixed(1)}
                      </span>
                      <VerdictBadge verdict={match.verdict} size="sm" />
                    </span>
                  ) : analysis_status === "needs_review" ? (
                    <span className="rounded-full bg-needs-review-bg px-2.5 py-1 text-[10px] font-semibold text-needs-review">
                      Needs review
                    </span>
                  ) : (
                    <span className="text-[10px] text-muted">Analysis unavailable</span>
                  )}
                  {showScamWarning && (
                    <ScamWarningBadge
                      onClick={() =>
                        setExpandedScamDetailJobId(isScamDetailExpanded ? null : job.id)
                      }
                    />
                  )}
                </div>
              </div>

              <p className="mt-4 text-xs leading-5 text-slate-500">{excerpt(job.description)}</p>

              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3">
                <div className="flex flex-wrap items-center gap-3">
                  {job.url && (
                    <a
                      href={job.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs font-semibold text-indigo-600 hover:text-indigo-800"
                    >
                      View job <span aria-hidden="true">↗</span>
                    </a>
                  )}
                  {analysis_status === "needs_review" && (
                    <button
                      type="button"
                      onClick={() => setExpandedJobId(isExpanded ? null : job.id)}
                      className="text-xs font-semibold text-indigo-600 hover:underline"
                    >
                      {isExpanded ? "Hide details" : "Compare analyses"}
                    </button>
                  )}
                  {scam_check_status === "needs_review" && (
                    <button
                      type="button"
                      onClick={() =>
                        setExpandedScamReviewJobId(isScamReviewExpanded ? null : job.id)
                      }
                      className="text-xs font-semibold text-amber-700 hover:underline"
                    >
                      {isScamReviewExpanded ? "Hide assessment" : "Review alert"}
                    </button>
                  )}
                </div>
                <StatusButtons
                  jobId={job.id}
                  initialStatus={application_status}
                  onStatusChange={(status) => onStatusChange?.(job.id, status)}
                />
              </div>

              {isExpanded && (
                <div className="mt-4 border-t border-slate-100 pt-4">
                  <AgentRunsDetail jobId={job.id} />
                </div>
              )}
              {showScamWarning && scam && isScamDetailExpanded && (
                <div className="mt-4 border-t border-slate-100 pt-4">
                  <ScamAssessmentDetail scam={scam} />
                </div>
              )}
              {isScamReviewExpanded && (
                <div className="mt-4 border-t border-slate-100 pt-4">
                  <AgentRunsDetail jobId={job.id} agentName="scam_detection_agent" />
                </div>
              )}
              {application_status === "approved" && (
                <div className="mt-4 border-t border-slate-100 pt-4">
                  <CoverLetterPanel jobId={job.id} />
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

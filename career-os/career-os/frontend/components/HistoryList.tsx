"use client";

import { useMemo, useState } from "react";
import type { JobWithMatch } from "@/lib/api";
import AgentRunsDetail from "./AgentRunsDetail";
import SourceBadge from "./SourceBadge";
import StatusButtons from "./StatusButtons";
import VerdictBadge from "./VerdictBadge";

type SortOrder = "newest" | "score";

function formatDate(iso: string) {
  return new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function excerpt(text: string, max = 150) {
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length > max ? `${clean.slice(0, max)}…` : clean;
}

export default function HistoryList({ items }: { items: JobWithMatch[] }) {
  const [sortOrder, setSortOrder] = useState<SortOrder>("newest");
  const [expandedJobId, setExpandedJobId] = useState<number | null>(null);

  // API đã trả về sort theo created_at (mới nhất trước) — "Điểm cao nhất" chỉ cần sort lại
  // ở client, không cần sửa API. Job chưa có match_result luôn rơi xuống cuối khi sort theo điểm.
  const sortedItems = useMemo(() => {
    if (sortOrder === "newest") return items;
    return [...items].sort((a, b) => (b.match?.score ?? -1) - (a.match?.score ?? -1));
  }, [items, sortOrder]);

  // Màn hình trống là lời mời hành động, không phải khoảng trắng trơ trọi.
  if (items.length === 0) {
    return (
      <div className="rounded-card border border-dashed border-line bg-surface-muted p-8 text-center">
        <p className="font-display text-body font-semibold">Chưa có job nào được phân tích</p>
        <p className="mt-2 text-body text-muted">Dán job đầu tiên vào ô bên trên để bắt đầu.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-4 flex justify-end">
        <label htmlFor="history-sort" className="sr-only">
          Sắp xếp theo
        </label>
        <select
          id="history-sort"
          value={sortOrder}
          onChange={(event) => setSortOrder(event.target.value as SortOrder)}
          className="rounded-control border border-line bg-surface px-3 py-1.5 text-caption font-semibold text-content outline-none focus:border-accent"
        >
          <option value="newest">Mới nhất</option>
          <option value="score">Điểm cao nhất</option>
        </select>
      </div>

      <ul className="space-y-3">
        {sortedItems.map(({ job, match, application_status, analysis_status }) => {
          const isExpanded = expandedJobId === job.id;

          return (
            <li
              key={job.id}
              className="animate-rise-in rounded-card border border-line bg-surface p-5 shadow-card transition duration-150 ease-out-soft hover:bg-surface-muted"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-display text-body font-semibold">
                      {job.title ?? `Job #${job.id}`}
                    </p>
                    <SourceBadge source={job.source} />
                  </div>
                  <p className="mt-1 text-caption text-muted">{formatDate(job.created_at)}</p>
                </div>

                {match ? (
                  <div className="flex shrink-0 items-center gap-3">
                    <span className="font-display text-section-lg font-bold tabular-nums">
                      {(match.score / 10).toFixed(1)}
                    </span>
                    <VerdictBadge verdict={match.verdict} size="sm" />
                  </div>
                ) : analysis_status === "needs_review" ? (
                  <span className="shrink-0 rounded-full bg-needs-review-bg px-2.5 py-1 text-[12px] font-semibold text-needs-review">
                    Cần xem lại
                  </span>
                ) : (
                  <span className="shrink-0 rounded-full bg-surface-muted px-2.5 py-1 text-[12px] font-semibold text-muted">
                    Chưa phân tích được
                  </span>
                )}
              </div>

              <p className="mt-3 text-body text-muted">{excerpt(job.description)}</p>

              {analysis_status === "needs_review" && (
                <div className="mt-4 border-t border-line pt-3">
                  <button
                    type="button"
                    onClick={() => setExpandedJobId(isExpanded ? null : job.id)}
                    className="text-caption font-semibold text-accent underline decoration-dotted"
                  >
                    {isExpanded ? "Ẩn chi tiết" : "2 model bất đồng — xem chi tiết"}
                  </button>
                  {isExpanded && (
                    <div className="mt-3">
                      <AgentRunsDetail jobId={job.id} />
                    </div>
                  )}
                </div>
              )}

              <div className="mt-4 flex justify-end border-t border-line pt-3">
                <StatusButtons jobId={job.id} initialStatus={application_status} />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

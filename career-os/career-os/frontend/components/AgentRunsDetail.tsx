"use client";

import { useEffect, useState } from "react";
import { ApiError, type AgentRunDetail, type Verdict, getJobAgentRuns } from "@/lib/api";
import VerdictBadge from "./VerdictBadge";

function isVerdict(value: unknown): value is Verdict {
  return (
    value === "strong_match" ||
    value === "good_match" ||
    value === "partial_match" ||
    value === "weak_match"
  );
}

/** 2 model bất đồng — hiện cạnh nhau đủ để người dùng tự đọc và tự quyết định, không chỉ 1
 * nhãn mơ hồ "cần xem lại". Tái dùng style của MatchCard/VerdictBadge, không thiết kế mới. */
export default function AgentRunsDetail({ jobId }: { jobId: number }) {
  const [runs, setRuns] = useState<AgentRunDetail[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getJobAgentRuns(jobId)
      .then(setRuns)
      .catch((err) => {
        setError(
          err instanceof ApiError ? err.message : "Không tải được chi tiết các lần phân tích.",
        );
      });
  }, [jobId]);

  if (error) {
    return (
      <p role="alert" className="text-caption font-semibold text-verdict-weak">
        {error}
      </p>
    );
  }

  if (!runs) {
    return <p className="text-caption text-muted">Đang tải…</p>;
  }

  if (runs.length === 0) {
    return <p className="text-caption text-muted">Chưa có lần phân tích nào.</p>;
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {runs.map((run) => {
        const score = typeof run.output?.score === "number" ? run.output.score : null;
        const verdict = isVerdict(run.output?.verdict) ? run.output?.verdict : null;
        const reasoning = typeof run.output?.reasoning === "string" ? run.output.reasoning : null;

        return (
          <div key={run.id} className="rounded-card border border-line bg-surface-muted p-4">
            <p className="font-display text-caption font-semibold uppercase tracking-wide text-muted">
              {run.model ?? "Model không rõ"}
            </p>

            {run.error ? (
              <p className="mt-2 text-body text-verdict-weak">{run.error}</p>
            ) : (
              <>
                <div className="mt-2 flex items-center gap-3">
                  {score !== null && (
                    <span className="font-display text-section font-bold tabular-nums">
                      {(score / 10).toFixed(1)}
                    </span>
                  )}
                  {verdict && <VerdictBadge verdict={verdict} size="sm" />}
                </div>
                {reasoning && <p className="mt-2 text-body text-muted">{reasoning}</p>}
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}

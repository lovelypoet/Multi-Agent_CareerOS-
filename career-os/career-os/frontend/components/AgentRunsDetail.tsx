"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  type AgentRunDetail,
  type RiskLevel,
  type Verdict,
  getJobAgentRuns,
} from "@/lib/api";
import RiskLevelBadge from "./RiskLevelBadge";
import VerdictBadge from "./VerdictBadge";

function isVerdict(value: unknown): value is Verdict {
  return (
    value === "strong_match" ||
    value === "good_match" ||
    value === "partial_match" ||
    value === "weak_match"
  );
}

function isRiskLevel(value: unknown): value is RiskLevel {
  return value === "low" || value === "medium" || value === "high";
}

/** 2 model bất đồng — hiện cạnh nhau đủ để người dùng tự đọc và tự quyết định, không chỉ 1
 * nhãn mơ hồ "cần xem lại". Tái dùng style của MatchCard/VerdictBadge, không thiết kế mới.
 *
 * Dùng chung cho CẢ 2 agent có thể rơi vào needs_review (matching, scam_detection) — output
 * shape khác nhau (`verdict`/`score` vs `risk_level`/`red_flags`), tự nhận diện field nào có
 * mặt trong `run.output` để hiện đúng loại, không cần 2 component riêng.
 *
 * `agentName` tuỳ chọn — lọc đúng agent cần so sánh (vd. "scam_detection_agent"), tránh lẫn
 * agent_runs của agent khác vào cùng 1 job (xem `api/jobs.py::get_job_agent_runs` mục filter). */
export default function AgentRunsDetail({
  jobId,
  agentName,
}: {
  jobId: number;
  agentName?: string;
}) {
  const [runs, setRuns] = useState<AgentRunDetail[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getJobAgentRuns(jobId, agentName)
      .then(setRuns)
      .catch((err) => {
        setError(
          err instanceof ApiError ? err.message : "Không tải được chi tiết các lần phân tích.",
        );
      });
  }, [jobId, agentName]);

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
        const riskLevel = isRiskLevel(run.output?.risk_level) ? run.output?.risk_level : null;
        const redFlags = Array.isArray(run.output?.red_flags)
          ? (run.output.red_flags as unknown[]).filter((item): item is string => typeof item === "string")
          : null;
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
                  {riskLevel && <RiskLevelBadge riskLevel={riskLevel} size="sm" />}
                </div>
                {redFlags && redFlags.length > 0 && (
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-body text-content">
                    {redFlags.map((flag, index) => (
                      <li key={index}>{flag}</li>
                    ))}
                  </ul>
                )}
                {reasoning && <p className="mt-2 text-body text-muted">{reasoning}</p>}
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}

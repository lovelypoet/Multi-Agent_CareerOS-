"use client";

import { useState } from "react";
import {
  type ApplicationStatus,
  type UpdatableApplicationStatus,
  updateApplicationStatus,
} from "@/lib/api";
import Icon from "./Icon";

export default function StatusButtons({
  jobId,
  initialStatus,
  onStatusChange,
}: {
  jobId: number;
  initialStatus: ApplicationStatus;
  onStatusChange?: (status: ApplicationStatus) => void;
}) {
  const [status, setStatus] = useState<ApplicationStatus>(initialStatus);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleUpdate(next: UpdatableApplicationStatus) {
    if (updating) return;
    setUpdating(true);
    setError(null);
    try {
      const result = await updateApplicationStatus(jobId, next);
      setStatus(result.status);
      onStatusChange?.(result.status);
    } catch {
      setError("Could not update status. Please try again.");
    } finally {
      setUpdating(false);
    }
  }

  const actions: UpdatableApplicationStatus[] =
    status === "approved"
      ? ["rejected"]
      : status === "rejected"
        ? ["approved"]
        : status === "pending"
          ? ["approved", "rejected"]
          : [];

  if (actions.length === 0) return null;

  return (
    <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
      {actions.map((next) => (
        <button
          key={next}
          type="button"
          onClick={() => void handleUpdate(next)}
          disabled={updating}
          className={`rounded-xl px-3 py-1.5 text-[10px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${
            next === "approved"
              ? "bg-indigo-50 text-indigo-700 hover:bg-indigo-100"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
          }`}
        >
          {updating ? (
            "Updating…"
          ) : (
            <span className="inline-flex items-center gap-1.5">
              <Icon name={next === "approved" ? "check" : "close"} className="h-3.5 w-3.5" />
              {next === "approved" ? "Approve" : "Reject"}
            </span>
          )}
        </button>
      ))}
      {error && <span role="alert" className="w-full text-right text-[11px] text-red-600">{error}</span>}
    </div>
  );
}

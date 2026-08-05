"use client";

import { useState } from "react";
import {
  type ApplicationStatus,
  type UpdatableApplicationStatus,
  updateApplicationStatus,
} from "@/lib/api";

const STATUS_STYLE: Record<"approved" | "rejected", { label: string; className: string }> = {
  approved: { label: "Đã approve", className: "bg-status-approved-bg text-status-approved" },
  rejected: { label: "Đã reject", className: "bg-status-rejected-bg text-status-rejected" },
};

export default function StatusButtons({
  jobId,
  initialStatus,
}: {
  jobId: number;
  initialStatus: ApplicationStatus;
}) {
  const [status, setStatus] = useState<ApplicationStatus>(initialStatus);
  const [updating, setUpdating] = useState(false);

  async function handleUpdate(next: UpdatableApplicationStatus) {
    // Chặn bấm lần 2 khi request trước chưa xong — cùng nguyên tắc nút Analyze ở Phase 0.
    if (updating) return;
    setUpdating(true);
    try {
      const result = await updateApplicationStatus(jobId, next);
      setStatus(result.status);
    } catch {
      // Giữ nguyên trạng thái cũ nếu lỗi — không đoán mò trạng thái mới.
    } finally {
      setUpdating(false);
    }
  }

  if (status === "approved" || status === "rejected") {
    const style = STATUS_STYLE[status];
    const otherStatus: UpdatableApplicationStatus = status === "approved" ? "rejected" : "approved";
    const otherLabel = otherStatus === "approved" ? "Đổi thành Approve" : "Đổi thành Reject";

    return (
      <div className="flex shrink-0 items-center gap-2">
        <span className={`rounded-full px-2.5 py-1 text-[12px] font-semibold ${style.className}`}>
          {style.label}
        </span>
        <button
          type="button"
          onClick={() => void handleUpdate(otherStatus)}
          disabled={updating}
          className="text-[12px] font-semibold text-muted underline decoration-dotted transition-colors duration-150 hover:text-accent disabled:cursor-not-allowed disabled:opacity-50"
        >
          {otherLabel}
        </button>
      </div>
    );
  }

  return (
    <div className="flex shrink-0 items-center gap-2">
      <button
        type="button"
        onClick={() => void handleUpdate("approved")}
        disabled={updating}
        className="rounded-control bg-status-approved-bg px-2.5 py-1 text-[12px] font-semibold text-status-approved transition duration-150 ease-out-soft hover:scale-[1.03] disabled:cursor-not-allowed disabled:opacity-50"
      >
        Approve
      </button>
      <button
        type="button"
        onClick={() => void handleUpdate("rejected")}
        disabled={updating}
        className="rounded-control bg-status-rejected-bg px-2.5 py-1 text-[12px] font-semibold text-status-rejected transition duration-150 ease-out-soft hover:scale-[1.03] disabled:cursor-not-allowed disabled:opacity-50"
      >
        Reject
      </button>
    </div>
  );
}

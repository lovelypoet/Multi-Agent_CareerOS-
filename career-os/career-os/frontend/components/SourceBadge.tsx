import type { JobSource } from "@/lib/api";

/** Chỉ hiện badge cho job tự động fetch (Phase 1) — job dán tay (manual) không hiện gì,
 * giữ đúng hành vi mặc định của Phase 0. */
export default function SourceBadge({ source }: { source: JobSource }) {
  if (source !== "itviec") return null;

  return (
    <span className="inline-flex shrink-0 items-center rounded-full bg-accent-subtle px-2.5 py-1 text-[12px] font-semibold text-accent">
      Tự động
    </span>
  );
}

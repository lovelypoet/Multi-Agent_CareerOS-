import type { Verdict } from "@/lib/api";

/** Mỗi verdict dùng đúng cặp màu semantic đã quy định, không tự chọn màu khác. */
const VERDICT_STYLE: Record<Verdict, { label: string; className: string }> = {
  strong_match: { label: "Rất phù hợp", className: "bg-verdict-strong-bg text-verdict-strong" },
  good_match: { label: "Phù hợp tốt", className: "bg-verdict-good-bg text-verdict-good" },
  partial_match: { label: "Phù hợp một phần", className: "bg-verdict-partial-bg text-verdict-partial" },
  weak_match: { label: "Chưa phù hợp", className: "bg-verdict-weak-bg text-verdict-weak" },
};

export default function VerdictBadge({
  verdict,
  size = "md",
}: {
  verdict: Verdict;
  size?: "sm" | "md";
}) {
  const style = VERDICT_STYLE[verdict];
  const padding = size === "sm" ? "px-2.5 py-1 text-[12px]" : "px-3 py-1.5 text-caption";

  return (
    <span
      className={`inline-flex items-center rounded-full font-display font-semibold ${padding} ${style.className}`}
    >
      {style.label}
    </span>
  );
}

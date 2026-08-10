import type { RiskLevel } from "@/lib/api";

/** Tái dùng đúng 3 màu semantic đã có (verdict-strong/needs-review/scam-warning) theo tông
 * đèn giao thông xanh-vàng-đỏ, không tạo token màu mới cho từng mức risk_level. */
const RISK_LEVEL_STYLE: Record<RiskLevel, { label: string; className: string }> = {
  low: { label: "Rủi ro thấp", className: "bg-verdict-strong-bg text-verdict-strong" },
  medium: { label: "Rủi ro trung bình", className: "bg-needs-review-bg text-needs-review" },
  high: { label: "Rủi ro cao", className: "bg-scam-warning-bg text-scam-warning" },
};

export default function RiskLevelBadge({
  riskLevel,
  size = "md",
}: {
  riskLevel: RiskLevel;
  size?: "sm" | "md";
}) {
  const style = RISK_LEVEL_STYLE[riskLevel];
  const padding = size === "sm" ? "px-2.5 py-1 text-[12px]" : "px-3 py-1.5 text-caption";

  return (
    <span
      className={`inline-flex items-center rounded-full font-display font-semibold ${padding} ${style.className}`}
    >
      {style.label}
    </span>
  );
}

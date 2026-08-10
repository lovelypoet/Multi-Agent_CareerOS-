import type { ScamAssessment } from "@/lib/api";
import RiskLevelBadge from "./RiskLevelBadge";

/** Chi tiết ĐÚNG 1 kết quả `scam_assessments` đã lưu — view ĐƠN GIẢN 1 khối, KHÔNG so sánh 2
 * model cạnh nhau (khác `AgentRunsDetail`, dành riêng cho case `needs_review` khi 2 model bất
 * đồng và không có 1 kết quả cuối cùng để hiện kiểu này). */
export default function ScamAssessmentDetail({ scam }: { scam: ScamAssessment }) {
  return (
    <div className="rounded-card border border-line bg-surface-muted p-4">
      <RiskLevelBadge riskLevel={scam.risk_level} size="sm" />

      {scam.red_flags.length > 0 && (
        <ul className="mt-3 list-disc space-y-1 pl-5 text-body text-content">
          {scam.red_flags.map((flag, index) => (
            <li key={index}>{flag}</li>
          ))}
        </ul>
      )}

      <p className="mt-3 text-body text-muted">{scam.reasoning}</p>
    </div>
  );
}

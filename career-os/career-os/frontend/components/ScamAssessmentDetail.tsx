import type { ScamAssessment } from "@/lib/api";
import RiskLevelBadge from "./RiskLevelBadge";

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

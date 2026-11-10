import type { JDAnalysis, RequirementAssessment } from "@/lib/api";

const STATUS_STYLE = {
  met: "bg-emerald-50 text-emerald-700",
  partial: "bg-amber-50 text-amber-800",
  missing: "bg-rose-50 text-rose-700",
} as const;

const STATUS_LABEL = {
  met: "Evidence found",
  partial: "Partial evidence",
  missing: "Not evidenced",
} as const;

export default function RequirementEvidence({
  analysis,
  assessments,
}: {
  analysis: JDAnalysis;
  assessments: RequirementAssessment[] | null;
}) {
  const byIndex = new Map((assessments ?? []).map((item) => [item.requirement_index, item]));

  return (
    <section className="mt-8 border-t border-line pt-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="font-display text-caption font-semibold uppercase tracking-wide text-muted">
            JD requirements &amp; CV evidence
          </h3>
          {analysis.role_title && (
            <p className="mt-1 text-sm font-semibold text-content">{analysis.role_title}</p>
          )}
          <p className="mt-1 text-caption text-muted">
            Each quote is checked against its original document. Required items count twice as much
            as preferred items.
          </p>
        </div>
        {analysis.experience_level && (
          <span className="rounded-full bg-surface-muted px-3 py-1 text-caption text-content">
            {analysis.experience_level}
          </span>
        )}
      </div>

      {analysis.tech_stack.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {analysis.tech_stack.map((technology) => (
            <span
              key={technology}
              className="rounded-full border border-line px-2.5 py-1 text-caption text-muted"
            >
              {technology}
            </span>
          ))}
        </div>
      )}

      <ul className="mt-4 space-y-3">
        {analysis.requirements.map((requirement, index) => {
          const assessment = byIndex.get(index);
          const status = assessment?.status ?? "missing";
          return (
            <li key={`${requirement.text}-${index}`} className="rounded-card bg-surface-muted p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-content">{requirement.text}</span>
                <span className="rounded-full bg-white px-2 py-0.5 text-[11px] text-muted">
                  {requirement.priority === "required" ? "Required" : "Preferred"}
                </span>
                <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${STATUS_STYLE[status]}`}>
                  {STATUS_LABEL[status]}
                </span>
              </div>
              <blockquote className="mt-2 border-l-2 border-slate-300 pl-3 text-caption text-muted">
                JD: “{requirement.jd_quote}”
              </blockquote>
              {assessment?.cv_evidence && (
                <blockquote className="mt-2 border-l-2 border-indigo-300 pl-3 text-caption text-content">
                  CV: “{assessment.cv_evidence}”
                </blockquote>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

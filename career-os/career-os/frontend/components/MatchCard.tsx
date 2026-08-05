import type { MatchResult } from "@/lib/api";
import ScoreCounter from "./ScoreCounter";
import VerdictBadge from "./VerdictBadge";

function RequirementList({
  title,
  items,
  marker,
  markerClass,
  emptyText,
}: {
  title: string;
  items: string[];
  marker: string;
  markerClass: string;
  emptyText: string;
}) {
  return (
    <section>
      <h3 className="font-display text-caption font-semibold uppercase tracking-wide text-muted">
        {title}
      </h3>
      {items.length === 0 ? (
        <p className="mt-3 text-body text-muted">{emptyText}</p>
      ) : (
        <ul className="mt-3 space-y-2.5">
          {items.map((item, index) => (
            <li key={index} className="flex gap-2.5 text-body">
              <span aria-hidden="true" className={`mt-0.5 shrink-0 font-semibold ${markerClass}`}>
                {marker}
              </span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function MatchCard({ match }: { match: MatchResult }) {
  return (
    <article className="animate-rise-in rounded-card border border-line bg-surface p-8 shadow-card">
      {/* Điểm số là thứ mắt phải nhìn thấy đầu tiên. */}
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-display text-caption font-semibold uppercase tracking-wide text-muted">
            Điểm phù hợp
          </p>
          <div className="mt-2">
            <ScoreCounter value={match.score} />
          </div>
        </div>
        <VerdictBadge verdict={match.verdict} />
      </header>

      <p className="mt-6 border-t border-line pt-6 text-body-lg">{match.reasoning}</p>

      <div className="mt-8 grid gap-8 sm:grid-cols-2">
        <RequirementList
          title="Đáp ứng được"
          items={match.matched_requirements}
          marker="+"
          markerClass="text-verdict-strong"
          emptyText="Chưa tìm thấy yêu cầu nào khớp rõ ràng."
        />
        <RequirementList
          title="Còn thiếu"
          items={match.missing_requirements}
          marker="−"
          markerClass="text-verdict-weak"
          emptyText="Không thiếu yêu cầu nào đáng kể."
        />
      </div>

      {match.suggestions.length > 0 && (
        <div className="mt-8 rounded-card bg-surface-muted p-6">
          <h3 className="font-display text-caption font-semibold uppercase tracking-wide text-muted">
            Gợi ý sửa CV cho job này
          </h3>
          <ol className="mt-3 space-y-2.5">
            {match.suggestions.map((suggestion, index) => (
              <li key={index} className="flex gap-3 text-body">
                <span
                  aria-hidden="true"
                  className="mt-0.5 shrink-0 font-display text-caption font-bold text-accent"
                >
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span>{suggestion}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </article>
  );
}

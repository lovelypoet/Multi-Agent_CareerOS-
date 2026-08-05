/** Loading tinh tế bằng 3 chấm nhấp nháy — không dùng spinner xoay generic. */
export default function PendingDots({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2" role="status" aria-live="polite">
      <span className="flex gap-1" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-1.5 w-1.5 rounded-full bg-current animate-dot-pulse"
            style={{ animationDelay: `${i * 140}ms` }}
          />
        ))}
      </span>
      {label ? <span>{label}</span> : null}
    </span>
  );
}

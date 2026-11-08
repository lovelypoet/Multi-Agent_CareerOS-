import type { EmailCategory } from "@/lib/api";

/** Tái dùng đúng màu semantic đã có (verdict-strong/verdict-weak/needs-review), không tạo token
 * màu mới riêng cho category — rejection = xấu (đỏ), interview_invite = tin tốt cần phản hồi
 * (xanh), follow_up_question = cần hành động (vàng, cùng ý nghĩa "cần xem lại" đã dùng ở nơi
 * khác), other_relevant = chỉ để biết, không cần làm gì (trung tính). */
const CATEGORY_STYLE: Record<EmailCategory, { label: string; className: string }> = {
  interview_invite: { label: "Interview invitation", className: "bg-verdict-strong-bg text-verdict-strong" },
  rejection: { label: "Rejection", className: "bg-verdict-weak-bg text-verdict-weak" },
  follow_up_question: { label: "Response required", className: "bg-needs-review-bg text-needs-review" },
  other_relevant: { label: "Relevant update", className: "bg-surface-muted text-muted" },
};

export default function EmailCategoryBadge({ category }: { category: EmailCategory }) {
  const style = CATEGORY_STYLE[category];

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-display font-semibold ${style.className}`}
    >
      {style.label}
    </span>
  );
}

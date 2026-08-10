import type { EmailCategory } from "@/lib/api";

/** Tái dùng đúng màu semantic đã có (verdict-strong/verdict-weak/needs-review), không tạo token
 * màu mới riêng cho category — rejection = xấu (đỏ), interview_invite = tin tốt cần phản hồi
 * (xanh), follow_up_question = cần hành động (vàng, cùng ý nghĩa "cần xem lại" đã dùng ở nơi
 * khác), other_relevant = chỉ để biết, không cần làm gì (trung tính). */
const CATEGORY_STYLE: Record<EmailCategory, { label: string; className: string }> = {
  interview_invite: { label: "Mời phỏng vấn", className: "bg-verdict-strong-bg text-verdict-strong" },
  rejection: { label: "Từ chối", className: "bg-verdict-weak-bg text-verdict-weak" },
  follow_up_question: { label: "Cần bạn trả lời", className: "bg-needs-review-bg text-needs-review" },
  other_relevant: { label: "Thông tin liên quan", className: "bg-surface-muted text-muted" },
};

/** Mời phỏng vấn nổi bật nhất trong 4 loại — thể hiện qua kích thước lớn hơn hẳn, không chỉ màu
 * sắc (màu sắc riêng biệt không đủ tạo cảm giác "nổi bật nhất" khi đặt cạnh nhau). */
export default function EmailCategoryBadge({ category }: { category: EmailCategory }) {
  const style = CATEGORY_STYLE[category];
  const isInterviewInvite = category === "interview_invite";

  return (
    <span
      className={`inline-flex items-center rounded-full font-display font-semibold ${
        isInterviewInvite ? "px-3.5 py-1.5 text-body" : "px-2.5 py-1 text-[12px]"
      } ${style.className}`}
    >
      {style.label}
    </span>
  );
}

/** Badge cảnh báo job có dấu hiệu lừa đảo — component cha (`HistoryList`) chỉ render component
 * này khi `scam_check_status === "analyzed"` VÀ `scam.is_suspicious === true`, nên ở đây không
 * kiểm tra lại điều kiện đó. Thuần trigger (không tự quản lý state mở/đóng) — component cha
 * quyết định hiện `ScamAssessmentDetail` ở đâu khi bấm, giống cách nút "2 model bất đồng — xem
 * chi tiết" của matching đã làm trong cùng file `HistoryList.tsx`. */
export default function ScamWarningBadge({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-scam-warning-bg px-2.5 py-1 text-[12px] font-semibold text-scam-warning transition duration-150 ease-out-soft hover:scale-[1.03]"
    >
      ⚠ Nghi ngờ lừa đảo
    </button>
  );
}

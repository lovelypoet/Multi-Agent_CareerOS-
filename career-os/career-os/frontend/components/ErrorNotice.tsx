import Link from "next/link";
import { ErrorCode } from "@/lib/api";

/**
 * Lỗi phải nói rõ chuyện gì xảy ra và làm gì tiếp theo — không đổ raw error kỹ thuật ra màn hình,
 * cũng không để trắng màn hình hay chỉ log console.
 */
export default function ErrorNotice({
  code,
  message,
  onRetry,
}: {
  code: string;
  message: string;
  onRetry?: () => void;
}) {
  const needsResume = code === ErrorCode.RESUME_NOT_FOUND;

  return (
    <div
      role="alert"
      className="animate-rise-in rounded-card border border-line bg-verdict-weak-bg p-5"
    >
      <p className="font-display text-body font-semibold text-verdict-weak">{message}</p>

      <div className="mt-4 flex flex-wrap gap-3">
        {needsResume && (
          <Link
            href="/resume"
            className="rounded-control bg-accent px-4 py-2 text-caption font-semibold text-white transition duration-150 ease-out-soft hover:bg-accent-hover hover:scale-[1.02]"
          >
            Lưu resume ngay
          </Link>
        )}
        {onRetry && !needsResume && (
          <button
            type="button"
            onClick={onRetry}
            className="rounded-control border border-line bg-surface px-4 py-2 text-caption font-semibold text-content transition duration-150 ease-out-soft hover:bg-surface-muted hover:scale-[1.02]"
          >
            Thử lại
          </button>
        )}
      </div>
    </div>
  );
}

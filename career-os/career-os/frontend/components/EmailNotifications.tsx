"use client";

import { useEffect, useState } from "react";
import { type EmailNotificationWithJob, getEmailNotifications } from "@/lib/api";
import EmailCategoryBadge from "./EmailCategoryBadge";

function formatDate(iso: string) {
  return new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Link "Mở trong Gmail" theo đúng địa chỉ email (không phải số thứ tự `/u/{n}/`, sai gần như
 * chắc chắn với tài khoản không phải mặc định khi có ≥2 tài khoản) — dùng query param
 * `authuser`, cách này được cộng đồng ghi nhận rộng rãi (không phải tài liệu chính thức của
 * Google) nên VẪN hiện rõ `account_email` cạnh link (xem `EmailNotifications`) để người dùng tự
 * biết cần mở đúng tài khoản nào nếu link lỡ mở nhầm tab.
 */
function gmailLink(accountEmail: string, messageId: string) {
  return `https://mail.google.com/mail/u/0/?authuser=${encodeURIComponent(accountEmail)}#inbox/${messageId}`;
}

export default function EmailNotifications() {
  const [items, setItems] = useState<EmailNotificationWithJob[] | null>(null);

  useEffect(() => {
    getEmailNotifications()
      .then(setItems)
      .catch(() => setItems([]));
  }, []);

  if (items === null) {
    return null;
  }

  if (items.length === 0) {
    return null;
  }

  // Không có endpoint riêng lộ ra "đang cấu hình bao nhiêu tài khoản Gmail" — suy ra từ chính dữ
  // liệu trả về: chỉ hiện account_email trên từng thẻ khi thực tế thấy ≥2 giá trị account_email
  // khác nhau trong danh sách đang có. Đơn giản, không cần thêm field cấu hình lộ ra FE chỉ để
  // phục vụ 1 quyết định hiển thị nhỏ.
  const distinctAccounts = new Set(items.map((item) => item.notification.account_email));
  const showAccountEmail = distinctAccounts.size > 1;

  return (
    <section>
      <h2 className="font-display text-section-lg font-bold tracking-tight">
        Email liên quan tới ứng tuyển
      </h2>
      <p className="mt-3 text-body-lg text-muted">
        Tự động phát hiện từ Gmail — chỉ đọc và phân loại, bạn tự trả lời/xử lý trực tiếp trên
        Gmail.
      </p>

      <ul className="mt-6 space-y-3">
        {items.map(({ notification, job }) => (
          <li
            key={notification.id}
            className="animate-rise-in rounded-card border border-line bg-surface p-5 shadow-card"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <p className="font-display text-body font-semibold">
                  {notification.company_name_mentioned ?? job?.company ?? notification.subject}
                </p>
                <p className="mt-1 text-caption text-muted">
                  {formatDate(notification.received_at)}
                  {showAccountEmail && ` · ${notification.account_email}`}
                </p>
              </div>
              {notification.category && <EmailCategoryBadge category={notification.category} />}
            </div>

            <p className="mt-3 text-body text-content">{notification.summary}</p>

            {job && (
              <p className="mt-2 text-caption text-muted">
                Liên quan tới job: {job.title ?? `#${job.id}`}
              </p>
            )}

            <div className="mt-4 flex justify-end border-t border-line pt-3">
              <a
                href={gmailLink(notification.account_email, notification.gmail_message_id)}
                target="_blank"
                rel="noopener noreferrer"
                className="text-caption font-semibold text-accent hover:underline"
              >
                Mở trong Gmail ↗
              </a>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

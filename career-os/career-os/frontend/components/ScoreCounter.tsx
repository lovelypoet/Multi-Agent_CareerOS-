"use client";

import { useEffect, useState } from "react";

/**
 * Đếm số từ 0 lên điểm thật trong ~600ms — khoảnh khắc "trình diễn" duy nhất của trang.
 * Nếu user bật giảm chuyển động thì hiện thẳng số cuối, không animate.
 */
export default function ScoreCounter({ value, durationMs = 600 }: { value: number; durationMs?: number }) {
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    const prefersReduced =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (prefersReduced) {
      setDisplay(value);
      return;
    }

    let frame = 0;
    const start = performance.now();

    const tick = (now: number) => {
      const progress = Math.min((now - start) / durationMs, 1);
      // ease-out: nhanh lúc đầu, chậm dần khi về đích.
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.round(eased * value));
      if (progress < 1) {
        frame = requestAnimationFrame(tick);
      }
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, durationMs]);

  return (
    <span className="font-display text-score font-bold tabular-nums text-content">
      {(display / 10).toFixed(1)}
      <span className="ml-1 text-section font-semibold text-muted">/10</span>
    </span>
  );
}

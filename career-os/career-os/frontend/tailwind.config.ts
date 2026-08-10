import type { Config } from "tailwindcss";

/**
 * Mọi token màu đều trỏ tới CSS variable khai báo trong app/globals.css.
 * Muốn đổi tông màu toàn app → sửa globals.css, không đụng vào component nào.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--color-bg)",
        surface: "var(--color-surface)",
        "surface-muted": "var(--color-surface-muted)",
        content: "var(--color-text)",
        muted: "var(--color-text-muted)",
        line: "var(--color-border)",
        accent: {
          DEFAULT: "var(--color-accent)",
          hover: "var(--color-accent-hover)",
          subtle: "var(--color-accent-subtle)",
        },
        verdict: {
          strong: "var(--verdict-strong)",
          "strong-bg": "var(--verdict-strong-bg)",
          good: "var(--verdict-good)",
          "good-bg": "var(--verdict-good-bg)",
          partial: "var(--verdict-partial)",
          "partial-bg": "var(--verdict-partial-bg)",
          weak: "var(--verdict-weak)",
          "weak-bg": "var(--verdict-weak-bg)",
        },
        status: {
          approved: "var(--status-approved)",
          "approved-bg": "var(--status-approved-bg)",
          rejected: "var(--status-rejected)",
          "rejected-bg": "var(--status-rejected-bg)",
        },
        "needs-review": {
          DEFAULT: "var(--needs-review)",
          bg: "var(--needs-review-bg)",
        },
        "scam-warning": {
          DEFAULT: "var(--scam-warning)",
          bg: "var(--scam-warning-bg)",
        },
      },
      fontFamily: {
        display: ["var(--font-manrope)", "system-ui", "sans-serif"],
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
      fontSize: {
        caption: ["13px", { lineHeight: "1.5" }],
        body: ["15px", { lineHeight: "1.65" }],
        "body-lg": ["16px", { lineHeight: "1.65" }],
        section: ["20px", { lineHeight: "1.35" }],
        "section-lg": ["24px", { lineHeight: "1.3" }],
        score: ["52px", { lineHeight: "1", letterSpacing: "-0.02em" }],
      },
      borderRadius: {
        card: "12px",
        control: "8px",
      },
      boxShadow: {
        card: "0 1px 3px rgba(43, 36, 39, 0.06)",
      },
      transitionTimingFunction: {
        "out-soft": "cubic-bezier(0, 0, 0.2, 1)",
      },
    },
  },
  plugins: [],
};

export default config;

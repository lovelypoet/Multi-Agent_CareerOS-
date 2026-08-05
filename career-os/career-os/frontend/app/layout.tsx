import type { Metadata } from "next";
import { Inter, Manrope } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const manrope = Manrope({
  subsets: ["latin", "vietnamese"],
  weight: ["600", "700"],
  variable: "--font-manrope",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin", "vietnamese"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "CareerOS",
  description: "Dán job description, chấm điểm phù hợp với CV của bạn.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" className={`${manrope.variable} ${inter.variable}`}>
      <body className="min-h-screen">
        <header className="border-b border-line bg-surface">
          <div className="mx-auto flex max-w-3xl items-center justify-between px-6 py-5">
            <Link href="/" className="font-display text-section font-bold tracking-tight">
              Career<span className="text-accent">OS</span>
            </Link>
            <nav className="flex gap-6 text-caption font-semibold">
              <Link href="/" className="transition-colors duration-150 hover:text-accent">
                Phân tích
              </Link>
              <Link href="/resume" className="transition-colors duration-150 hover:text-accent">
                Resume
              </Link>
            </nav>
          </div>
        </header>

        <main className="mx-auto max-w-3xl px-6 py-12">{children}</main>
      </body>
    </html>
  );
}

import type { Metadata } from "next";
import { Inter, Manrope } from "next/font/google";
import Sidebar from "@/components/Sidebar";
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
  description: "Manage your job search with CareerOS.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
      <html lang="en" className={`${manrope.variable} ${inter.variable}`}>
      <body className="min-h-screen">
        <div className="md:flex">
          <Sidebar />
          <main className="min-w-0 flex-1 p-4 sm:p-6 lg:p-8">{children}</main>
        </div>
      </body>
    </html>
  );
}

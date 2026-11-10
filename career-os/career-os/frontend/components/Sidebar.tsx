"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

type IconName = "dashboard" | "briefcase" | "pipeline" | "documents";

const navigation: {
  label: string;
  icon: IconName;
  href: string;
  isActive: (pathname: string) => boolean;
}[] = [
  { label: "Dashboard", icon: "dashboard", href: "/", isActive: (path) => path === "/" },
  { label: "Jobs", icon: "briefcase", href: "/jobs", isActive: (path) => path === "/jobs" },
  { label: "Pipeline", icon: "pipeline", href: "/pipeline", isActive: (path) => path === "/pipeline" },
  { label: "Documents", icon: "documents", href: "/resume", isActive: (path) => path === "/resume" },
];

function NavigationIcon({ name }: { name: IconName }) {
  const paths: Record<IconName, ReactNode> = {
    dashboard: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1.5" />
        <rect x="14" y="3" width="7" height="5" rx="1.5" />
        <rect x="14" y="12" width="7" height="9" rx="1.5" />
        <rect x="3" y="14" width="7" height="7" rx="1.5" />
      </>
    ),
    briefcase: (
      <>
        <rect x="3" y="7" width="18" height="14" rx="2" />
        <path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18M10 12v2h4v-2" />
      </>
    ),
    pipeline: (
      <>
        <path d="M4 5h16M4 12h10M4 19h6" />
        <circle cx="18" cy="12" r="2" />
        <circle cx="13" cy="19" r="2" />
      </>
    ),
    documents: (
      <>
        <path d="M6 3h8l4 4v14H6z" />
        <path d="M14 3v5h5M9 13h6M9 17h6" />
      </>
    ),
  };

  return (
    <svg
      aria-hidden="true"
      className="h-[18px] w-[18px] shrink-0"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name]}
    </svg>
  );
}

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="border-b border-line bg-white/90 px-4 py-4 md:sticky md:top-0 md:flex md:h-screen md:w-[250px] md:shrink-0 md:flex-col md:border-b-0 md:border-r md:px-5 md:py-6">
      <Link href="/" className="flex w-fit items-center gap-3 px-1">
        <span className="grid h-10 w-10 place-items-center rounded-full bg-gradient-to-br from-blue-500 to-indigo-700 text-lg font-bold text-white shadow-sm">
          C
        </span>
        <span className="font-display text-xl font-bold tracking-tight text-slate-900">
          Career<span className="text-indigo-600">OS</span>
        </span>
      </Link>

      <nav aria-label="Main navigation" className="mt-5 md:mt-10">
        <ul className="flex gap-1 overflow-x-auto pb-1 md:flex-col md:gap-1.5 md:overflow-visible md:pb-0">
          {navigation.map((item) => {
            const active = item.isActive(pathname);
            const className = `flex min-w-fit items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-medium transition-all duration-150 ${
              active
                ? "bg-indigo-50 text-indigo-700"
                : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
            }`;

            return (
              <li key={item.label}>
                <Link href={item.href} aria-current={active ? "page" : undefined} className={className}>
                  <NavigationIcon name={item.icon} />
                  <span>{item.label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </aside>
  );
}

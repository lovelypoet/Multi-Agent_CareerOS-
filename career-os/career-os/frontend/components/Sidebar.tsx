import Link from "next/link";
import type { ReactNode } from "react";

type IconName =
  | "dashboard"
  | "briefcase"
  | "pipeline"
  | "applications"
  | "interviews"
  | "documents"
  | "preparation"
  | "analytics"
  | "settings";

const navigation: {
  label: string;
  icon: IconName;
  href?: string;
  active?: boolean;
}[] = [
  { label: "Dashboard", icon: "dashboard", href: "/#overview" },
  { label: "Jobs", icon: "briefcase", href: "/#job-search" },
  { label: "Pipeline", icon: "pipeline", href: "/#pipeline", active: true },
  { label: "Applications", icon: "applications", href: "/#pipeline" },
  { label: "Interviews", icon: "interviews" },
  { label: "Documents", icon: "documents", href: "/resume" },
  { label: "Preparation", icon: "preparation" },
  { label: "Analytics", icon: "analytics" },
  { label: "Settings", icon: "settings" },
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
    applications: (
      <>
        <rect x="5" y="3" width="14" height="18" rx="2" />
        <path d="M9 8h6M9 12h6M9 16h3" />
      </>
    ),
    interviews: (
      <>
        <path d="M20 11.5a7.5 7.5 0 0 1-8 7.5 8.6 8.6 0 0 1-3.5-.8L4 20l1.5-3.5A7.2 7.2 0 0 1 4 12c0-4.1 3.6-7.5 8-7.5s8 3.1 8 7Z" />
        <path d="M8 12h.01M12 12h.01M16 12h.01" />
      </>
    ),
    documents: (
      <>
        <path d="M6 3h8l4 4v14H6z" />
        <path d="M14 3v5h5M9 13h6M9 17h6" />
      </>
    ),
    preparation: (
      <>
        <circle cx="12" cy="12" r="8" />
        <path d="m9 12 2 2 4-5M12 2v2M22 12h-2M4 12H2" />
      </>
    ),
    analytics: (
      <>
        <path d="M4 19V5M4 19h17" />
        <path d="m7 15 4-4 3 2 5-6" />
      </>
    ),
    settings: (
      <>
        <circle cx="12" cy="12" r="3" />
        <path d="m19.4 15 .1.1 1.4 1.1-1.5 2.6-1.7-.7a8 8 0 0 1-1.6.9l-.3 1.8h-3l-.3-1.8a8 8 0 0 1-1.6-.9l-1.7.7-1.5-2.6 1.4-1.1a7 7 0 0 1 0-1.9l-1.4-1.1 1.5-2.6 1.7.7a8 8 0 0 1 1.6-.9l.3-1.8h3l.3 1.8a8 8 0 0 1 1.6.9l1.7-.7 1.5 2.6-1.4 1.1a7 7 0 0 1-.1 1.8Z" />
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

function InterviewCopilot() {
  const bars = [12, 22, 16, 29, 19, 34, 15, 25, 12, 30, 18, 24, 11, 28, 16, 22, 10];

  return (
    <section className="mt-auto hidden rounded-2xl border border-line bg-white p-4 shadow-sm lg:block">
      <div className="flex items-center gap-2">
        <span className="grid h-8 w-8 place-items-center rounded-xl bg-indigo-50 text-indigo-600">
          <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor">
            <path d="m12 2 1.7 6.3L20 10l-6.3 1.7L12 18l-1.7-6.3L4 10l6.3-1.7L12 2Zm7 12 .9 3.1L23 18l-3.1.9L19 22l-.9-3.1L15 18l3.1-.9L19 14Z" />
          </svg>
        </span>
        <div>
          <h2 className="text-sm font-semibold text-content">Interview Copilot</h2>
          <span className="text-[11px] font-medium text-indigo-600">Coming soon</span>
        </div>
      </div>
      <p className="mt-3 text-xs leading-5 text-muted">
        Interview tracking and personalized briefings will be available here soon.
      </p>
      <div className="my-4 flex h-9 items-center justify-center gap-[3px]" aria-hidden="true">
        {bars.map((height, index) => (
          <span
            key={index}
            className={`w-[3px] rounded-full ${index % 2 ? "bg-blue-500" : "bg-indigo-800"}`}
            style={{ height }}
          />
        ))}
      </div>
      <button
        type="button"
        disabled
        className="w-full cursor-not-allowed rounded-xl bg-indigo-600 px-3 py-2.5 text-xs font-semibold text-white opacity-70"
      >
        Generate a briefing
      </button>
    </section>
  );
}

export default function Sidebar() {
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
            const className = `flex min-w-fit items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-medium transition-colors ${
              item.active
                ? "bg-indigo-50 text-indigo-700"
                : item.href
                  ? "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
                  : "cursor-not-allowed text-slate-400"
            }`;
            const contents = (
              <>
                <NavigationIcon name={item.icon} />
                <span>{item.label}</span>
                {!item.href && (
                  <span className="ml-auto hidden text-[10px] font-medium text-slate-400 md:inline">
                    Soon
                  </span>
                )}
              </>
            );

            return (
              <li key={item.label}>
                {item.href ? (
                  <Link href={item.href} aria-current={item.active ? "page" : undefined} className={className}>
                    {contents}
                  </Link>
                ) : (
                  <span aria-disabled="true" className={className} title="Coming soon">
                    {contents}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      </nav>

      <InterviewCopilot />
    </aside>
  );
}

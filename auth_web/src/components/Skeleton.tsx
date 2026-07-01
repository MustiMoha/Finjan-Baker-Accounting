import type { ReactNode } from "react";

function cx(...parts: Array<string | false | undefined>) {
  return parts.filter(Boolean).join(" ");
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cx("animate-pulse rounded-md bg-slate-200/80", className)}
      aria-hidden
    />
  );
}

export function SkeletonPageHeader({ subtitle = true }: { subtitle?: boolean }) {
  return (
    <header className="mb-6 space-y-2">
      <Skeleton className="h-8 w-56 max-w-full" />
      {subtitle ? <Skeleton className="h-4 w-80 max-w-full" /> : null}
    </header>
  );
}

export function SkeletonSection({
  title = true,
  children,
  className,
}: {
  title?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cx("rounded-xl border border-gray-100 bg-white p-5 shadow-sm", className)}
    >
      {title ? <Skeleton className="mb-4 h-6 w-40" /> : null}
      {children}
    </section>
  );
}

export function SkeletonMetricGrid({ count = 4 }: { count?: number }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="mt-3 h-8 w-28" />
          <Skeleton className="mt-2 h-3 w-32" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonChart({ tall = false }: { tall?: boolean }) {
  return (
    <SkeletonSection>
      <Skeleton className="mb-4 h-5 w-36" />
      <Skeleton className={cx("w-full rounded-lg", tall ? "h-64" : "h-48")} />
    </SkeletonSection>
  );
}

export function SkeletonTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <SkeletonSection title={false}>
      <div className="mb-3 flex gap-3">
        {Array.from({ length: cols }, (_, i) => (
          <Skeleton key={i} className="h-4 flex-1" />
        ))}
      </div>
      <div className="space-y-2">
        {Array.from({ length: rows }, (_, r) => (
          <Skeleton key={r} className="h-10 w-full" />
        ))}
      </div>
    </SkeletonSection>
  );
}

export function SkeletonCardList({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="mt-3 h-4 w-full" />
          <Skeleton className="mt-2 h-4 w-2/3" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonFormGrid({ fields = 4 }: { fields?: number }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {Array.from({ length: fields }, (_, i) => (
        <div key={i} className="space-y-2">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-10 w-full rounded-lg" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonTabs({ count = 2 }: { count?: number }) {
  return (
    <div className="mb-4 flex gap-2">
      {Array.from({ length: count }, (_, i) => (
        <Skeleton key={i} className="h-9 w-32 rounded-lg" />
      ))}
    </div>
  );
}

export function DashboardPageSkeleton() {
  return (
    <div className="mx-auto max-w-6xl space-y-6" aria-busy aria-label="Loading dashboard">
      <header className="space-y-2">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-40" />
      </header>
      <SkeletonMetricGrid count={4} />
      <div className="grid gap-6 lg:grid-cols-2">
        <SkeletonChart />
        <SkeletonChart />
      </div>
      <SkeletonChart tall />
    </div>
  );
}

export function AccountantHomePageSkeleton() {
  return (
    <div className="mx-auto max-w-5xl space-y-6" aria-busy aria-label="Loading accountant home">
      <SkeletonPageHeader />
      <Skeleton className="h-14 w-full rounded-xl" />
      <SkeletonSection>
        <Skeleton className="mb-6 h-4 w-72" />
        <div className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="rounded-lg border border-gray-100 bg-slate-50/50 p-4">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="mt-3 h-9 w-20" />
              <Skeleton className="mt-3 h-12 w-full" />
            </div>
          ))}
        </div>
      </SkeletonSection>
      <SkeletonSection>
        <SkeletonFormGrid fields={4} />
      </SkeletonSection>
    </div>
  );
}

export function SettingsPageSkeleton() {
  return (
    <div aria-busy aria-label="Loading settings">
      <SkeletonPageHeader />
      <div className="space-y-6">
        <SkeletonSection>
          <SkeletonFormGrid fields={2} />
        </SkeletonSection>
        <SkeletonSection>
          <SkeletonFormGrid fields={4} />
        </SkeletonSection>
        <SkeletonSection>
          <Skeleton className="h-32 w-full rounded-lg" />
        </SkeletonSection>
      </div>
    </div>
  );
}

export function OrgSettingsPageSkeleton() {
  return (
    <div aria-busy aria-label="Loading organization">
      <SkeletonPageHeader />
      <SkeletonSection>
        <Skeleton className="h-4 w-48" />
        <Skeleton className="mt-3 h-12 w-40 rounded-lg" />
      </SkeletonSection>
      <div className="mt-6">
        <SkeletonCardList count={2} />
      </div>
    </div>
  );
}

export function ForecastPageSkeleton() {
  return (
    <div className="mx-auto max-w-5xl space-y-6" aria-busy aria-label="Loading forecast">
      <SkeletonPageHeader />
      <SkeletonSection>
        <Skeleton className="h-10 w-48" />
      </SkeletonSection>
      <SkeletonSection>
        <div className="space-y-3">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-14 w-full rounded-lg" />
          ))}
        </div>
      </SkeletonSection>
      <SkeletonChart tall />
    </div>
  );
}

export function TablePageSkeleton({ tabs = false }: { tabs?: boolean }) {
  return (
    <div aria-busy aria-label="Loading page">
      <SkeletonPageHeader />
      {tabs ? <SkeletonTabs /> : null}
      <SkeletonTable />
    </div>
  );
}

export function EntriesPageSkeleton() {
  return (
    <div aria-busy aria-label="Loading entries">
      <SkeletonPageHeader />
      <SkeletonSection>
        <SkeletonFormGrid fields={3} />
        <Skeleton className="mt-4 h-32 w-full rounded-lg" />
      </SkeletonSection>
      <div className="mt-6">
        <SkeletonTable rows={3} cols={5} />
      </div>
    </div>
  );
}

export function ClassificationPageSkeleton() {
  return (
    <div className="mx-auto max-w-5xl space-y-6" aria-busy aria-label="Loading classification">
      <SkeletonPageHeader />
      <SkeletonSection>
        <Skeleton className="mb-4 h-4 w-full max-w-2xl" />
        <div className="space-y-3">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-20 w-full rounded-lg" />
          ))}
        </div>
      </SkeletonSection>
      <SkeletonSection>
        <SkeletonCardList count={3} />
      </SkeletonSection>
    </div>
  );
}

export function SidebarNavSkeleton() {
  return (
    <div className="space-y-6 px-1" aria-hidden>
      <div className="space-y-2">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-3 w-40" />
        <Skeleton className="h-3 w-28" />
      </div>
      <div className="space-y-2">
        <Skeleton className="h-8 w-full rounded-lg" />
        <Skeleton className="h-8 w-full rounded-lg" />
        <Skeleton className="h-8 w-full rounded-lg" />
        <Skeleton className="h-8 w-4/5 rounded-lg" />
      </div>
      <div className="space-y-2">
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-8 w-full rounded-lg" />
        <Skeleton className="h-8 w-full rounded-lg" />
      </div>
    </div>
  );
}

export function CenteredPageSkeleton({ label }: { label?: string }) {
  return (
    <div
      className="flex min-h-screen items-center justify-center bg-slate-50 p-6"
      aria-busy
      aria-label={label ?? "Loading"}
    >
      <div className="w-full max-w-sm space-y-4">
        <Skeleton className="mx-auto h-10 w-10 rounded-xl" />
        <Skeleton className="mx-auto h-5 w-40" />
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-4/5" />
      </div>
    </div>
  );
}

export function WorkspacePageSkeleton() {
  return (
    <div className="flex min-h-[40vh] items-start p-2" aria-busy aria-label="Loading workspace">
      <div className="mx-auto w-full max-w-6xl space-y-6">
        <SkeletonPageHeader />
        <SkeletonMetricGrid count={3} />
      </div>
    </div>
  );
}

export function HandoffPageSkeleton() {
  return (
    <div
      className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-50 p-6"
      aria-busy
      aria-label="Opening Financials"
    >
      <Skeleton className="h-10 w-10 rounded-full" />
      <Skeleton className="h-4 w-36" />
      <Skeleton className="h-3 w-52" />
    </div>
  );
}

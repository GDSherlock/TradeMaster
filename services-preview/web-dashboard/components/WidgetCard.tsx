import type { ReactNode } from "react";

type WidgetCardProps = {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
};

export function WidgetCard({ title, subtitle, action, children }: WidgetCardProps) {
  return (
    <section className="card-surface p-5" aria-label={title}>
      <header className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-ink">{title}</h2>
          {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

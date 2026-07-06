import { ReactNode } from 'react';

interface StatusCardProps {
  title: string;
  value: string | number;
  description?: string;
  icon: ReactNode;
}

export default function StatusCard({ title, value, description, icon }: StatusCardProps) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-center justify-between space-y-0 pb-2">
        <h3 className="text-sm font-medium tracking-tight text-zinc-600 dark:text-zinc-400">
          {title}
        </h3>
        <div className="text-zinc-400">
          {icon}
        </div>
      </div>
      <div className="mt-2">
        <div className="text-2xl font-bold text-zinc-900 dark:text-zinc-50">{value}</div>
        {description && (
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            {description}
          </p>
        )}
      </div>
    </div>
  );
}
import React from 'react';
import { cn } from '../../lib/utils';

export interface ProgressBarProps {
  value?: number | null; // 0 to 1, or null for indeterminate
  className?: string;
  color?: 'primary' | 'accent';
}

export const ProgressBar: React.FC<ProgressBarProps> = ({ value, className, color = 'primary' }) => {
  const isIndeterminate = value === null || value === undefined;
  const pct = isIndeterminate ? 0 : Math.min(100, Math.max(0, Math.round(value * 100)));

  const bgColors = {
    primary: 'bg-primary',
    accent: 'bg-accent',
  };

  return (
    <div className={cn('w-full bg-surface-card bg-slate-800/60 rounded-full h-2 overflow-hidden relative', className)}>
      {isIndeterminate ? (
        <div className={cn('h-full rounded-full w-1/3 animate-[indeterminate_1.5s_infinite_ease-in-out]', bgColors[color])} />
      ) : (
        <div
          className={cn('h-full rounded-full transition-all duration-300 ease-out', bgColors[color])}
          style={{ width: `${pct}%` }}
        />
      )}
    </div>
  );
};

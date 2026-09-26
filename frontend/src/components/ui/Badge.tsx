import React from 'react';
import { cn } from '../../lib/utils';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'selected' | 'dropped' | 'danger' | 'warning' | 'accent';
}

export const Badge: React.FC<BadgeProps> = ({ className, variant = 'default', children, ...props }) => {
  const variants = {
    default: 'bg-surface text-muted border-border',
    selected: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    dropped: 'bg-slate-500/15 text-slate-400 border-slate-500/30',
    danger: 'bg-rose-500/15 text-rose-400 border-rose-500/30',
    warning: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    accent: 'bg-sky-500/15 text-sky-400 border-sky-500/30',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border font-mono',
        variants[variant],
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
};

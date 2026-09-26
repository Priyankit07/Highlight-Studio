import React from 'react';
import { cn } from '../../lib/utils';

export interface SliderProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  valueDisplay?: string | number;
  description?: string;
  unit?: string;
}

export const Slider: React.FC<SliderProps> = ({
  label,
  valueDisplay,
  description,
  unit,
  className,
  value,
  ...props
}) => {
  return (
    <div className={cn('space-y-1.5', className)}>
      <div className="flex items-center justify-between text-xs">
        {label && <label className="font-medium text-text">{label}</label>}
        <span className="font-mono text-accent font-semibold tabular-nums">
          {valueDisplay !== undefined ? valueDisplay : value}
          {unit && ` ${unit}`}
        </span>
      </div>
      <input
        type="range"
        value={value}
        className="w-full h-1.5 bg-border rounded-lg appearance-none cursor-pointer accent-primary focus:outline-none"
        {...props}
      />
      {description && <p className="text-[11px] text-muted leading-tight">{description}</p>}
    </div>
  );
};

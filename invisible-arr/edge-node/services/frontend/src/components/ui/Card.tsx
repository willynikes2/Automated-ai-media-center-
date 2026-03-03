import type { HTMLAttributes } from 'react';

interface Props extends HTMLAttributes<HTMLDivElement> {
  hover?: boolean;
}

export function Card({ hover, className = '', children, ...props }: Props) {
  return (
    <div
      className={`bg-bg-secondary rounded-xl border border-white/5 ${
        hover ? 'hover:border-accent/30 hover:bg-bg-tertiary/50 transition-all cursor-pointer' : ''
      } ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

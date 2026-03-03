import { forwardRef, type InputHTMLAttributes } from 'react';

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, Props>(
  ({ label, error, className = '', ...props }, ref) => (
    <div>
      {label && <label className="block text-sm text-text-secondary mb-1">{label}</label>}
      <input
        ref={ref}
        className={`w-full bg-bg-tertiary border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-tertiary focus:outline-none focus:ring-2 focus:ring-accent/50 ${
          error ? 'border-status-failed' : 'border-white/10'
        } ${className}`}
        {...props}
      />
      {error && <p className="mt-1 text-xs text-status-failed">{error}</p>}
    </div>
  )
);
Input.displayName = 'Input';

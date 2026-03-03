import { create } from 'zustand';
import { useEffect } from 'react';
import { CheckCircle, XCircle, Info, X } from 'lucide-react';

interface Toast {
  id: string;
  message: string;
  type: 'success' | 'error' | 'info';
}

interface ToastStore {
  toasts: Toast[];
  add: (message: string, type?: Toast['type']) => void;
  remove: (id: string) => void;
}

export const useToastStore = create<ToastStore>()((set) => ({
  toasts: [],
  add: (message, type = 'info') => {
    const id = Date.now().toString();
    set((s) => ({ toasts: [...s.toasts, { id, message, type }] }));
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), 4000);
  },
  remove: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

export function toast(message: string, type: Toast['type'] = 'info') {
  useToastStore.getState().add(message, type);
}

const icons = { success: CheckCircle, error: XCircle, info: Info };
const colors = {
  success: 'border-status-available/30 bg-status-available/10',
  error: 'border-status-failed/30 bg-status-failed/10',
  info: 'border-accent/30 bg-accent/10',
};

export function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts);
  const remove = useToastStore((s) => s.remove);

  if (!toasts.length) return null;

  return (
    <div className="fixed bottom-20 md:bottom-6 right-4 z-50 flex flex-col gap-2 max-w-sm">
      {toasts.map((t) => {
        const Icon = icons[t.type];
        return (
          <div key={t.id} className={`glass rounded-lg p-3 flex items-start gap-3 border ${colors[t.type]} animate-in slide-in-from-right`}>
            <Icon className="h-5 w-5 shrink-0 mt-0.5" />
            <p className="text-sm flex-1">{t.message}</p>
            <button onClick={() => remove(t.id)} className="shrink-0 text-text-tertiary hover:text-text-primary">
              <X className="h-4 w-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
}

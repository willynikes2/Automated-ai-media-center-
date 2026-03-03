import { Navigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import { useSessionCheck } from '@/hooks/useAuth';

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const { isLoading } = useSessionCheck();

  if (!isAuthenticated) return <Navigate to="/login" replace />;

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-bg-primary">
        <div className="h-8 w-8 border-2 border-accent border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return <>{children}</>;
}

export function AdminRoute({ children }: { children: React.ReactNode }) {
  const role = useAuthStore((s) => s.user?.role);
  if (role !== 'admin') return <Navigate to="/" replace />;
  return <>{children}</>;
}

export function ResellerRoute({ children }: { children: React.ReactNode }) {
  const role = useAuthStore((s) => s.user?.role);
  if (role !== 'reseller' && role !== 'admin') return <Navigate to="/" replace />;
  return <>{children}</>;
}

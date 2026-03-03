import { QuickConnect } from '@/components/jellyfin/QuickConnect';
import { Link } from 'react-router-dom';
import { Zap, ArrowLeft } from 'lucide-react';

export function QuickConnectPage() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4 bg-bg-primary">
      <div className="w-full max-w-md">
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="h-10 w-10 rounded-xl bg-accent flex items-center justify-center">
            <Zap className="h-6 w-6 text-white" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight">AutoMedia</h1>
        </div>

        <QuickConnect />

        <div className="mt-6 text-center">
          <Link to="/login" className="inline-flex items-center gap-1 text-sm text-accent hover:text-accent-hover transition-colors">
            <ArrowLeft className="h-4 w-4" /> Back to Login
          </Link>
        </div>
      </div>
    </div>
  );
}

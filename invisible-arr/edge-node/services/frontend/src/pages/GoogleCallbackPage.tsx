import { useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useGoogleLogin } from '@/hooks/useAuth';

export function GoogleCallbackPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const googleLogin = useGoogleLogin();

  useEffect(() => {
    const code = searchParams.get('code');
    if (!code) {
      navigate('/login');
      return;
    }

    const redirectUri = `${window.location.origin}/auth/google/callback`;
    googleLogin.mutate({ code, redirectUri });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center">
        {googleLogin.isError ? (
          <>
            <p className="text-status-failed text-lg mb-4">Sign in failed</p>
            <button
              onClick={() => navigate('/login')}
              className="text-accent hover:text-accent-hover transition-colors"
            >
              Back to login
            </button>
          </>
        ) : (
          <>
            <div className="h-8 w-8 border-2 border-accent border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <p className="text-text-secondary">Signing in with Google...</p>
          </>
        )}
      </div>
    </div>
  );
}

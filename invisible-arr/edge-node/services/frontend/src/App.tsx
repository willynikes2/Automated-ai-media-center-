import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppShell } from '@/components/layout/AppShell';
import { ProtectedRoute, AdminRoute, ResellerRoute } from '@/components/layout/ProtectedRoute';
import { ToastContainer } from '@/components/ui/Toast';
import { LoginPage } from '@/pages/LoginPage';
import { RegisterPage } from '@/pages/RegisterPage';
import { DiscoverPage } from '@/pages/DiscoverPage';
import { SearchPage } from '@/pages/SearchPage';
import { MediaDetailPage } from '@/pages/MediaDetailPage';
import { RequestsPage } from '@/pages/RequestsPage';
import { LibraryPage } from '@/pages/LibraryPage';
import { IPTVPage } from '@/pages/IPTVPage';
import { SettingsPage } from '@/pages/SettingsPage';
import { ActivityPage } from '@/pages/ActivityPage';
import { AdminPage } from '@/pages/AdminPage';
import { QuickConnectPage } from '@/pages/QuickConnectPage';
import { LibraryItemPage } from '@/pages/LibraryItemPage';
import { SetupPage } from '@/pages/SetupPage';
import { ResellerPage } from '@/pages/ResellerPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          {/* Public routes */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/quick-connect" element={<QuickConnectPage />} />

          {/* Protected standalone routes (no AppShell) */}
          <Route path="/setup" element={<ProtectedRoute><SetupPage /></ProtectedRoute>} />

          {/* Protected routes */}
          <Route element={<ProtectedRoute><AppShell /></ProtectedRoute>}>
            <Route index element={<DiscoverPage />} />
            <Route path="search" element={<SearchPage />} />
            <Route path="media/:type/:id" element={<MediaDetailPage />} />
            <Route path="requests" element={<RequestsPage />} />
            <Route path="requests/:id" element={<RequestsPage />} />
            <Route path="activity" element={<ActivityPage />} />
            <Route path="library" element={<LibraryPage />} />
            <Route path="library/:id" element={<LibraryItemPage />} />
            <Route path="iptv" element={<IPTVPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="admin" element={<AdminRoute><AdminPage /></AdminRoute>} />
            <Route path="reseller" element={<ResellerRoute><ResellerPage /></ResellerRoute>} />
          </Route>
        </Routes>
        <ToastContainer />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

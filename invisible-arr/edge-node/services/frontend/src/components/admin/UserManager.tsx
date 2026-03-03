import { Card } from '@/components/ui/Card';
import { useJellyfinUsers } from '@/hooks/useAdmin';
import { Users } from 'lucide-react';

export function UserManager() {
  const { data: users, isLoading } = useJellyfinUsers();

  return (
    <Card className="p-4">
      <h3 className="font-semibold mb-3">Jellyfin Users</h3>
      {isLoading ? (
        <p className="text-sm text-text-secondary">Loading...</p>
      ) : !users?.length ? (
        <p className="text-sm text-text-secondary">No users found.</p>
      ) : (
        <div className="space-y-2">
          {users.map((u: any) => (
            <div key={u.Id} className="flex items-center gap-3 p-3 rounded-lg bg-bg-tertiary/50">
              <div className="h-8 w-8 rounded-full bg-accent/20 flex items-center justify-center">
                <span className="text-xs font-bold text-accent">{u.Name?.[0]?.toUpperCase()}</span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium">{u.Name}</p>
                <p className="text-xs text-text-tertiary">
                  {u.Policy?.IsAdministrator ? 'Admin' : 'User'}
                  {u.LastLoginDate && ` · Last login: ${new Date(u.LastLoginDate).toLocaleDateString()}`}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";
import {
  LayoutDashboard,
  Search,
  Activity,
  MessageSquare,
  Settings,
} from "lucide-react";

export const metadata: Metadata = {
  title: "Invisible Arr",
  description: "Automated media management",
};

const nav = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/search", label: "Search", icon: Search },
  { href: "/activity", label: "Activity", icon: Activity },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/settings", label: "Settings", icon: Settings },
];

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="flex h-screen overflow-hidden">
        {/* Sidebar */}
        <aside className="w-60 flex-shrink-0 bg-surface-800 border-r border-surface-600 flex flex-col">
          <div className="p-5 border-b border-surface-600">
            <h1 className="text-lg font-bold tracking-tight text-white">
              Invisible Arr
            </h1>
            <p className="text-xs text-gray-500 mt-0.5">Media Automation</p>
          </div>
          <nav className="flex-1 py-3 px-2 space-y-0.5">
            {nav.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-gray-400 hover:text-white hover:bg-surface-700 transition-colors"
              >
                <item.icon size={18} />
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="p-4 border-t border-surface-600 text-xs text-gray-600">
            v1.0.0
          </div>
        </aside>

        {/* Main content */}
        <main className="flex-1 overflow-y-auto">{children}</main>
      </body>
    </html>
  );
}

"use client";

import { MessageSquare } from "lucide-react";

export default function ChatPage() {
  return (
    <div className="p-8 max-w-4xl mx-auto">
      <h2 className="text-2xl font-bold text-white mb-6">Chat</h2>
      <div className="bg-surface-800 rounded-xl border border-surface-600 p-12 text-center">
        <MessageSquare size={48} className="mx-auto text-gray-600 mb-4" />
        <h3 className="text-lg font-medium text-gray-400 mb-2">
          Coming Soon
        </h3>
        <p className="text-sm text-gray-500 max-w-md mx-auto">
          Natural language chat interface for requesting media, checking status,
          and managing your library. This feature will be available in a future
          update.
        </p>
      </div>
    </div>
  );
}

'use client';

import { Plus, MessageSquare, Trash2 } from 'lucide-react';

export interface ChatSession {
  session_id: string;
  title: string;
  created_at: string;
}

interface ChatHistorySidebarProps {
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  onNewChat: () => void;
  onDeleteSession: (sessionId: string) => void; // <-- New Prop added
}

export default function ChatHistorySidebar({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
  onDeleteSession,
}: ChatHistorySidebarProps) {
  return (
    <div className="flex h-full w-64 shrink-0 flex-col border-r border-zinc-200 bg-zinc-50/50 p-4 pt-5 dark:border-zinc-800 dark:bg-zinc-900/50">
      
      {/* New Chat Button */}
      <button
        onClick={onNewChat}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-3 py-2.5 text-sm font-medium text-white shadow hover:bg-blue-700 active:scale-95 transition-all"
      >
        <Plus className="h-4 w-4" />
        New Chat
      </button>

      {/* Recent Chats List */}
      <div className="mt-5 flex-1 overflow-y-auto pr-1">
        <h3 className="px-1 text-[11px] font-bold tracking-wider text-zinc-400 uppercase">
          Recent Chats
        </h3>
        <div className="mt-2 space-y-1">
          {sessions.length === 0 ? (
            <p className="px-1 text-xs text-zinc-400 italic">No previous chats</p>
          ) : (
            sessions.map((session) => {
              const isActive = activeSessionId === session.session_id;
              return (
                // Used 'group' class so delete icon appears only on hover
                <div
                  key={session.session_id}
                  className={`group flex w-full items-center justify-between rounded-md px-1.5 py-1.5 text-xs transition-colors ${
                    isActive
                      ? 'bg-zinc-200/80 font-medium text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100'
                      : 'text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800/50 dark:hover:text-zinc-200'
                  }`}
                >
                  <button
                    onClick={() => onSelectSession(session.session_id)}
                    className="flex flex-1 items-center gap-2 overflow-hidden text-left px-1 py-1"
                  >
                    <MessageSquare className="h-3.5 w-3.5 shrink-0 text-zinc-400" />
                    <span className="truncate">{session.title}</span>
                  </button>
                  
                  {/* Delete Button (Appears on Hover) */}
                  <button
                    onClick={(e) => {
                      e.stopPropagation(); // Prevents clicking the row when clicking delete
                      onDeleteSession(session.session_id);
                    }}
                    className={`p-1.5 rounded-md transition-opacity hover:bg-zinc-300 dark:hover:bg-zinc-700 ${
                      isActive ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                    }`}
                    title="Delete Chat"
                  >
                    <Trash2 className="h-3.5 w-3.5 text-zinc-500 hover:text-red-600 transition-colors" />
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
'use client';
import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { 
  LayoutDashboard, 
  FileSpreadsheet, 
  FileText, 
  UploadCloud, 
  ListTodo,
  Search // Added for Module 4 Query Engine
} from 'lucide-react';
import { getApiUrl } from '@/lib/api';

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'CSV Dataset', href: '/csv', icon: FileSpreadsheet },
  { name: 'PDF Docs', href: '/pdf', icon: FileText },
  { name: 'Upload Hub', href: '/upload', icon: UploadCloud },
  { name: 'Task Monitor', href: '/tasks', icon: ListTodo },
  { name: 'Query Engine', href: '/query', icon: Search }, // Added link route
];

export default function Sidebar() {
  const pathname = usePathname();
  const [isOnline, setIsOnline] = useState<boolean | null>(null);

  // Health Check Effect: Polls every 30 seconds
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const apiRoot = getApiUrl().replace(/\/api\/v1$/, '');
        const res = await fetch(`${apiRoot}/`);
        setIsOnline(res.ok);
      } catch {
        setIsOnline(false);
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex h-full w-64 flex-col border-r border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-center gap-2 px-2 py-4">
        <span className="text-lg font-bold tracking-tight text-zinc-900 dark:text-zinc-50">
          AI Training
        </span>
      </div>
      
      <nav className="flex-1 space-y-1 py-4">
        {navigation.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.name}
              href={item.href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-50'
                  : 'text-zinc-600 hover:bg-zinc-50 hover:text-zinc-950 dark:text-zinc-400 dark:hover:bg-zinc-900 dark:hover:text-zinc-50'
              }`}
            >
              <item.icon className="h-4 w-4" />
              {item.name}
            </Link>
          );
        })}
      </nav>

      {/* Backend Health Status Indicator */}
      <div className="border-t border-zinc-200 dark:border-zinc-800 pt-4 px-2">
        <div className="flex items-center gap-2 text-xs text-zinc-500">
          <div className={`h-2 w-2 rounded-full ${
            isOnline === null ? 'bg-zinc-400' : 
            isOnline ? 'bg-emerald-500' : 'bg-red-500'
          }`} />
          {isOnline === null ? 'Checking status...' : isOnline ? 'Backend Online' : 'Backend Offline'}
        </div>
      </div>
    </div>
  );
}
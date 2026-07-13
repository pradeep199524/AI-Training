"use client";

import React, { useState, useEffect } from 'react';

// Define the shape of our task data
interface Task {
  task_id: string;
  filename: string;
  status: string;
  result?: any;
  timestamp: number;
}

export default function TaskMonitorPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);

  // 1. Load tasks from LocalStorage on mount with deduplication
  useEffect(() => {
    const savedTasks = JSON.parse(localStorage.getItem('ingestion_tasks') || '[]');
    
    // Explicitly define Map<string, Task> to satisfy TypeScript
    const uniqueTasks = Array.from(
      new Map<string, Task>(savedTasks.map((t: Task) => [t.task_id, t])).values()
    );
    
    setTasks(uniqueTasks);
    setLoading(false);
  }, []);

  // 2. Poll backend for updates on active tasks
  useEffect(() => {
    // Filter tasks that need checking
    const activeTasks = tasks.filter(t => ['PENDING', 'STARTED'].includes(t.status) || !t.status);
    
    if (activeTasks.length === 0) return;

    // Use an interval to poll every 3 seconds
    const interval = setInterval(async () => {
      // Use for...of loop to handle requests sequentially
      for (const task of activeTasks) {
        try {
          const res = await fetch(`http://127.0.0.1:8000/api/v1/tasks/${task.task_id}`);
          
          if (res.ok) {
            const data = await res.json();
            updateTaskInState(task.task_id, data.status, data.result);
          } else {
            console.warn(`Task ${task.task_id} returned status: ${res.status}`);
          }
        } catch (error) {
          console.error(`Connection failed for ${task.task_id}. Is the backend running?`);
        }
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [tasks]);

  const updateTaskInState = (id: string, newStatus: string, result: any) => {
    setTasks(prevTasks => {
      const updated = prevTasks.map(t => 
        t.task_id === id ? { ...t, status: newStatus, result } : t
      );
      localStorage.setItem('ingestion_tasks', JSON.stringify(updated));
      return updated;
    });
  };

  const clearHistory = () => {
    setTasks([]);
    localStorage.removeItem('ingestion_tasks');
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'SUCCESS': return <span className="bg-green-500/20 text-green-400 px-2 py-1 rounded text-xs font-semibold">SUCCESS</span>;
      case 'FAILURE': return <span className="bg-red-500/20 text-red-400 px-2 py-1 rounded text-xs font-semibold">FAILURE</span>;
      case 'STARTED':
      case 'PENDING': return <span className="bg-blue-500/20 text-blue-400 px-2 py-1 rounded text-xs font-semibold animate-pulse">PROCESSING</span>;
      default: return <span className="bg-gray-500/20 text-gray-400 px-2 py-1 rounded text-xs font-semibold">{status || 'UNKNOWN'}</span>;
    }
  };

  if (loading) return null;

  return (
    <div className="p-8 max-w-6xl mx-auto text-slate-200">
      <div className="mb-8 flex justify-between items-end">
        <div>
          <h1 className="text-sm font-bold tracking-widest text-slate-500 uppercase mb-2">System Operations</h1>
          <h2 className="text-3xl font-semibold text-white">Task Monitor</h2>
          <p className="text-slate-400 mt-2">Track background file processing and ingestion queues.</p>
        </div>
        <button onClick={clearHistory} className="text-sm text-slate-400 hover:text-white transition-colors">
          Clear History
        </button>
      </div>

      {/* Task List */}
      <div className="bg-[#11131e] rounded-xl border border-slate-800 overflow-hidden">
        {tasks.length === 0 ? (
          <div className="p-8 text-center text-slate-500">
            No tasks found in local history. Upload a file to see it here.
          </div>
        ) : (
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-900/50 border-b border-slate-800 text-slate-400 text-sm">
                <th className="p-4 font-medium">Filename</th>
                <th className="p-4 font-medium">Task ID</th>
                <th className="p-4 font-medium">Status</th>
                <th className="p-4 font-medium">Time Added</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {tasks.map((task) => (
                <tr key={task.task_id} className="hover:bg-slate-800/30 transition-colors">
                  <td className="p-4 text-white font-medium">{task.filename}</td>
                  <td className="p-4 text-slate-400 text-sm font-mono">{task.task_id}</td>
                  <td className="p-4">{getStatusBadge(task.status)}</td>
                  <td className="p-4 text-slate-500 text-sm">
                    {new Date(task.timestamp).toLocaleTimeString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
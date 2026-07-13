'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { apiPath } from '@/lib/api';

type Ticket = {
  id: number;
  title: string;
  customer_name: string;
  status: string;
};

type DocumentSummary = {
  id: number;
  filename: string;
  page_count?: number;
  paragraph_count?: number;
};

export default function DashboardPage() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [totalDocuments, setTotalDocuments] = useState(0);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  
  // Track which file is pending deletion to show the custom UI modal
  const [fileToDelete, setFileToDelete] = useState<string | null>(null);

  const fetchDashboard = async () => {
    setLoading(true);
    try {
      const [documentsRes, ticketsRes] = await Promise.all([
        fetch(apiPath('documents?limit=10')),
        fetch(apiPath('tickets?limit=10')),
      ]);

      const documentsJson = await documentsRes.json().catch(() => ({}));
      const ticketsJson = await ticketsRes.json().catch(() => ({}));

      setDocuments((documentsJson.data || []) as DocumentSummary[]);
      setTotalDocuments(documentsJson.count || ((documentsJson.data || []).length));
      setTickets((ticketsJson.data || []) as Ticket[]);
    } catch (err) {
      console.error(err);
      setError('Unable to load dashboard data.');
    } finally {
      setLoading(false);
    }
  };

  // Executes the actual deletion block after user confirms via the custom modal
  const executeDelete = async () => {
    if (!fileToDelete) return;

    try {
      const res = await fetch(apiPath(`files/${encodeURIComponent(fileToDelete)}`), {
        method: 'DELETE',
      });

      if (!res.ok) {
        throw new Error('Failed to delete the file.');
      }

      await fetchDashboard();
    } catch (err) {
      console.error(err);
      alert('Error deleting document. Please verify your backend API configuration.');
    } finally {
      setFileToDelete(null);
    }
  };

  useEffect(() => {
    fetchDashboard();

    const handler = () => fetchDashboard();
    if (typeof window !== 'undefined') {
      window.addEventListener('documentsUpdated', handler);
    }
    return () => {
      if (typeof window !== 'undefined') {
        window.removeEventListener('documentsUpdated', handler);
      }
    };
  }, []);

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100 relative">
      <div className="mx-auto flex min-h-screen max-w-7xl flex-col gap-8 px-6 py-8 lg:px-8">
        <div className="flex flex-col gap-4 rounded-3xl bg-slate-900 p-8 shadow-xl shadow-slate-950/40">
          <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-sm uppercase tracking-[0.3em] text-slate-500">Module 3 dashboard</p>
              <h1 className="mt-2 text-4xl font-semibold tracking-tight text-white">Ingestion & Document Operations</h1>
              <p className="mt-3 max-w-2xl text-slate-400">Browse uploaded data, inspect extracted content, and manage a simple business process from one polished UI.</p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Link href="/upload" className="rounded-2xl bg-sky-500 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-sky-500/20 transition hover:bg-sky-400">
                Upload Hub
              </Link>
              <Link href="/csv" className="rounded-2xl bg-emerald-500 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-emerald-500/20 transition hover:bg-emerald-400">
                CSV Records
              </Link>
              <Link href="/pdf" className="rounded-2xl bg-violet-500 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-violet-500/20 transition hover:bg-violet-400">
                PDF Insights
              </Link>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <div className="rounded-3xl bg-slate-950/90 p-6">
              <p className="text-sm text-slate-400">Documents Loaded</p>
              <p className="mt-4 text-4xl font-semibold text-white">{totalDocuments}</p>
            </div>
            <div className="rounded-3xl bg-slate-950/90 p-6">
              <p className="text-sm text-slate-400">Tickets in System</p>
              <p className="mt-4 text-4xl font-semibold text-white">{tickets.length}</p>
            </div>
            <div className="rounded-3xl bg-slate-950/90 p-6">
              <p className="text-sm text-slate-400">Backend Status</p>
              <p className="mt-4 text-4xl font-semibold text-white">{loading ? 'Refreshing…' : 'Online'}</p>
            </div>
          </div>
        </div>

        {error ? (
          <div className="rounded-3xl bg-rose-500/10 border border-rose-500/20 p-6 text-rose-100">{error}</div>
        ) : null}

        <div className="grid gap-6 xl:grid-cols-[1.3fr_0.7fr]">
          <section className="rounded-3xl bg-slate-900 p-8 shadow-xl shadow-slate-950/30">
            <div className="mb-6 flex items-center justify-between gap-4">
              <div>
                <h2 className="text-xl font-semibold text-white">Recent Documents</h2>
                <p className="mt-2 text-sm text-slate-400">Latest ingestion results and metadata.</p>
              </div>
              <button
                onClick={() => fetchDashboard()}
                className="rounded-2xl bg-slate-800 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-700"
              >
                Refresh
              </button>
            </div>

            {/* Grid-based document layout with fixed alignments */}
            <div className="rounded-3xl border border-slate-800 bg-slate-950 p-5">
              <div className="grid grid-cols-12 gap-4 pb-3 border-b border-slate-800 text-xs font-semibold uppercase tracking-wider text-slate-500 px-2">
                <div className="col-span-5">Filename</div>
                <div className="col-span-2 text-center">Pages</div>
                <div className="col-span-3 text-center">Paragraphs</div>
                <div className="col-span-2 text-right">Actions</div>
              </div>

              <div className="divide-y divide-slate-800/60 max-h-[420px] overflow-y-auto pr-1 custom-scrollbar">
                {documents.length === 0 ? (
                  <div className="py-12 text-center text-sm text-slate-500">
                    No documents available yet.
                  </div>
                ) : (
                  documents.map((document) => (
                    <div key={document.id} className="grid grid-cols-12 gap-4 items-center py-3.5 text-sm px-2 hover:bg-slate-900/30 rounded-xl transition-colors">
                      <div className="col-span-5 font-medium text-slate-200 truncate pr-2" title={document.filename}>
                        {document.filename}
                      </div>
                      <div className="col-span-2 text-center text-slate-300 font-mono">
                        {document.page_count ?? '-'}
                      </div>
                      <div className="col-span-3 text-center text-slate-300 font-mono">
                        {document.paragraph_count ?? '-'}
                      </div>
                      <div className="col-span-2 text-right">
                        <button
                          onClick={() => setFileToDelete(document.filename)}
                          className="rounded-xl bg-rose-500/10 px-3 py-1.5 text-xs font-semibold text-rose-400 transition hover:bg-rose-500 hover:text-white"
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </section>

          <section className="rounded-3xl bg-slate-900 p-8 shadow-xl shadow-slate-950/30">
            <h2 className="text-xl font-semibold text-white">Recent Tickets</h2>
            <p className="mt-2 text-sm text-slate-400">Track the latest business records from the API.</p>
            <div className="mt-6 space-y-4 max-h-[490px] overflow-y-auto pr-1 custom-scrollbar">
              {tickets.length === 0 ? (
                <div className="rounded-3xl border border-dashed border-slate-800 bg-slate-950 p-8 text-center text-slate-500">
                  No tickets found.
                </div>
              ) : (
                tickets.map((ticket) => (
                  <article key={ticket.id} className="rounded-2xl border border-slate-800 bg-slate-950 p-5 hover:border-slate-700 transition-colors">
                    <div className="flex items-start justify-between gap-4">
                      <p className="font-semibold text-slate-200 leading-tight">{ticket.title}</p>
                      <span className="shrink-0 rounded-full bg-slate-800 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-[0.12em] text-slate-300 border border-slate-700/50">
                        {ticket.status}
                      </span>
                    </div>
                    <p className="mt-2.5 text-xs text-slate-400 font-medium">Assigned to: {ticket.customer_name}</p>
                  </article>
                ))
              )}
            </div>
          </section>
        </div>
      </div>

      {/* CONFIRMATION MODAL */}
      {fileToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-3xl bg-slate-900 border border-slate-800 p-6 shadow-2xl shadow-slate-950/50">
            <h3 className="text-xl font-semibold text-white tracking-tight">
              Confirm Permanent Deletion
            </h3>
            <p className="mt-3 text-sm text-slate-400 leading-relaxed">
              Are you sure you want to permanently delete <span className="text-slate-200 font-mono bg-slate-950 px-1.5 py-0.5 rounded border border-slate-800 break-all inline-block">{fileToDelete}</span>? This action clears all extracted row content and paragraphs from the database.
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => setFileToDelete(null)}
                className="rounded-2xl bg-slate-800 px-5 py-2.5 text-sm font-semibold text-slate-300 transition hover:bg-slate-700"
              >
                Cancel
              </button>
              <button
                onClick={executeDelete}
                className="rounded-2xl bg-rose-500 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-rose-500/20 transition hover:bg-rose-400"
              >
                Delete File
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
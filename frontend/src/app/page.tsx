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
      // Clear target string to close the custom modal UI view
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

        <div className="grid gap-6 xl:grid-cols-[0.95fr_0.75fr]">
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
            <div className="overflow-x-auto rounded-3xl border border-slate-800 bg-slate-950 p-4">
              <table className="min-w-full text-left text-sm text-slate-300">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-500">
                    <th className="py-3">Filename</th>
                    <th className="py-3">Pages</th>
                    <th className="py-3">Paragraphs</th>
                    <th className="py-3">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="py-8 text-center text-slate-500">No documents available yet.</td>
                    </tr>
                  ) : (
                    documents.map((document) => (
                      <tr key={document.id} className="border-b border-slate-800 last:border-b-0">
                        <td className="py-4 text-slate-100">{document.filename}</td>
                        <td className="py-4 text-slate-100">{document.page_count ?? '-'}</td>
                        <td className="py-4 text-slate-100">{document.paragraph_count ?? '-'}</td>
                        <td className="py-4">
                          <button
                            onClick={() => setFileToDelete(document.filename)}
                            className="rounded-xl bg-rose-500/10 px-3 py-1.5 text-xs font-semibold text-rose-400 transition hover:bg-rose-500 hover:text-white"
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-3xl bg-slate-900 p-8 shadow-xl shadow-slate-950/30">
            <h2 className="text-xl font-semibold text-white">Recent Tickets</h2>
            <p className="mt-2 text-sm text-slate-400">Track the latest business records from the API.</p>
            <div className="mt-6 space-y-4">
              {tickets.length === 0 ? (
                <div className="rounded-3xl border border-dashed border-slate-800 bg-slate-950 p-8 text-center text-slate-500">No tickets found.</div>
              ) : (
                tickets.map((ticket) => (
                  <article key={ticket.id} className="rounded-3xl border border-slate-800 bg-slate-950 p-5">
                    <div className="flex items-center justify-between gap-4">
                      <p className="font-semibold text-white">{ticket.title}</p>
                      <span className="rounded-full bg-slate-800 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-slate-300">{ticket.status}</span>
                    </div>
                    <p className="mt-2 text-sm text-slate-400">{ticket.customer_name}</p>
                  </article>
                ))
              )}
            </div>
          </section>
        </div>
      </div>

      {/* CUSTOM CONFIRMATION MODAL UI ELEMENT */}
      {fileToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-sm animate-fadeIn">
          <div className="w-full max-w-md rounded-3xl bg-slate-900 border border-slate-800 p-6 shadow-2xl shadow-slate-950/50 transform scale-100 transition-all">
            <h3 className="text-xl font-semibold text-white tracking-tight">
              Confirm Permanent Deletion
            </h3>
            
            <p className="mt-3 text-sm text-slate-400 leading-relaxed">
              Are you sure you want to permanently delete <span className="text-slate-200 font-mono bg-slate-950 px-1.5 py-0.5 rounded border border-slate-800">{fileToDelete}</span>? This action clears all extracted row content and paragraphs from the database.
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
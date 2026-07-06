'use client';

import { useState, useEffect } from 'react';
import { apiPath } from '@/lib/api';

interface PdfParagraph {
  source_pdf: string;
  page: number;
  paragraph_index: number;
  text: string;
}

export default function PdfInspectorPage() {
  const [fileTarget, setFileTarget] = useState('');
  const [availableFiles, setAvailableFiles] = useState<string[]>([]);
  const [pageFilter, setPageFilter] = useState('');
  const [records, setRecords] = useState<PdfParagraph[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const pullTrace = async () => {
    setLoading(true);
    setError('');

    try {
      const res = await fetch(apiPath(`records/pdf?source_file=${encodeURIComponent(fileTarget)}&limit=15`));
      if (!res.ok) {
        throw new Error('Unable to load PDF paragraphs.');
      }
      const payload = await res.json();
      setRecords(payload.data || []);
    } catch (err) {
      console.error(err);
      setError('Unable to load PDF paragraphs.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const loadFiles = async () => {
      try {
        const res = await fetch(apiPath('files?extensions=pdf'));
        const payload = await res.json().catch(() => ({}));
        setAvailableFiles(payload.data || []);
      } catch (e) {
        // ignore
      }
    };
    loadFiles();
  }, []);

  const filteredRecords = records.filter((record) => {
    if (!pageFilter) {
      return true;
    }
    return record.page.toString() === pageFilter;
  });

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-6xl px-6 py-10 lg:px-8">
        <header className="mb-8 space-y-3">
          <p className="text-sm uppercase tracking-[0.3em] text-slate-500">Document Inspection</p>
          <h1 className="text-4xl font-semibold tracking-tight text-white">PDF Paragraph Browser</h1>
          <p className="max-w-2xl text-slate-400">Search by PDF filename, filter by page, and review extracted text content here.</p>
        </header>

        <section className="mb-8 rounded-3xl bg-slate-900 p-6 shadow-xl shadow-slate-950/30">
          <div className="grid gap-4 lg:grid-cols-[1.4fr_0.8fr_0.85fr]">
            <label className="block">
              <span className="text-sm text-slate-400">PDF source filename</span>
              {/* Added relative wrapper for positioning custom arrow */}
              <div className="relative mt-2">
                <select
                  value={fileTarget}
                  onChange={(e) => setFileTarget(e.target.value)}
                  className="w-full appearance-none rounded-3xl border border-slate-700 bg-slate-950 pl-4 pr-10 py-3 text-white outline-none transition focus:border-sky-400"
                >
                  <option value="" disabled>
                    Select PDF file...
                  </option>
                  {availableFiles.map((f) => (
                    <option key={f} value={f}>
                      {f}
                    </option>
                  ))}
                </select>
                {/* SVG Chevron Arrow UI Sync */}
                <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-4 text-slate-400">
                  <svg
                    className="h-4 w-4"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth="2.5"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </div>
            </label>
            <label className="block">
              <span className="text-sm text-slate-400">Page filter</span>
              <input
                type="number"
                min="1"
                value={pageFilter}
                onChange={(e) => setPageFilter(e.target.value)}
                placeholder="Page #"
                className="mt-2 w-full rounded-3xl border border-slate-700 bg-slate-950 px-4 py-3 text-white outline-none transition focus:border-sky-400"
              />
            </label>
            <div className="flex items-end">
              <button
                onClick={pullTrace}
                disabled={loading}
                className="inline-flex h-14 items-center justify-center rounded-3xl bg-violet-500 px-6 text-sm font-semibold text-white transition hover:bg-violet-400 disabled:cursor-not-allowed disabled:bg-slate-700"
              >
                {loading ? 'Fetching…' : 'Load Paragraphs'}
              </button>
            </div>
          </div>
          {error ? <p className="mt-4 text-sm text-rose-400">{error}</p> : null}
        </section>

        <section className="grid gap-4">
          {filteredRecords.length === 0 ? (
            <div className="rounded-3xl border border-slate-800 bg-slate-950 p-10 text-center text-slate-500">
              {records.length === 0 ? 'No paragraph records loaded yet.' : 'No paragraph records match the current page filter.'}
            </div>
          ) : (
            filteredRecords.map((record, idx) => (
              <article key={`${record.source_pdf}-${record.page}-${record.paragraph_index}-${idx}`} className="rounded-3xl border border-slate-800 bg-slate-950 p-6 shadow-sm">
                <div className="mb-4 flex flex-wrap items-center gap-3 text-sm text-slate-400">
                  <span>{record.source_pdf}</span>
                  <span className="rounded-full bg-slate-800 px-3 py-1">Page {record.page}</span>
                  <span className="rounded-full bg-slate-800 px-3 py-1">Paragraph {record.paragraph_index}</span>
                </div>
                <p className="text-slate-200 leading-7">{record.text}</p>
              </article>
            ))
          )}
        </section>
      </div>
    </main>
  );
}
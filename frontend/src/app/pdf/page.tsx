'use client';

import { useState, useEffect } from 'react';
import { apiPath } from '@/lib/api';

interface PdfParagraph {
  source_pdf: string;
  page: number;
  paragraph_index: number;
  text: string;
  // Included to support the nested JSONB table metrics response
  extracted_tables?: string[][][]; 
}

export default function PdfInspectorPage() {
  const [fileTarget, setFileTarget] = useState('');
  const [availableFiles, setAvailableFiles] = useState<string[]>([]);
  const [pageFilter, setPageFilter] = useState('');
  const [records, setRecords] = useState<PdfParagraph[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const pullTrace = async () => {
    if (!fileTarget) {
      setError('Please select a PDF file first.');
      return;
    }
    setLoading(true);
    setError('');

    try {
      // Build query parameters. If a page filter exists, explicitly pass the 0-indexed integer to the backend lookup engine
      let queryUrl = `records/pdf?source_file=${encodeURIComponent(fileTarget)}&limit=100`;
      if (pageFilter) {
        const backendPageIndex = Math.max(0, parseInt(pageFilter, 10) - 1);
        queryUrl += `&page=${backendPageIndex}`;
      }

      const res = await fetch(apiPath(queryUrl));
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

  // Client-side array safety verification mapping 1-based UI logic to 0-based database indexing structure safely
  const filteredRecords = records.filter((record) => {
    if (!pageFilter) {
      return true;
    }
    const targetPageNum = parseInt(pageFilter, 10);
    if (isNaN(targetPageNum)) return true;
    
    return record.page === targetPageNum - 1;
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
                className="w-full inline-flex h-14 items-center justify-center rounded-3xl bg-violet-500 px-6 text-sm font-semibold text-white transition hover:bg-violet-400 disabled:cursor-not-allowed disabled:bg-slate-700"
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
              <article key={`${record.source_pdf}-${record.page}-${record.paragraph_index}-${idx}`} className="rounded-3xl border border-slate-800 bg-slate-950 p-6 shadow-sm space-y-4">
                <div className="flex flex-wrap items-center gap-3 text-sm text-slate-400">
                  <span className="font-medium text-slate-300">{record.source_pdf}</span>
                  {/* Visually map back to a 1-based page index format inside the row header component output */}
                  <span className="rounded-full bg-slate-800 px-3 py-1 text-xs font-semibold text-slate-200">
                    Page {record.page + 1}
                  </span>
                  <span className="rounded-full bg-slate-800 px-3 py-1 text-xs">Paragraph {record.paragraph_index}</span>
                </div>
                
                <p className="text-slate-200 leading-7">{record.text}</p>

                {/* Relational Tabular Data Block Renderer */}
                {record.extracted_tables && record.extracted_tables.length > 0 && (
                  <div className="mt-4 rounded-2xl border border-slate-800 bg-slate-900/50 p-4">
                    <div className="mb-3 flex items-center gap-2">
                      <span className="h-2 w-2 rounded-full bg-cyan-400 animate-pulse"></span>
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-cyan-400">Isolated Table Matrix</h3>
                    </div>
                    {record.extracted_tables.map((table, tIdx) => (
                      <div key={tIdx} className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950">
                        <table className="min-w-full text-xs text-left text-slate-300">
                          <thead>
                            <tr className="border-b border-slate-800 bg-slate-900 text-slate-400">
                              {table[0]?.map((headerCell, hIdx) => (
                                <th key={hIdx} className="px-4 py-3 font-semibold">{headerCell}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {table.slice(1).map((rowCells, rIdx) => (
                              <tr key={rIdx} className="border-b border-slate-900/60 hover:bg-slate-900/40 transition">
                                {rowCells.map((cell, cIdx) => (
                                  <td key={cIdx} className="px-4 py-2.5 font-mono text-slate-300">{cell}</td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ))}
                  </div>
                )}
              </article>
            ))
          )}
        </section>
      </div>
    </main>
  );
}
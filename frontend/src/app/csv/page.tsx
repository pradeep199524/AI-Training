'use client';

import { useState, useEffect } from 'react';
import { apiPath } from '@/lib/api';

type CsvRecord = {
  id: number;
  source: string;
  row: Record<string, unknown>;
};

export default function CsvPage() {
  const [fileTarget, setFileTarget] = useState('');
  const [availableFiles, setAvailableFiles] = useState<string[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [dataRows, setDataRows] = useState<CsvRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const pullCsvTrace = async () => {
    setLoading(true);
    setError('');

    try {
      // Pulls up to 100 records at once so you can scroll them
      const res = await fetch(apiPath(`records/csv?source_file=${encodeURIComponent(fileTarget)}&limit=100`));
      if (!res.ok) {
        throw new Error('Unable to fetch CSV records.');
      }
      const payload = await res.json();
      setDataRows(payload.data || []);
    } catch (err) {
      console.error(err);
      setError('Unable to fetch CSV records.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const loadFiles = async () => {
      try {
        const res = await fetch(apiPath('files?extensions=csv'));
        const payload = await res.json().catch(() => ({}));
        setAvailableFiles(payload.data || []);
      } catch (e) {
        // ignore
      }
    };
    loadFiles();
  }, []);

  // 🛠️ FIXED: Dynamic column matching instead of hardcoded fields
  const visibleRows = dataRows.filter((item) => {
    if (!searchTerm) return true; // Show everything if search box is blank
    
    const search = searchTerm.toLowerCase();

    // Loop through every field/value inside the row object dynamically
    return Object.values(item.row).some((value) => {
      if (value === null || value === undefined) return false;
      return String(value).toLowerCase().includes(search);
    });
  });

  const deleteRecord = async (rowId: number) => {
    if (!confirm('Delete this record?')) return;

    try {
      const res = await fetch(apiPath(`records/csv/${rowId}`), { method: 'DELETE' });
      if (!res.ok) {
        throw new Error('Delete request failed.');
      }
      await pullCsvTrace();
    } catch (err) {
      console.error(err);
      setError('Failed to delete record.');
    }
  };

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-6xl px-6 py-10 lg:px-8">
        <header className="mb-8 space-y-3">
          <p className="text-sm uppercase tracking-[0.3em] text-slate-500">Data Exploration</p>
          <h1 className="text-4xl font-semibold tracking-tight text-white">CSV Record Browser</h1>
          <p className="max-w-2xl text-slate-400">Browse ingested table data, filter rows, and manage records directly from the frontend.</p>
        </header>

        <section className="mb-8 rounded-3xl bg-slate-900 p-6 shadow-xl shadow-slate-950/30">
          <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr_0.8fr]">
            <label className="block">
              <span className="text-sm text-slate-400">Source CSV filename</span>
              <div className="relative mt-2">
                <select
                  value={fileTarget}
                  onChange={(e) => setFileTarget(e.target.value)}
                  className="w-full appearance-none rounded-3xl border border-slate-700 bg-slate-950 pl-4 pr-10 py-3 text-white outline-none transition focus:border-sky-400"
                >
                  <option value="" disabled>
                    Select CSV file...
                  </option>
                  {availableFiles.map((f) => (
                    <option key={f} value={f} className="bg-slate-950 text-white">
                      {f}
                    </option>
                  ))}
                </select>
                <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-4 text-slate-400">
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </div>
            </label>
            
            <label className="block">
              <span className="text-sm text-slate-400">Filter rows</span>
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search row content"
                className="mt-2 w-full rounded-3xl border border-slate-700 bg-slate-950 px-4 py-3 text-white outline-none transition focus:border-sky-400"
              />
            </label>
            <div className="flex items-end">
              <button
                onClick={pullCsvTrace}
                disabled={loading}
                className="inline-flex h-14 w-full items-center justify-center rounded-3xl bg-sky-500 px-6 text-sm font-semibold text-white transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:bg-slate-700"
              >
                {loading ? 'Loading…' : 'Load CSV Records'}
              </button>
            </div>
          </div>
          {error ? <p className="mt-4 text-sm text-rose-400">{error}</p> : null}
        </section>

        <section className="rounded-3xl bg-slate-900 p-6 shadow-xl shadow-slate-950/30">
          <div className="mb-4 flex items-center justify-between gap-4">
            <div>
              <h2 className="text-xl font-semibold text-white">Recent Rows</h2>
              <p className="mt-1 text-sm text-slate-400">Interact with ingested CSV data and remove stale rows.</p>
            </div>
            <span className="rounded-full bg-slate-800 px-3 py-1 text-xs uppercase tracking-[0.18em] text-slate-400">{visibleRows.length} visible</span>
          </div>
          
          <div className="max-h-[650px] overflow-y-auto rounded-3xl border border-slate-800 bg-slate-950 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent">
            <table className="min-w-full table-fixed divide-y divide-slate-800 text-left text-sm text-slate-200">
              <thead className="bg-slate-950 sticky top-0 z-10 text-slate-400 shadow-sm">
                <tr>
                  <th className="w-1/4 px-6 py-4 align-top">Source</th>
                  <th className="w-3/5 px-6 py-4 align-top">Row JSON</th>
                  <th className="w-24 px-6 py-4 align-top text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {visibleRows.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="px-6 py-10 text-center text-slate-500">
                      {dataRows.length === 0 ? 'No CSV rows loaded yet.' : 'No rows match the current filter.'}
                    </td>
                  </tr>
                ) : (
                  visibleRows.map((item) => (
                    <tr key={item.id} className="hover:bg-slate-900/30 transition-colors">
                      <td className="px-6 py-4 align-top break-all text-slate-200" title={item.source}>
                        {item.source}
                      </td>
                      <td className="px-6 py-4 align-top">
                        <pre className="max-h-56 w-full overflow-y-auto whitespace-pre-wrap break-all rounded-lg bg-slate-900/80 px-3 py-2 font-mono text-xs text-emerald-400 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent">
                          {JSON.stringify(item.row, null, 2)}
                        </pre>
                      </td>
                      <td className="px-6 py-4 align-top text-right">
                        <button
                          onClick={() => deleteRecord(item.id)}
                          className="rounded-2xl bg-rose-500/90 px-4 py-2 text-xs font-semibold text-white transition hover:bg-rose-400"
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
      </div>
    </main>
  );
}
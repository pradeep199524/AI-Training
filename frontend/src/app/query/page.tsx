"use client";
import React, { useState } from 'react';
import { Search, Cpu, Layers, HelpCircle, CheckCircle2, AlertTriangle } from 'lucide-react';

interface StrategyResult {
  text: string;
  score: number;
  document_name: string;
  page_number: number;
}

interface ChartMetric {
  strategy: string;
  accuracy: number;
}

interface RetrievalResponse {
  input_query: string;
  normalized_query: string;
  dense_results: StrategyResult[];
  sparse_results: StrategyResult[];
  hybrid_results: StrategyResult[];
  charts_data: ChartMetric[];
}

export default function QueryEnginePage() {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<RetrievalResponse | null>(null);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError(null);
    try {
      const response = await fetch('http://localhost:8000/api/v1/retrieve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.trim() }),
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || 'Failed to retrieve metrics from backend.');
      }

      const result = await response.json();
      setData(result);
    } catch (err: any) {
      setError(err.message || 'Connecting to server failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 min-h-screen text-gray-800">
      {/* Top Heading */}
      <div>
        <h1 className="text-3xl font-extrabold tracking-tight text-gray-900">Retrieval &amp; Search Intelligence</h1>
        <p className="text-gray-500 mt-1 text-sm">
          Evaluate Dense Vector, Sparse Keyword (BM25), and Hybrid Reranked index performance strategies side-by-side.
        </p>
      </div>

      {/* Main Console Container */}
      <div className="bg-gradient-to-r from-slate-900 to-indigo-950 p-6 rounded-3xl border border-slate-800 shadow-xl text-white">
        <form onSubmit={handleSearch} className="space-y-4">
          <label className="block text-sm font-semibold tracking-wide uppercase text-indigo-200">
            Search Vector Spaces &amp; Structured Indexes
          </label>
          <div className="relative flex items-center">
            <Search className="absolute left-4 h-5 w-5 text-slate-400" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Enter cross-examination query (e.g., What are production customer feeds?)..."
              className="w-full bg-slate-950/60 border border-slate-700/80 rounded-2xl py-4 pl-12 pr-36 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm transition-all"
            />
            <button
              type="submit"
              disabled={loading}
              className="absolute right-2 bg-blue-600 hover:bg-blue-500 active:bg-blue-700 text-white text-xs font-bold uppercase tracking-wider px-5 py-2.5 rounded-xl transition-all shadow-md disabled:opacity-50"
            >
              {loading ? 'Processing...' : 'Execute Search'}
            </button>
          </div>
        </form>

        {/* Unified Subpanel: Analytics Left & Small Compact Graph Right */}
        {data && (
          <div className="mt-4 pt-4 border-t border-slate-800 grid grid-cols-1 lg:grid-cols-3 gap-4 text-xs">
            {/* Left Hand: Query Analytics Fields */}
            <div className="lg:col-span-2 space-y-3">
              <div className="bg-slate-950/40 p-3 rounded-xl border border-slate-800">
                <span className="text-slate-400 block font-medium mb-0.5">Raw User Input:</span>
                <span className="font-mono text-slate-200 italic">"{data.input_query}"</span>
              </div>
              <div className="bg-slate-950/40 p-3 rounded-xl border border-slate-800">
                <span className="text-indigo-400 block font-medium mb-0.5">Optimized Pipeline Variant:</span>
                <span className="font-mono text-indigo-200 font-semibold">"{data.normalized_query}"</span>
              </div>
            </div>

            {/* Right Hand: Small Compact Graph Widget */}
            <div className="bg-slate-950/40 p-3 rounded-xl border border-slate-800 space-y-2 flex flex-col justify-center">
              <span className="text-slate-400 font-bold tracking-wider uppercase text-[10px] flex items-center gap-1">
                <Cpu className="h-3 w-3 text-blue-400" /> Benchmark Hit Rate
              </span>
              <div className="space-y-1.5">
                {data.charts_data.map((bar, index) => {
                  const colors = [
                    'from-amber-400 to-orange-500', 
                    'from-cyan-400 to-blue-600', 
                    'from-indigo-500 to-purple-600'
                  ];
                  return (
                    <div key={bar.strategy} className="space-y-0.5">
                      <div className="flex justify-between text-[10px] font-medium text-slate-300">
                        <span className="truncate max-w-[120px]">{bar.strategy.split(' ')[0]} Match</span>
                        <span>{bar.accuracy}%</span>
                      </div>
                      <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                        <div 
                          className={`bg-gradient-to-r ${colors[index % colors.length]} h-full rounded-full transition-all duration-1000`} 
                          style={{ width: `${bar.accuracy}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Error Output Catch */}
      {error && (
        <div className="bg-red-50 border border-red-200 p-4 rounded-2xl flex items-start gap-3 text-red-700">
          <AlertTriangle className="h-5 w-5 text-red-500 shrink-0 mt-0.5" />
          <div>
            <h5 className="font-bold text-sm">Execution Engine Alert</h5>
            <p className="text-xs text-red-600 mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {/* Main Results Display Areas directly underneath */}
      {data && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 animate-in fade-in slide-in-from-bottom-3 duration-300">
          
          {/* Column 1: Sparse Keywords */}
          <div className="bg-gray-50 rounded-2xl p-5 border border-gray-200/60 flex flex-col">
            <div className="flex items-center justify-between border-b border-gray-200 pb-3 mb-4">
              <h4 className="font-bold text-sm text-gray-800 flex items-center gap-1.5">
                <Layers className="h-4 w-4 text-orange-500" /> Sparse BM25 Matcher
              </h4>
              <span className="text-xs px-2.5 py-0.5 bg-orange-100 text-orange-700 font-bold rounded-full">Keyword Only</span>
            </div>
            <ResultList results={data.sparse_results} />
          </div>

          {/* Column 2: Pure Dense Vector */}
          <div className="bg-gray-50 rounded-2xl p-5 border border-gray-200/60 flex flex-col">
            <div className="flex items-center justify-between border-b border-gray-200 pb-3 mb-4">
              <h4 className="font-bold text-sm text-gray-800 flex items-center gap-1.5">
                <Layers className="h-4 w-4 text-blue-500" /> Dense Vector (Chroma)
              </h4>
              <span className="text-xs px-2.5 py-0.5 bg-blue-100 text-blue-700 font-bold rounded-full">Semantic Embeds</span>
            </div>
            <ResultList results={data.dense_results} />
          </div>

          {/* Column 3: Hybrid + Cross Reranking */}
          <div className="bg-gradient-to-b from-indigo-50/50 to-purple-50/20 rounded-2xl p-5 border border-indigo-100 flex flex-col shadow-sm">
            <div className="flex items-center justify-between border-b border-indigo-100 pb-3 mb-4">
              <h4 className="font-bold text-sm text-indigo-950 flex items-center gap-1.5">
                <CheckCircle2 className="h-4 w-4 text-purple-600" /> Hybrid + Cross-Reranker
              </h4>
              <span className="text-xs px-2.5 py-0.5 bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-bold rounded-full shadow-sm">RRF Optimized</span>
            </div>
            <ResultList results={data.hybrid_results} isPremium />
          </div>

        </div>
      )}

      {/* Empty State Banner */}
      {!data && !loading && (
        <div className="bg-white rounded-2xl border border-gray-100 p-12 text-center max-w-xl mx-auto shadow-sm">
          <HelpCircle className="h-10 w-10 text-gray-300 mx-auto mb-3" />
          <h4 className="font-bold text-gray-800 text-base">Execution Space Ready</h4>
          <p className="text-gray-400 text-xs mt-1">
            Submit a diagnostic request using the controller terminal above to construct evaluation parameters across vector weights.
          </p>
        </div>
      )}
    </div>
  );
}

// Result Renderer displaying paragraphs directly at the top
function ResultList({ results, isPremium = false }: { results: StrategyResult[]; isPremium?: boolean }) {
  if (!results || results.length === 0) {
    return <p className="text-xs text-gray-400 italic py-4">No payload segments matched indices.</p>;
  }

  return (
    <div className="space-y-4">
      {results.map((item, idx) => {
        const displayScore = isPremium && (item.score > 1.0 || item.score < 0.0)
          ? `${item.score.toFixed(2)} (Logit)`
          : item.score.toFixed(4);

        return (
          <div 
            key={idx} 
            className={`p-4 rounded-xl border transition-all text-xs flex flex-col gap-3 shadow-sm ${
              isPremium 
                ? 'bg-white border-indigo-200 hover:border-purple-300' 
                : 'bg-white border-gray-200 hover:border-gray-300'
            }`}
          >
            {/* 1. PRIMARY POSITIONING: Extracted Content Blocks */}
            <div className="bg-slate-50/60 p-3 rounded-lg border border-slate-100 font-normal text-gray-700 leading-relaxed text-left">
              "{item.text}"
            </div>
            
            {/* 2. SECONDARY POSITIONING: Contextual Metadata Block */}
            <div className="flex flex-col gap-2 pt-1 border-t border-gray-100 text-[11px]">
              <div className="flex justify-between items-center font-semibold">
                <span className={`truncate max-w-[150px] px-2 py-0.5 rounded ${isPremium ? 'bg-indigo-50 text-indigo-700' : 'bg-gray-100 text-gray-600'}`}>
                  📄 {item.document_name}
                </span>
                <span className="text-gray-400 shrink-0">Page {item.page_number}</span>
              </div>
              
              <div className="flex justify-between items-center">
                <span className="text-gray-400 font-medium">Confidence Weight:</span>
                <span className={`font-mono font-bold ${isPremium ? 'text-purple-600' : 'text-gray-700'}`}>
                  {displayScore}
                </span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
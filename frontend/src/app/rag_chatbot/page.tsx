"use client";

import React, { useState, useRef, useEffect } from 'react';
import { Send, User, Bot, Loader2, ServerCrash, Clock } from 'lucide-react'; // FileText removed as it's no longer needed

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  citations?: string[];
  latency?: string;
  timestamp?: string;
}

// Helper function to get current time (Forced 'en-US' for consistent AM/PM capitalization)
const getCurrentTime = () => {
  return new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
};

export default function ChatbotPage() {
  const [isMounted, setIsMounted] = useState(false);
  const [query, setQuery] = useState('');
  
  const [messages, setMessages] = useState<ChatMessage[]>([
    { 
      role: 'assistant', 
      content: 'Hello. I am your AI Assistant, ready to help you analyze records and documents. How may I help you today?',
      timestamp: getCurrentTime()
    }
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };
  
  useEffect(() => { scrollToBottom(); }, [messages, isLoading, error]);

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    const userMessage: ChatMessage = { 
      role: 'user', 
      content: query.trim(),
      timestamp: getCurrentTime() 
    };
    
    const chatHistory = messages
      .filter(msg => msg.role === 'user' || msg.role === 'assistant')
      .map(msg => ({ 
        role: msg.role, 
        content: msg.content 
      }));
    
    setMessages(prev => [...prev, userMessage]);
    setQuery('');
    setIsLoading(true);
    setError(null);

    try {
      // --- FIXED: Changed localhost to 127.0.0.1 to match backend and avoid CORS/Network hangs ---
      const response = await fetch('http://127.0.0.1:8000/api/v1/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          query: userMessage.content,
          history: chatHistory 
        })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Failed to fetch response from backend');
      }
      
      const aiMessage: ChatMessage = { 
        role: 'assistant', 
        content: data.answer,
        citations: data.citations,
        latency: data.latency,
        timestamp: getCurrentTime()
      };
      
      setMessages(prev => [...prev, aiMessage]);
    } catch (err: any) {
      console.error("Chat Error:", err);
      setError(err.message || 'Sorry, I encountered an error connecting to the knowledge base.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen max-h-screen bg-gray-50 p-4 sm:p-6 font-sans">
      <div className="flex flex-col h-full max-w-5xl mx-auto w-full bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden">
        
        {/* Header */}
        <div className="bg-slate-900 text-white p-4 sm:px-6 flex items-center justify-between shadow-md z-10">
          <div className="flex items-center space-x-3">
            <div className="bg-blue-600 p-2 rounded-lg">
              <Bot size={24} />
            </div>
            <div>
              <h2 className="text-xl font-bold">AI Assistant</h2>
              <p className="text-xs text-blue-200 font-medium">Ready to help</p>
            </div>
          </div>
          <div className="flex items-center space-x-2 bg-slate-800 py-1 px-3 rounded-full">
            <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span className="text-xs text-slate-200 uppercase tracking-wider font-semibold">Online</span>
          </div>
        </div>

        {/* Chat History Area */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6 bg-slate-50/50">
          {messages.map((msg, index) => (
            <div key={index} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`flex max-w-[85%] sm:max-w-[75%] ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
                
                <div className={`flex-shrink-0 h-10 w-10 rounded-full flex items-center justify-center mx-3 shadow-sm
                  ${msg.role === 'user' ? 'bg-blue-600 text-white' : 'bg-slate-800 text-blue-400'}`}>
                  {msg.role === 'user' ? <User size={20} /> : <Bot size={20} />}
                </div>

                <div className="flex flex-col">
                  <div className={`relative p-3.5 pb-7 rounded-2xl ${
                    msg.role === 'user' 
                      ? 'bg-blue-600 text-white rounded-tr-none shadow-md' 
                      : 'bg-white border border-gray-200 text-gray-800 rounded-tl-none shadow-sm'
                  }`}>
                    <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                    
                    {/* Timestamp is ONLY rendered if the component is fully mounted */}
                    {isMounted && msg.timestamp && (
                      <span className={`absolute bottom-1.5 right-3 text-[10px] font-medium tracking-wide ${
                        msg.role === 'user' ? 'text-blue-200' : 'text-gray-400'
                      }`}>
                        {msg.timestamp}
                      </span>
                    )}
                  </div>

                  {/* Latency Footer block (Citations mapping completely removed) */}
                  {msg.latency && (
                    <div className="mt-2 flex flex-wrap items-center gap-2 pl-1">
                      <div className="flex items-center text-xs bg-gray-100 text-gray-600 border border-gray-200 px-2.5 py-1.5 rounded-lg font-medium shadow-sm">
                        <Clock size={14} className="mr-1.5 text-gray-500" />
                        {msg.latency}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}

          {/* Loading Indicator */}
          {isLoading && (
            <div className="flex justify-start">
              <div className="flex flex-row max-w-[80%]">
                <div className="flex-shrink-0 h-10 w-10 rounded-full bg-slate-800 text-blue-400 flex items-center justify-center mx-3 shadow-sm">
                  <Bot size={20} />
                </div>
                <div className="bg-white border border-gray-200 p-4 rounded-2xl rounded-tl-none shadow-sm flex items-center space-x-3">
                  <Loader2 className="animate-spin text-blue-600" size={18} />
                  <span className="text-sm text-gray-600 font-medium">Analyzing documents and generating response...</span>
                </div>
              </div>
            </div>
          )}

          {/* Error Banner */}
          {error && (
            <div className="flex justify-center my-4">
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center shadow-sm max-w-lg">
                <ServerCrash size={20} className="mr-2 flex-shrink-0" />
                <span className="text-sm font-medium">{error}</span>
              </div>
            </div>
          )}
          
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="bg-white p-4 sm:p-5 border-t border-gray-200 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.05)]">
          <form onSubmit={handleSendMessage} className="flex relative items-center">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask about your CSV records, PDF documents, or system policies..."
              className="flex-1 bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 block w-full p-4 pr-14 outline-none transition-all"
              disabled={isLoading}
            />
            <button
              type="submit"
              disabled={!query.trim() || isLoading}
              className="absolute right-2 bg-blue-600 text-white p-2.5 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:hover:bg-blue-600 transition-colors shadow-sm"
            >
              <Send size={20} />
            </button>
          </form>
          <div className="text-center mt-2">
             <span className="text-xs text-gray-400">AI can make mistakes. Verify important information using the citations.</span>
          </div>
        </div>
      </div>
    </div>
  );
}
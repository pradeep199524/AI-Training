"use client";

import React, { useState, useRef, useEffect } from 'react';
import { Send, User, Bot, Loader2, ServerCrash, Clock, Menu } from 'lucide-react';
import ChatHistorySidebar, { ChatSession } from '@/components/ChatHistorySidebar';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  citations?: string[];
  latency?: string;
  timestamp?: string;
}

const getCurrentTime = () => {
  return new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
};

export default function ChatbotPage() {
  const [isMounted, setIsMounted] = useState(false);
  const [query, setQuery] = useState('');
  
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

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
    fetchSessions();
  }, []);

  const fetchSessions = async () => {
    try {
      const res = await fetch('http://127.0.0.1:8000/api/v1/sessions');
      if (res.ok) {
        const data = await res.json();
        setSessions(data);
      }
    } catch (err) {
      console.error("Failed to fetch sessions:", err);
    }
  };

  const handleSelectSession = async (sessionId: string) => {
    setActiveSessionId(sessionId);
    setIsLoading(true);
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/v1/sessions/${sessionId}/messages`);
      if (res.ok) {
        const data = await res.json();
        const formattedMessages = data.map((msg: any) => ({
          role: msg.role,
          content: msg.content,
          timestamp: getCurrentTime()
        }));
        setMessages(formattedMessages.length > 0 ? formattedMessages : [
          { role: 'assistant', content: 'Hello! How can I help you with this chat?', timestamp: getCurrentTime() }
        ]);
      }
    } catch (err) {
      console.error("Failed to load session messages:", err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleNewChat = () => {
    setActiveSessionId(null);
    setMessages([
      { 
        role: 'assistant', 
        content: 'Hello. I am your AI Assistant, ready to help you analyze records and documents. How may I help you today?',
        timestamp: getCurrentTime()
      }
    ]);
  };

  // --- NEW: Delete Session Function ---
  const handleDeleteSession = async (sessionId: string) => {
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/v1/sessions/${sessionId}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        // Remove the session from the sidebar UI immediately
        setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
        // Reset to a new chat if the user deletes the currently active chat
        if (activeSessionId === sessionId) {
          handleNewChat();
        }
      }
    } catch (err) {
      console.error("Failed to delete session:", err);
    }
  };

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
      const response = await fetch('http://127.0.0.1:8000/api/v1/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          query: userMessage.content,
          history: chatHistory,
          session_id: activeSessionId
        })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Failed to fetch response from backend');
      }
      
      if (data.session_id && !activeSessionId) {
        setActiveSessionId(data.session_id);
        fetchSessions();
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
    <div className="flex h-[calc(100vh-theme(spacing.16))] w-full bg-gray-50 font-sans overflow-hidden">
      
      {/* Inner Chat History Sidebar */}
      <div className={`${isSidebarOpen ? 'flex' : 'hidden'} sm:flex h-full shrink-0 flex-col z-10`}>
        <ChatHistorySidebar
          sessions={sessions}
          activeSessionId={activeSessionId}
          onSelectSession={handleSelectSession}
          onNewChat={handleNewChat}
          onDeleteSession={handleDeleteSession} // --- NEW: Passed the delete function here ---
        />
      </div>

      {/* Main Chat Panel */}
      <div className="flex flex-col flex-1 h-full bg-white border-l border-gray-200 overflow-hidden relative">
        
        {/* Header - Now fully visible at the top */}
        <div className="bg-slate-900 text-white p-4 sm:px-6 flex items-center justify-between shadow-md z-10 shrink-0">
          <div className="flex items-center space-x-3">
            <button 
              onClick={() => setIsSidebarOpen(!isSidebarOpen)} 
              className="text-slate-300 hover:text-white mr-1"
              title="Toggle Sidebar"
            >
              <Menu size={22} />
            </button>
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
                    
                    {isMounted && msg.timestamp && (
                      <span className={`absolute bottom-1.5 right-3 text-[10px] font-medium tracking-wide ${
                        msg.role === 'user' ? 'text-blue-200' : 'text-gray-400'
                      }`}>
                        {msg.timestamp}
                      </span>
                    )}
                  </div>

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
        <div className="bg-white p-4 sm:p-5 border-t border-gray-200 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.05)] shrink-0">
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
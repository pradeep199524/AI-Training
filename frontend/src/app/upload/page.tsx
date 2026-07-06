'use client';

import { useEffect, useState, FormEvent } from 'react';
import FileUpload from '@/components/FileUpload';
import { apiPath } from '@/lib/api';

type Ticket = {
  id: number;
  title: string;
  customer_name: string;
  description: string;
  status: string;
};

type DocumentSummary = {
  id: number;
  filename: string;
  page_count?: number;
  paragraph_count?: number;
};

type PdfParagraph = {
  source_pdf: string;
  page: number;
  paragraph_index: number;
  text: string;
};

type CsvRecord = {
  id: number;
  source: string;
  row: Record<string, unknown>;
};

const defaultTicketForm = {
  title: '',
  customer_name: '',
  description: '',
  status: 'new',
};

export default function UploadPage() {
  const [file, setFile] = useState<globalThis.File | null>(null);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [pdfRecords, setPdfRecords] = useState<PdfParagraph[]>([]);
  const [csvRecords, setCsvRecords] = useState<CsvRecord[]>([]);
  const [ticketForm, setTicketForm] = useState(defaultTicketForm);
  const [editingTicketId, setEditingTicketId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingTickets, setLoadingTickets] = useState(false);
  const [loadingContent, setLoadingContent] = useState(false);
  const [statusMsg, setStatusMsg] = useState('');
  const [error, setError] = useState('');
  const [retryAction, setRetryAction] = useState<
    | { type: 'pdf' | 'csv'; filename: string; taskId?: string }
    | null
  >(null);
  const [activityLog, setActivityLog] = useState<string[]>(['Ready to ingest documents and manage tickets.']);

  const pushActivity = (message: string) => {
    setActivityLog((prev) => [message, ...prev].slice(0, 6));
  };

  useEffect(() => {
    loadDocuments();
    loadTickets();
  }, []);


  const loadDocuments = async () => {
    try {
      const res = await fetch(apiPath('documents?limit=10'));
      const payload = await res.json().catch(() => ({}));
      setDocuments(payload.data || []);
      pushActivity('Refreshed document index.');
    } catch (err) {
      console.error(err);
      setError('Unable to refresh document list.');
    }
  };

  const loadTickets = async () => {
    setLoadingTickets(true);
    try {
      const res = await fetch(apiPath('tickets?limit=10'));
      const payload = await res.json().catch(() => ({}));
      setTickets(payload.data || []);
      pushActivity('Refreshed ticket queue.');
    } catch (err) {
      console.error(err);
      setError('Unable to refresh tickets.');
    } finally {
      setLoadingTickets(false);
    }
  };

  const loadExtractedContent = async (filename: string) => {
    setLoadingContent(true);
    try {
      const [pdfRes, csvRes] = await Promise.all([
        fetch(apiPath(`records/pdf?source_file=${encodeURIComponent(filename)}&limit=10`)),
        fetch(apiPath(`records/csv?source_file=${encodeURIComponent(filename)}&limit=8`)),
      ]);

      const pdfData = await pdfRes.json().catch(() => ({}));
      const csvData = await csvRes.json().catch(() => ({}));
      setPdfRecords(pdfData.data || []);
      setCsvRecords(csvData.data || []);
    } catch (err) {
      console.error(err);
      setError('Unable to refresh extracted content.');
    } finally {
      setLoadingContent(false);
    }
  };

  const getFileType = (filename: string | null): 'pdf' | 'csv' | null => {
    if (!filename) {
      return null;
    }
    const lower = filename.toLowerCase();
    if (lower.endsWith('.pdf')) return 'pdf';
    if (lower.endsWith('.csv')) return 'csv';
    return null;
  };

  const waitForIngestionCompletion = async (filename: string, type: 'pdf' | 'csv') => {
    const maxAttempts = 12;
    const delayMs = 1500;

    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      pushActivity(`Waiting for ${type.toUpperCase()} ingestion (${attempt}/${maxAttempts})...`);

      try {
        if (type === 'pdf') {
          const res = await fetch(apiPath('documents?limit=20'));
          const payload = await res.json().catch(() => ({}));
          const docs = payload.data || [];
          if (docs.some((doc: DocumentSummary) => doc.filename === filename)) {
            return true;
          }
        } else {
          const res = await fetch(apiPath(`records/csv?source_file=${encodeURIComponent(filename)}&limit=1`));
          const payload = await res.json().catch(() => ({}));
          const records = payload.data || [];
          if (records.length > 0) {
            return true;
          }
        }
      } catch (err) {
        console.error(err);
      }

      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }

    return false;
  };

  const uploadAndIngest = async (expectedType: 'pdf' | 'csv') => {
    if (!file) {
      setError('Please select a file first.');
      return;
    }

    const actualType = getFileType(file.name);
    if (!actualType) {
      setError('Selected file type is not supported. Please upload a .pdf or .csv file.');
      return;
    }

    if (actualType !== expectedType) {
      setError(`Selected file is a .${actualType} but you clicked the ${expectedType.toUpperCase()} button. Please use the correct upload button.`);
      return;
    }

    setLoading(true);
    setError('');
    setStatusMsg('');
    pushActivity(`Starting ${actualType.toUpperCase()} ingestion for ${file.name}...`);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const uploadRes = await fetch(apiPath('upload/file'), {
        method: 'POST',
        body: formData,
      });

      if (!uploadRes.ok) {
        const payload = await uploadRes.json().catch(() => ({}));
        throw new Error(payload.detail || 'File upload failed.');
      }

      const uploadPayload = await uploadRes.json().catch(() => ({}));
      const taskId = uploadPayload.task_id;

      setStatusMsg(`File uploaded and queued for ${actualType.toUpperCase()} ingestion.`);
      setRetryAction({ type: actualType, filename: file.name, taskId });
      pushActivity(`Queued ${actualType.toUpperCase()} ingestion for ${file.name}. Task: ${taskId}`);

      // Poll task status endpoint to show explicit success/fail
      const pollTaskStatus = async (id: string) => {
        const maxAttempts = 16;
        const delayMs = 1500;
        for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
          try {
            const res = await fetch(apiPath(`tasks/${encodeURIComponent(id)}`));
            if (res.ok) {
              const data = await res.json().catch(() => ({}));
              const status = data.status;
              if (status === 'SUCCESS') {
                return { ok: true, result: data.result };
              }
              if (status === 'FAILURE' || status === 'REVOKED') {
                return { ok: false, result: data.result };
              }
            }
          } catch (e) {
            console.error(e);
          }
          await new Promise((r) => setTimeout(r, delayMs));
        }
        return { ok: null };
      };

      const taskOutcome = taskId ? await pollTaskStatus(taskId) : { ok: null };
      const ingestionSucceeded = taskOutcome.ok === true || !!uploadPayload.direct_ingest;

      if (ingestionSucceeded) {
        setStatusMsg(
          `${actualType.toUpperCase()} ingestion succeeded for ${file.name}.` +
            (actualType === 'csv' ? ' CSV rows are available.' : ' Document list refreshed.') +
            (uploadPayload.direct_ingest ? ' Processed directly because background queue was unavailable.' : '')
        );
        pushActivity(`Ingestion succeeded for ${file.name}.`);
        try {
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new Event('documentsUpdated'));
          }
        } catch (e) {
          console.error('dispatch event failed', e);
        }
      } else if (taskOutcome.ok === false) {
        setStatusMsg(`${actualType.toUpperCase()} ingestion failed for ${file.name}.`);
        pushActivity(`Ingestion task ${taskId} failed.`);
      } else {
        setStatusMsg(`File queued successfully. Ingestion is still processing in the background.`);
        pushActivity(`Ingestion still pending for ${file.name}.`);
      }

      await loadDocuments();
      await loadExtractedContent(file.name);
    } catch (err: any) {
      console.error(err);
      pushActivity(`Ingestion failed for ${file.name}.`);
      setError(err?.message || 'Upload failed.');
    } finally {
      setLoading(false);
    }
  };

  const retryLastAction = async () => {
    if (!retryAction) {
      setError('No previous upload available to retry.');
      return;
    }
    await uploadAndIngest(retryAction.type);
  };

  const saveTicket = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    setStatusMsg('');
    pushActivity(editingTicketId ? `Updating ticket ${editingTicketId}...` : 'Creating a new ticket...');

    try {
      const method = editingTicketId ? 'PUT' : 'POST';
      const targetUrl = editingTicketId ? apiPath(`tickets/${editingTicketId}`) : apiPath('tickets');
      const res = await fetch(targetUrl, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(ticketForm),
      });

      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        throw new Error(payload.detail || 'Unable to save ticket.');
      }

      setTicketForm(defaultTicketForm);
      setEditingTicketId(null);
      await loadTickets();
      setStatusMsg('Ticket saved successfully.');
      pushActivity(editingTicketId ? `Updated ticket ${editingTicketId}.` : 'Created a new ticket.');
    } catch (err: any) {
      console.error(err);
      setError(err?.message || 'Ticket save failed.');
    }
  };

  const editTicket = (ticket: Ticket) => {
    setEditingTicketId(ticket.id);
    setTicketForm({
      title: ticket.title,
      customer_name: ticket.customer_name,
      description: ticket.description,
      status: ticket.status,
    });
  };

  const deleteTicket = async (ticketId: number) => {
    if (!confirm('Delete this ticket?')) {
      return;
    }

    try {
      const res = await fetch(apiPath(`tickets/${ticketId}`), { method: 'DELETE' });
      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        throw new Error(payload.detail || 'Unable to delete ticket.');
      }
      await loadTickets();
      setStatusMsg('Ticket deleted.');
      pushActivity(`Deleted ticket ${ticketId}.`);
    } catch (err: any) {
      console.error(err);
      setError(err?.message || 'Ticket delete failed.');
    }
  };

  return (
    <main style={{ padding: '2rem', minHeight: '100vh', backgroundColor: '#030712', color: '#f8fafc', fontFamily: 'Inter, sans-serif' }}>
      <div style={{ maxWidth: 1300, width: '100%', margin: '0 auto', display: 'grid', gap: '1.5rem' }}>
        <header style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <p style={{ color: '#94a3b8', margin: 0 }}>Document ingestion and ticketing</p>
          <h1 style={{ margin: 0, fontSize: '2.2rem' }}>Upload & Ingestion Hub</h1>
          <p style={{ margin: 0, color: '#cbd5e1', maxWidth: 760 }}>
            Select a file to upload, trigger ingestion, inspect extracted records, and manage operational tickets in one place.
          </p>
        </header>

        <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 0.9fr', gap: '1.5rem' }}>
          <section style={{ background: '#0f172a', borderRadius: '1rem', padding: '1.5rem' }}>
            <h2 style={{ marginTop: 0 }}>Upload & Ingest</h2>
            <div style={{ display: 'grid', gap: '1rem' }}>
              <FileUpload
                accept=".pdf,.csv"
                onFileSelect={(selectedFile) => {
                  setFile(selectedFile);
                  setError('');
                  if (selectedFile) {
                    pushActivity(`Selected ${selectedFile.name}`);
                  }
                }}
              />

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem' }}>
                <button
                  type="button"
                  disabled={loading}
                  onClick={() => uploadAndIngest('pdf')}
                  style={{ flex: '1 1 160px', padding: '0.85rem 1rem', backgroundColor: '#6366f1', color: '#fff', border: 'none', borderRadius: '0.75rem', cursor: 'pointer' }}
                >
                  Upload PDF
                </button>
                <button
                  type="button"
                  disabled={loading}
                  onClick={() => uploadAndIngest('csv')}
                  style={{ flex: '1 1 160px', padding: '0.85rem 1rem', backgroundColor: '#14b8a6', color: '#fff', border: 'none', borderRadius: '0.75rem', cursor: 'pointer' }}
                >
                  Upload CSV
                </button>
              </div>

              {retryAction ? (
                <button
                  type="button"
                  onClick={retryLastAction}
                  style={{ padding: '0.85rem 1rem', backgroundColor: '#f59e0b', color: '#fff', border: 'none', borderRadius: '0.75rem', cursor: 'pointer' }}
                >
                  Retry Last Ingestion
                </button>
              ) : null}

              {statusMsg ? (
                <div style={{ padding: '1rem', borderRadius: '0.85rem', background: '#064e3b', color: '#a7f3d0' }}>{statusMsg}</div>
              ) : null}
              {error ? (
                <div style={{ padding: '1rem', borderRadius: '0.85rem', background: '#7f1d1d', color: '#fecaca' }}>{error}</div>
              ) : null}
              <div style={{ padding: '1rem', borderRadius: '0.85rem', background: '#111827', border: '1px solid #1e293b' }}>
                <h3 style={{ margin: '0 0 0.75rem', color: '#f8fafc' }}>System Activity</h3>
                <div style={{ display: 'grid', gap: '0.5rem' }}>
                  {activityLog.map((entry, index) => (
                    <div key={`${entry}-${index}`} style={{ color: '#cbd5e1', fontSize: '0.95rem' }}>
                      • {entry}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </section>

          <section style={{ background: '#0f172a', borderRadius: '1rem', padding: '1.5rem' }}>
            <h2 style={{ marginTop: 0 }}>Ticket Manager</h2>
            <form onSubmit={saveTicket} style={{ display: 'grid', gap: '0.9rem' }}>
              <input
                type="text"
                value={ticketForm.title}
                onChange={(event) => setTicketForm({ ...ticketForm, title: event.target.value })}
                placeholder="Ticket title"
                required
                style={{ padding: '0.85rem', borderRadius: '0.75rem', border: '1px solid #334155', background: '#0b1120', color: '#e2e8f0' }}
              />
              <input
                type="text"
                value={ticketForm.customer_name}
                onChange={(event) => setTicketForm({ ...ticketForm, customer_name: event.target.value })}
                placeholder="Customer name"
                required
                style={{ padding: '0.85rem', borderRadius: '0.75rem', border: '1px solid #334155', background: '#0b1120', color: '#e2e8f0' }}
              />
              <textarea
                value={ticketForm.description}
                onChange={(event) => setTicketForm({ ...ticketForm, description: event.target.value })}
                placeholder="Description"
                required
                style={{ minHeight: '110px', padding: '0.85rem', borderRadius: '0.75rem', border: '1px solid #334155', background: '#0b1120', color: '#e2e8f0' }}
              />
              <select
                value={ticketForm.status}
                onChange={(event) => setTicketForm({ ...ticketForm, status: event.target.value })}
                style={{ padding: '0.85rem', borderRadius: '0.75rem', border: '1px solid #334155', background: '#0b1120', color: '#e2e8f0' }}
              >
                <option value="new">New</option>
                <option value="in_progress">In Progress</option>
                <option value="resolved">Resolved</option>
              </select>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem' }}>
                <button
                  type="submit"
                  style={{ flex: '1 1 140px', padding: '0.85rem 1rem', backgroundColor: '#0284c7', color: '#fff', border: 'none', borderRadius: '0.75rem', cursor: 'pointer' }}
                >
                  {editingTicketId ? 'Update Ticket' : 'Create Ticket'}
                </button>
                {editingTicketId ? (
                  <button
                    type="button"
                    onClick={() => {
                      setEditingTicketId(null);
                      setTicketForm(defaultTicketForm);
                    }}
                    style={{ flex: '1 1 140px', padding: '0.85rem 1rem', backgroundColor: '#475569', color: '#fff', border: 'none', borderRadius: '0.75rem', cursor: 'pointer' }}
                  >
                    Cancel
                  </button>
                ) : null}
              </div>
            </form>
          </section>
        </div>

        <div style={{ display: 'grid', gap: '1.5rem' }}>
          <section style={{ background: '#0f172a', borderRadius: '1rem', padding: '1.5rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
              <h2 style={{ margin: 0 }}>Recent Documents</h2>
              <button
                type="button"
                onClick={loadDocuments}
                style={{ padding: '0.75rem 1rem', backgroundColor: '#2563eb', color: '#fff', border: 'none', borderRadius: '0.75rem', cursor: 'pointer' }}
              >
                Refresh
              </button>
            </div>
            <div style={{ marginTop: '1rem', overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 680 }}>
                <thead>
                  <tr style={{ color: '#94a3b8', borderBottom: '1px solid #334155' }}>
                    <th style={{ padding: '0.9rem 0' }}>Filename</th>
                    <th style={{ padding: '0.9rem 0' }}>Pages</th>
                    <th style={{ padding: '0.9rem 0' }}>Paragraphs</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.length === 0 ? (
                    <tr>
                      <td colSpan={3} style={{ padding: '1rem 0', color: '#94a3b8' }}>No documents found.</td>
                    </tr>
                  ) : (
                    documents.map((document) => (
                      <tr key={document.id} style={{ borderBottom: '1px solid #1e293b' }}>
                        <td style={{ padding: '0.85rem 0' }}>{document.filename}</td>
                        <td style={{ padding: '0.85rem 0' }}>{document.page_count ?? '-'}</td>
                        <td style={{ padding: '0.85rem 0' }}>{document.paragraph_count ?? '-'}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section style={{ display: 'grid', gap: '1.5rem' }}>
            <div style={{ background: '#0f172a', borderRadius: '1rem', padding: '1.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', gap: '1rem' }}>
                <h2 style={{ margin: 0 }}>Extracted Content</h2>
                <button
                  type="button"
                  onClick={() => loadExtractedContent(file?.name || '')}
                  disabled={loadingContent || !file}
                  style={{ padding: '0.75rem 1rem', backgroundColor: '#10b981', color: '#fff', border: 'none', borderRadius: '0.75rem', cursor: 'pointer' }}
                >
                  Refresh
                </button>
              </div>
              <div style={{ display: 'grid', gap: '1rem' }}>
                <div>
                  <h3 style={{ margin: '0 0 0.5rem', color: '#f8fafc' }}>PDF Records</h3>
                  {pdfRecords.length === 0 ? (
                    <p style={{ color: '#94a3b8' }}>No PDF content loaded.</p>
                  ) : (
                    pdfRecords.slice(0, 3).map((record, index) => (
                      <div key={`${record.source_pdf}-${index}`} style={{ padding: '1rem', borderRadius: '0.85rem', background: '#111827', border: '1px solid #1e293b', marginBottom: '0.75rem' }}>
                        <p style={{ margin: 0, color: '#60a5fa' }}>{record.source_pdf} | page {record.page}</p>
                        <p style={{ margin: '0.5rem 0 0', color: '#e2e8f0' }}>{record.text}</p>
                      </div>
                    ))
                  )}
                </div>
                <div>
                  <h3 style={{ margin: '0 0 0.5rem', color: '#f8fafc' }}>CSV Records</h3>
                  {csvRecords.length === 0 ? (
                    <p style={{ color: '#94a3b8' }}>No CSV content loaded.</p>
                  ) : (
                    csvRecords.slice(0, 3).map((record) => (
                      <div key={record.id} style={{ padding: '1rem', borderRadius: '0.85rem', background: '#111827', border: '1px solid #1e293b', marginBottom: '0.75rem' }}>
                        <p style={{ margin: 0, color: '#60a5fa' }}>{record.source}</p>
                        <p style={{ margin: '0.5rem 0 0', color: '#e2e8f0' }}>{JSON.stringify(record.row)}</p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </section>
        </div>

        <section style={{ background: '#0f172a', borderRadius: '1rem', padding: '1.5rem' }}>
          <h2 style={{ marginTop: 0 }}>Ticket Queue</h2>
          {loadingTickets ? (
            <p style={{ color: '#94a3b8' }}>Loading tickets…</p>
          ) : tickets.length === 0 ? (
            <p style={{ color: '#94a3b8' }}>No tickets available.</p>
          ) : (
            <div style={{ display: 'grid', gap: '0.85rem' }}>
              {tickets.map((ticket) => (
                <div key={ticket.id} style={{ padding: '1rem', borderRadius: '0.85rem', background: '#111827', border: '1px solid #1e293b', display: 'grid', gap: '0.5rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <strong>{ticket.title}</strong>
                    <span style={{ color: '#7dd3fc' }}>{ticket.status}</span>
                  </div>
                  <div style={{ color: '#94a3b8' }}>{ticket.customer_name}</div>
                  <p style={{ margin: 0, color: '#e2e8f0' }}>{ticket.description}</p>
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    <button
                      onClick={() => editTicket(ticket)}
                      style={{ padding: '0.55rem 0.85rem', backgroundColor: '#2563eb', color: '#fff', border: 'none', borderRadius: '0.75rem', cursor: 'pointer' }}
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => deleteTicket(ticket.id)}
                      style={{ padding: '0.55rem 0.85rem', backgroundColor: '#dc2626', color: '#fff', border: 'none', borderRadius: '0.75rem', cursor: 'pointer' }}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

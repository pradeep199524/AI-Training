'use client';
import { useState, DragEvent } from 'react';
import { UploadCloud, File as FileIcon, X } from 'lucide-react';

interface FileUploadProps {
  accept?: string;
  onFileSelect: (file: globalThis.File | null) => void;
}

export default function FileUpload({ accept, onFileSelect }: FileUploadProps) {
  const [isDragActive, setIsDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState<globalThis.File | null>(null);

  const handleDrag = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setIsDragActive(true);
    } else if (e.type === "dragleave") {
      setIsDragActive(false);
    }
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      setSelectedFile(file);
      onFileSelect(file);
    }
  };

  const removeFile = () => {
    setSelectedFile(null);
    onFileSelect(null);
  };

  return (
    <div className="w-full max-w-xl">
      {!selectedFile ? (
        <label
          onDragEnter={handleDrag}
          onDragOver={handleDrag}
          onDragLeave={handleDrag}
          onDrop={handleDrop}
          className={`flex flex-col items-center justify-center w-full h-48 border-2 border-dashed rounded-xl cursor-pointer transition-colors ${
            isDragActive
              ? 'border-zinc-500 bg-zinc-50 dark:border-zinc-400 dark:bg-zinc-900'
              : 'border-zinc-300 bg-white hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:bg-zinc-900'
          }`}
        >
          <div className="flex flex-col items-center justify-center pt-5 pb-6 px-4 text-center">
            <UploadCloud className="w-8 h-8 mb-3 text-zinc-400" />
            <p className="mb-1 text-sm font-medium text-zinc-700 dark:text-zinc-300">
              Click to upload or drag and drop
            </p>
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              {accept ? `Accepted formats: ${accept}` : 'Any training data file'}
            </p>
          </div>
          <input 
            type="file" 
            className="hidden" 
            accept={accept}
            onChange={(e) => {
              if (e.target.files?.[0]) {
                setSelectedFile(e.target.files[0]);
                onFileSelect(e.target.files[0]);
              }
            }}
          />
        </label>
      ) : (
        <div className="flex items-center justify-between gap-4 rounded-3xl border border-slate-200 bg-white p-4 shadow-sm transition dark:border-slate-800 dark:bg-slate-950">
          <div className="flex items-center gap-3">
            <FileIcon className="h-5 w-5 text-slate-500" />
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">{selectedFile.name}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">{(selectedFile.size / 1024 / 1024).toFixed(2)} MB</p>
            </div>
          </div>
          <button 
            type="button"
            onClick={removeFile}
            className="rounded-full p-2 text-slate-400 transition hover:text-slate-600 dark:hover:text-slate-200"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}

import React, { useCallback, useState } from 'react';
import { Upload, FileText, AlertCircle, FileCheck, FileUp } from 'lucide-react';

interface FileUploadProps {
  onFileSelect: (base64: string, mimeType: string, fileName: string) => void;
  disabled: boolean;
}

export const FileUpload: React.FC<FileUploadProps> = ({ onFileSelect, disabled }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const processFile = useCallback((file: File) => {
    setError(null);
    if (!file) return;

    const validTypes = ['application/pdf', 'image/jpeg', 'image/png', 'image/webp'];
    if (!validTypes.includes(file.type)) {
      setError("Unsupported file format. Please use PDF, JPEG, or PNG.");
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      const result = e.target?.result as string;
      const base64 = result.split(',')[1];
      onFileSelect(base64, file.type, file.name);
    };
    reader.onerror = () => setError("Failed to read file.");
    reader.readAsDataURL(file);
  }, [onFileSelect]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (disabled) return;
    processFile(e.dataTransfer.files[0]);
  }, [processFile, disabled]);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (disabled || !e.target.files?.length) return;
    processFile(e.target.files[0]);
  }, [processFile, disabled]);

  return (
    <div className="w-full">
      <div
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        className={`
          relative group overflow-hidden rounded-lg transition-all duration-200 ease-out border border-dashed
          ${isDragging 
            ? 'bg-blue-500/10 border-blue-500' 
            : 'bg-zinc-900 border-zinc-700 hover:border-zinc-500 hover:bg-zinc-800/50'
          }
          ${disabled ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'}
        `}
      >
        <input
          type="file"
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed z-20"
          onChange={handleFileInput}
          disabled={disabled}
          accept=".pdf,.jpg,.jpeg,.png,.webp"
        />
        
        <div className="px-8 py-12 flex flex-col items-center justify-center text-center">
          <div className={`
            w-12 h-12 mb-4 rounded-full flex items-center justify-center transition-all duration-200
            ${isDragging ? 'bg-blue-500 text-white' : 'bg-zinc-800 text-zinc-400 group-hover:text-zinc-200'}
          `}>
            {isDragging ? (
              <FileCheck className="w-6 h-6" />
            ) : (
              <Upload className="w-6 h-6" />
            )}
          </div>
          
          <h3 className="text-sm font-medium text-zinc-200 mb-1">
            {isDragging ? 'Drop file to upload' : 'Upload Bank Statement'}
          </h3>
          
          <p className="text-xs text-zinc-500 mb-6">
            Drag PDF or Image, or click to browse.
          </p>

          <div className={`
            px-4 py-2 rounded-md text-xs font-medium transition-all duration-200 border
            ${isDragging 
              ? 'bg-blue-600 border-blue-600 text-white' 
              : 'bg-zinc-800 border-zinc-700 text-zinc-300 group-hover:bg-zinc-700 group-hover:border-zinc-600'
            }
          `}>
            Select File
          </div>
        </div>
      </div>

      {error && (
        <div className="mt-3 p-3 bg-red-900/20 border border-red-900/50 text-red-400 rounded-lg flex items-center gap-2 text-xs font-medium">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}
    </div>
  );
};

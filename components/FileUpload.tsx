import React, { useCallback, useState } from 'react';
import { Upload, FileText, AlertCircle, FileCheck } from 'lucide-react';

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
          relative group overflow-hidden rounded-2xl transition-all duration-300 ease-out
          ${isDragging 
            ? 'bg-blue-50 border-2 border-blue-500 scale-[1.01] shadow-2xl' 
            : 'bg-white border border-slate-200 hover:border-blue-400 hover:shadow-xl hover:shadow-blue-900/5'
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
        
        <div className="px-8 py-16 flex flex-col items-center justify-center text-center">
          <div className={`
            w-20 h-20 mb-6 rounded-2xl flex items-center justify-center transition-all duration-300
            ${isDragging ? 'bg-blue-100 scale-110' : 'bg-slate-50 group-hover:bg-blue-50 group-hover:scale-105'}
          `}>
            {isDragging ? (
              <FileCheck className="w-10 h-10 text-blue-600" />
            ) : (
              <Upload className="w-10 h-10 text-slate-400 group-hover:text-blue-600 transition-colors" />
            )}
          </div>
          
          <h3 className="text-xl font-bold text-slate-900 mb-2 group-hover:text-blue-700 transition-colors">
            {isDragging ? 'Drop file to upload' : 'Upload Bank Statement'}
          </h3>
          
          <p className="text-slate-500 max-w-sm mx-auto mb-8 leading-relaxed">
            Drag and drop your PDF or image here, or click to browse your secure files.
          </p>

          <div className={`
            px-6 py-2.5 rounded-lg text-sm font-semibold transition-all duration-300
            ${isDragging 
              ? 'bg-blue-600 text-white shadow-lg' 
              : 'bg-slate-900 text-white shadow-md group-hover:bg-blue-600 group-hover:shadow-lg group-hover:-translate-y-0.5'
            }
          `}>
            Browse Files
          </div>
        </div>

        {/* Decorative Grid Background */}
        <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-10 pointer-events-none"></div>
      </div>

      {error && (
        <div className="mt-4 p-4 bg-red-50 border border-red-100 text-red-700 rounded-xl flex items-center gap-3 text-sm font-medium animate-in fade-in slide-in-from-top-2 shadow-sm">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          {error}
        </div>
      )}
    </div>
  );
};
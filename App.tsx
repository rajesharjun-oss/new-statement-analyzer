import React, { useState, useEffect } from 'react';
import { FileUpload } from './components/FileUpload';
import { AnalysisDashboard } from './components/AnalysisDashboard';
import { SettingsModal } from './components/SettingsModal';
import { analyzeBankStatement } from './services/geminiService';
import { AppStatus, AnalysisResult } from './types';
import { Loader2, FileText, ShieldCheck, Settings } from 'lucide-react';

const App: React.FC = () => {
  const [status, setStatus] = useState<AppStatus>(AppStatus.IDLE);
  const [data, setData] = useState<AnalysisResult | null>(null);
  const [fileName, setFileName] = useState<string>('');
  
  // Settings State
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [userApiKey, setUserApiKey] = useState<string>('');

  useEffect(() => {
    // Load custom key from local storage on mount
    const storedKey = localStorage.getItem('gemini_custom_key');
    if (storedKey) setUserApiKey(storedKey);
  }, []);

  const handleSaveSettings = (key: string) => {
    setUserApiKey(key);
    if (key) {
      localStorage.setItem('gemini_custom_key', key);
    } else {
      localStorage.removeItem('gemini_custom_key');
    }
  };

  const handleFileSelect = async (base64: string, mimeType: string, name: string) => {
    setFileName(name);
    setStatus(AppStatus.ANALYZING);
    try {
      // Pass the userApiKey (if exists) to the service
      const result = await analyzeBankStatement(base64, mimeType, userApiKey);
      setData(result);
      setStatus(AppStatus.COMPLETE);
    } catch (error) {
      console.error(error);
      setStatus(AppStatus.ERROR);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Navbar */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="bg-blue-600 p-1.5 rounded-lg">
              <ShieldCheck className="w-6 h-6 text-white" />
            </div>
            <h1 className="text-xl font-bold text-slate-900 tracking-tight">
              Bank Statement Sentinel
            </h1>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-sm text-slate-500 hidden sm:block">
              Powered by Gemini 1.5 Pro
            </div>
            <button
              onClick={() => setIsSettingsOpen(true)}
              className="p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-full transition-colors"
              title="Settings"
            >
              <Settings className="w-5 h-5" />
            </button>
          </div>
        </div>
      </header>

      {/* Settings Modal */}
      <SettingsModal 
        isOpen={isSettingsOpen} 
        onClose={() => setIsSettingsOpen(false)}
        onSave={handleSaveSettings}
        currentKey={userApiKey}
      />

      {/* Main Content */}
      <main className="flex-1 flex flex-col">
        {status === AppStatus.IDLE && (
          <div className="flex-1 flex flex-col items-center justify-center p-6 animate-in fade-in duration-500">
            <div className="text-center max-w-lg mb-12">
              <h2 className="text-3xl font-extrabold text-slate-900 sm:text-4xl mb-4">
                Audit-Grade Analysis
              </h2>
              <p className="text-lg text-slate-600">
                Upload your bank statement PDF or Image. We'll extract, reconcile, and categorize every transaction automatically.
              </p>
            </div>
            <FileUpload onFileSelect={handleFileSelect} disabled={false} />
            
            <div className="mt-12 grid grid-cols-1 sm:grid-cols-3 gap-8 text-center px-4">
              <div>
                <div className="mx-auto w-12 h-12 bg-green-100 rounded-full flex items-center justify-center mb-3">
                  <ShieldCheck className="w-6 h-6 text-green-600" />
                </div>
                <h3 className="font-semibold text-slate-900">Strict Reconciliation</h3>
                <p className="text-sm text-slate-500 mt-1">Row-by-row math validation to ensure 100% accuracy.</p>
              </div>
              <div>
                 <div className="mx-auto w-12 h-12 bg-purple-100 rounded-full flex items-center justify-center mb-3">
                  <FileText className="w-6 h-6 text-purple-600" />
                </div>
                <h3 className="font-semibold text-slate-900">Smart Categorization</h3>
                <p className="text-sm text-slate-500 mt-1">AI automatically tags expenses (Rent, Utilities, etc.).</p>
              </div>
              <div>
                 <div className="mx-auto w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center mb-3">
                  <Loader2 className="w-6 h-6 text-blue-600" />
                </div>
                <h3 className="font-semibold text-slate-900">Instant Excel Export</h3>
                <p className="text-sm text-slate-500 mt-1">Get a formatted .xlsx report ready for your finance team.</p>
              </div>
            </div>
          </div>
        )}

        {status === AppStatus.ANALYZING && (
          <div className="flex-1 flex flex-col items-center justify-center p-6 animate-in fade-in duration-500">
             <div className="relative">
                <div className="w-24 h-24 border-4 border-slate-200 border-t-blue-600 rounded-full animate-spin"></div>
                <div className="absolute inset-0 flex items-center justify-center">
                  <ShieldCheck className="w-8 h-8 text-slate-400" />
                </div>
             </div>
             <h2 className="mt-8 text-2xl font-bold text-slate-900">Analyzing Statement...</h2>
             <p className="text-slate-500 mt-2 max-w-md text-center">
               Gemini is reading "{fileName}". This involves text extraction, reconciliation checks, and category assignment. This may take up to 30 seconds.
             </p>
          </div>
        )}

        {status === AppStatus.ERROR && (
          <div className="flex-1 flex flex-col items-center justify-center p-6 animate-in fade-in duration-500">
            <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mb-6">
              <ShieldCheck className="w-8 h-8 text-red-600" />
            </div>
            <h2 className="text-2xl font-bold text-slate-900">Analysis Failed</h2>
            <p className="text-slate-500 mt-2 max-w-md text-center mb-8">
              We couldn't process this file. It might be blurry, password-protected, or in an unsupported format.
              <br/>
              <span className="text-sm text-red-500 font-medium">Tip: Check if your API Key has quota remaining in Settings.</span>
            </p>
            <button 
              onClick={() => setStatus(AppStatus.IDLE)}
              className="px-6 py-3 bg-slate-900 text-white font-medium rounded-lg hover:bg-slate-800 transition-colors"
            >
              Try Another File
            </button>
          </div>
        )}

        {status === AppStatus.COMPLETE && data && (
          <div className="flex-1 animate-in slide-in-from-bottom-4 duration-700">
             <div className="bg-slate-100 border-b border-slate-200 px-4 py-2 flex justify-center">
                <button 
                  onClick={() => setStatus(AppStatus.IDLE)}
                  className="text-sm text-slate-500 hover:text-blue-600 underline"
                >
                  Analyze another file
                </button>
             </div>
            <AnalysisDashboard data={data} />
          </div>
        )}
      </main>
    </div>
  );
};

export default App;
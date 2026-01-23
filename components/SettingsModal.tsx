import React, { useState, useEffect } from 'react';
import { X, Key, Save, Check, ExternalLink } from 'lucide-react';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (key: string) => void;
  currentKey: string;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose, onSave, currentKey }) => {
  const [key, setKey] = useState(currentKey);
  const [showSuccess, setShowSuccess] = useState(false);

  useEffect(() => {
    setKey(currentKey);
  }, [currentKey, isOpen]);

  const handleSave = () => {
    onSave(key);
    setShowSuccess(true);
    setTimeout(() => {
      setShowSuccess(false);
      onClose();
    }, 1500);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#0f172a]/70 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-white w-full max-w-md rounded-2xl shadow-2xl border border-white/20 overflow-hidden transform transition-all scale-100">
        <div className="bg-[#0f172a] px-6 py-4 flex justify-between items-center border-b border-slate-800">
          <div className="flex items-center gap-2 text-white">
            <Key className="w-5 h-5 text-blue-400" />
            <h3 className="text-lg font-bold">API Configuration</h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-6">
          <div>
            <label className="block text-sm font-semibold text-slate-900 mb-2">
              Gemini API Key
            </label>
            <div className="relative">
              <input
                type="password"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder="AIzaSy..."
                className="w-full pl-4 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all text-sm font-mono text-slate-900 placeholder:text-slate-400"
              />
            </div>
            <p className="mt-3 text-xs text-slate-500 leading-relaxed">
              Your API key is used directly to authenticate requests with Google's servers. It is stored locally in your browser and is never transmitted to our backend.
            </p>
            <a 
              href="https://aistudio.google.com/app/apikey" 
              target="_blank" 
              rel="noreferrer"
              className="inline-flex items-center gap-1 mt-3 text-xs font-semibold text-blue-600 hover:text-blue-800"
            >
              Generate a key in Google AI Studio <ExternalLink className="w-3 h-3" />
            </a>
          </div>

          <div className="flex gap-3 pt-2">
            <button
              onClick={onClose}
              className="flex-1 px-4 py-3 text-slate-600 font-semibold bg-white border border-slate-200 hover:bg-slate-50 rounded-xl transition-all"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={showSuccess}
              className={`flex-1 px-4 py-3 font-semibold rounded-xl transition-all flex items-center justify-center gap-2 shadow-lg hover:shadow-xl hover:-translate-y-0.5
                ${showSuccess 
                  ? 'bg-emerald-600 text-white' 
                  : 'bg-slate-900 hover:bg-slate-800 text-white'
                }`}
            >
              {showSuccess ? (
                <>
                  <Check className="w-4 h-4" /> Saved
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" /> Save
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
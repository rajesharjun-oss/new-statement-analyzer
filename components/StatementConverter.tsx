import { useEffect, useRef, useState } from "react";
import type { DragEvent, FormEvent } from "react";
import { AlertCircle, CheckCircle2, Download, FileSpreadsheet, FileText, LoaderCircle, Upload, X } from "lucide-react";
import "./statement-converter.css";

const banks = [
  ["auto", "Auto-detect bank"], ["access", "Access Bank"], ["apt_securities", "APT Securities"],
  ["ecobank", "Ecobank"], ["fcmb", "FCMB"], ["fidelity", "Fidelity Bank"], ["firstbank", "First Bank"],
  ["gtbank", "GTBank"], ["gtco", "GTCO"], ["keystone", "Keystone Bank"], ["moniepoint", "Moniepoint"],
  ["opay", "OPay"], ["providus", "Providus Bank"], ["standard_chartered", "Standard Chartered"],
  ["sterling", "Sterling Bank"], ["uba", "UBA"], ["wema", "Wema Bank"], ["zenith", "Zenith Bank"],
] as const;

interface Converted {
  url: string;
  filename: string;
  count: number;
  matched: boolean;
}

const maxBytes = 20 * 1024 * 1024;
const xlsxMime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

function excelFilename(name: string) {
  const base = name.replace(/\.pdf$/i, "").replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_").slice(0, 160).trim();
  return `${base || "Statement"}.xlsx`;
}

interface Props {
  initialFile: File | null;
  initialBank: string;
  onClose: () => void;
}

export default function StatementConverter({ initialFile, initialBank, onClose }: Props) {
  const [file, setFile] = useState(initialFile);
  const [bank, setBank] = useState(initialBank);
  const [password, setPassword] = useState("");
  const [needsPassword, setNeedsPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const [converted, setConverted] = useState<Converted | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const passwordInput = useRef<HTMLInputElement>(null);
  const request = useRef<AbortController | null>(null);

  useEffect(() => {
    if (dialog.current && !dialog.current.open) dialog.current.showModal();
  }, []);
  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => {
    if (converted) return () => URL.revokeObjectURL(converted.url);
  }, [converted]);
  useEffect(() => {
    if (needsPassword && !busy) passwordInput.current?.focus();
  }, [needsPassword, busy]);

  function selectFile(next: File | null) {
    if (request.current) return;
    setConverted(null);
    setPassword("");
    setNeedsPassword(false);
    setDragging(false);
    if (next && (!/\.pdf$/i.test(next.name) || !next.size || next.size > maxBytes)) {
      setFile(null);
      setError("Choose a non-empty PDF no larger than 20 MB.");
    } else {
      setFile(next);
      setError("");
    }
  }

  function drop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    if (busy) return;
    if (event.dataTransfer.files.length > 1) {
      selectFile(null);
      setError("Choose one statement PDF at a time.");
    } else if (event.dataTransfer.files.length === 1) {
      selectFile(event.dataTransfer.files[0]);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || request.current) return;
    const controller = new AbortController();
    request.current = controller;
    const timer = window.setTimeout(() => controller.abort(), 300_000);
    setBusy(true);
    setError("");
    setConverted(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("bank", bank);
      if (password) form.append("password", password);
      const response = await fetch("/convert", { method: "POST", body: form, signal: controller.signal });
      if (!response.ok) {
        const { detail } = await response.json().catch(() => ({}));
        if (detail?.code === "pdf_password_required") {
          setNeedsPassword(true);
          setPassword("");
        }
        const message = response.status === 503 || response.status === 429
          ? "The converter is busy. Try again shortly."
          : typeof detail === "string" ? detail : detail?.message || "Conversion failed. Try again.";
        throw new Error(message);
      }
      if (!response.headers.get("Content-Type")?.startsWith(xlsxMime)) {
        throw new Error("The converter did not return an Excel workbook. Try again.");
      }
      const workbook = await response.blob();
      if (controller.signal.aborted) return;
      setConverted({
        url: URL.createObjectURL(workbook), filename: excelFilename(file.name),
        count: Number(response.headers.get("X-Transaction-Count") || 0),
        matched: response.headers.get("X-Statement-Check") === "matched",
      });
      setPassword("");
      setNeedsPassword(false);
    } catch (failure) {
      setError(controller.signal.aborted ? "Conversion timed out. Try again." :
        failure instanceof TypeError ? "The converter could not be reached. Check your connection and retry." :
        failure instanceof Error ? failure.message : "Conversion failed. Try again.");
    } finally {
      window.clearTimeout(timer);
      request.current = null;
      setBusy(false);
    }
  }

  return (
    <dialog ref={dialog} className="converter" aria-labelledby="pdf-to-excel-title" onClose={onClose}>
      <div className="converter-main">
        <div className="converter-heading">
          <h2 id="pdf-to-excel-title">PDF to Excel</h2>
          <button type="button" className="converter-icon" title="Close converter" aria-label="Close converter" onClick={() => dialog.current?.close()}>
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <form aria-label="Convert a bank statement" aria-busy={busy} onSubmit={submit}>
          <div className="converter-settings">
            <label htmlFor="statement-bank">Issuing bank</label>
            <select id="statement-bank" disabled={busy} value={bank} onChange={(event) => {
              setBank(event.target.value);
              setConverted(null);
              setError("");
            }}>
              {banks.map(([key, name]) => <option key={key} value={key}>{name}</option>)}
            </select>
          </div>
          <input ref={input} type="file" accept=".pdf,application/pdf" aria-label="Statement PDF" hidden
            onChange={(event) => {
              selectFile(event.currentTarget.files?.[0] || null);
              event.currentTarget.value = "";
            }} />
          <div className={`converter-drop${dragging ? " is-dragging" : ""}${file ? " has-file" : ""}`}
            onDragOver={(event) => { event.preventDefault(); if (!busy) setDragging(true); }}
            onDragLeave={(event) => {
              if (!(event.relatedTarget instanceof Node) || !event.currentTarget.contains(event.relatedTarget)) setDragging(false);
            }} onDrop={drop}>
            {file ? (
              <>
                <FileText size={22} aria-hidden="true" />
                <div className="converter-file"><strong>{file.name}</strong><span>{(file.size / (1024 * 1024)).toFixed(2)} MB</span></div>
                <button type="button" title="Remove PDF" aria-label="Remove PDF" className="converter-icon" disabled={busy} onClick={() => selectFile(null)}><X size={18} aria-hidden="true" /></button>
              </>
            ) : (
              <>
                <Upload size={24} aria-hidden="true" />
                <span className="converter-file-limit">PDF, up to 20 MB</span>
                <button type="button" className="converter-button secondary" onClick={() => input.current?.click()}>Choose PDF</button>
              </>
            )}
          </div>
          {needsPassword && <div className="converter-settings">
            <label htmlFor="statement-password">PDF password</label>
            <input id="statement-password" ref={passwordInput} autoComplete="off" type="password" maxLength={256} required value={password} disabled={busy} onChange={(event) => setPassword(event.target.value)} />
          </div>}
          {error && <p className="converter-message error" role="alert"><AlertCircle size={18} aria-hidden="true" />{error}</p>}
          <div className="converter-actions">
            {busy && <span role="status" className="converter-muted">Extracting and checking transactions</span>}
            <button type="submit" className="converter-button primary" disabled={!file || busy}>
              {busy ? <LoaderCircle className="converter-spinner" size={17} aria-hidden="true" /> : <FileSpreadsheet size={17} aria-hidden="true" />}
              {busy ? "Converting..." : "Convert to Excel"}
            </button>
          </div>
        </form>
        {converted && <section className="converter-result" aria-label="Conversion result">
          <div className="converter-result-copy" role="status">
            <strong><CheckCircle2 size={18} aria-hidden="true" /> Workbook ready</strong>
            <span>{converted.count.toLocaleString()} {converted.count === 1 ? "transaction" : "transactions"}{" / "}{converted.matched ? "Totals match statement" : "Statement totals unavailable"}</span>
          </div>
          <a className="converter-button secondary" href={converted.url} download={converted.filename}><Download size={17} aria-hidden="true" /> Download Excel</a>
        </section>}
      </div>
    </dialog>
  );
}

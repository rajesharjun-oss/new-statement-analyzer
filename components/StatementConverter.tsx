import { useEffect, useRef, useState } from "react";
import type { DragEvent, FormEvent } from "react";
import { AlertCircle, ArrowDownToLine, ArrowRight, CheckCircle2, Download, FileSpreadsheet, FileText, LoaderCircle, LockKeyhole, RefreshCw, Upload, X } from "lucide-react";
import { statementBanks } from "../services/statementBanks";
import "./statement-converter.css";

interface Converted {
  url: string;
  filename: string;
  count: number;
  matched: boolean;
}

type Transfer = { phase: "uploading"; percent: number | null } | { phase: "processing" };
type ConversionError = { detail?: string | { code?: string; message?: string } };

const maxBytes = 20 * 1024 * 1024;
const xlsxMime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

function excelFilename(name: string) {
  const base = name.replace(/\.pdf$/i, "").replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_").slice(0, 160).trim();
  return `${base || "Statement"}.xlsx`;
}

export default function StatementConverter() {
  const [file, setFile] = useState<File | null>(null);
  const [bank, setBank] = useState("auto");
  const [password, setPassword] = useState("");
  const [needsPassword, setNeedsPassword] = useState(false);
  const [transfer, setTransfer] = useState<Transfer | null>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const [converted, setConverted] = useState<Converted | null>(null);
  const busy = transfer !== null;
  const input = useRef<HTMLInputElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const pickFile = useRef<HTMLButtonElement>(null);
  const selectedFile = useRef<HTMLDivElement>(null);
  const fileChanged = useRef(false);
  const convertButton = useRef<HTMLButtonElement>(null);
  const downloadLink = useRef<HTMLAnchorElement>(null);
  const passwordInput = useRef<HTMLInputElement>(null);
  const request = useRef<XMLHttpRequest | null>(null);

  useEffect(() => () => {
    const active = request.current;
    request.current = null;
    active?.abort();
  }, []);
  useEffect(() => {
    if (converted) {
      downloadLink.current?.focus();
      return () => URL.revokeObjectURL(converted.url);
    }
  }, [converted]);
  useEffect(() => {
    if (!fileChanged.current) return;
    fileChanged.current = false;
    if (file) selectedFile.current?.focus();
    else pickFile.current?.focus();
  }, [file]);
  useEffect(() => {
    if (busy || !file || converted) return;
    if (needsPassword && !passwordInput.current?.value) passwordInput.current?.focus();
    else if (document.activeElement === document.body && formRef.current?.getClientRects().length) convertButton.current?.focus();
  }, [needsPassword, busy, file, converted]);

  function selectFile(next: File | null) {
    if (request.current) return;
    setDragging(false);
    if (next && (!/\.pdf$/i.test(next.name) || !next.size || next.size > maxBytes)) {
      setError("Choose a non-empty PDF no larger than 20 MB.");
      return;
    }
    setConverted(null);
    setPassword("");
    setNeedsPassword(false);
    fileChanged.current = true;
    setFile(next);
    setError("");
  }

  function drop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    if (busy) return;
    if (event.dataTransfer.files.length > 1) {
      setError("Choose one statement PDF at a time.");
    } else if (event.dataTransfer.files.length === 1) {
      selectFile(event.dataTransfer.files[0]);
    }
  }

  function stopWaiting() {
    const active = request.current;
    request.current = null;
    active?.abort();
    setTransfer(null);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || request.current || converted) return;
    const xhr = new XMLHttpRequest();
    request.current = xhr;
    setTransfer({ phase: "uploading", percent: null });
    setError("");

    function finish() {
      if (request.current !== xhr) return false;
      request.current = null;
      setTransfer(null);
      return true;
    }

    function fail(message: string) {
      if (finish()) setError(message);
    }

    xhr.upload.addEventListener("progress", ({ lengthComputable, loaded, total }) => {
      if (request.current === xhr && lengthComputable && total > 0) {
        setTransfer({ phase: "uploading", percent: Math.min(100, Math.floor(loaded / total * 100)) });
      }
    });
    xhr.upload.addEventListener("load", () => {
      if (request.current === xhr) setTransfer({ phase: "processing" });
    });
    xhr.addEventListener("timeout", () => fail("Conversion timed out. Try again."));
    xhr.addEventListener("error", () => fail("The converter could not be reached. Check your connection and retry."));
    xhr.addEventListener("load", async () => {
      if (request.current !== xhr) return;
      if (xhr.status < 200 || xhr.status >= 300) {
        const body: ConversionError | null = await (xhr.response as Blob | null)?.text().then(JSON.parse).catch(() => null) ?? null;
        const detail = body?.detail;
        const reason = typeof detail === "string" ? detail : detail?.message;
        if (!finish()) return;
        if (typeof detail === "object" && detail?.code === "pdf_password_required") {
          setNeedsPassword(true);
          setPassword("");
        }
        setError(xhr.status === 503 || xhr.status === 429
          ? "The converter is busy. Try again shortly."
          : typeof reason === "string" && reason ? reason : "Conversion failed. Try again.");
        return;
      }
      const workbook = xhr.response as Blob | null;
      if (!xhr.getResponseHeader("Content-Type")?.startsWith(xlsxMime) || !workbook?.size) {
        fail("The converter did not return an Excel workbook. Try again.");
        return;
      }
      if (!finish()) return;
      setConverted({
        url: URL.createObjectURL(workbook), filename: excelFilename(file.name),
        count: Number(xhr.getResponseHeader("X-Transaction-Count") || 0),
        matched: xhr.getResponseHeader("X-Statement-Check") === "matched",
      });
      setPassword("");
      setNeedsPassword(false);
    });

    try {
      const form = new FormData();
      form.append("file", file);
      form.append("bank", bank);
      if (needsPassword && password) form.append("password", password);
      xhr.open("POST", "/convert");
      xhr.responseType = "blob";
      xhr.timeout = 300_000;
      xhr.send(form);
    } catch {
      fail("The converter could not be reached. Check your connection and retry.");
    }
  }

  return (
    <section className="converter" aria-labelledby="pdf-to-excel-title">
      <header className="converter-heading">
        <h1 id="pdf-to-excel-title">PDF to Excel</h1>
        <div className="converter-format" aria-label="PDF input, Excel workbook output">
          <span><FileText size={17} aria-hidden="true" /> PDF</span>
          <ArrowRight size={16} aria-hidden="true" />
          <span><FileSpreadsheet size={17} aria-hidden="true" /> XLSX</span>
        </div>
      </header>
      <form ref={formRef} className="converter-form" aria-label="Convert a bank statement" onSubmit={submit}>
        <div className="converter-grid">
          <div className="converter-source">
            <h2>Bank statement</h2>
            <input ref={input} type="file" accept=".pdf,application/pdf" aria-label="Statement PDF" hidden
              onChange={(event) => {
                const next = event.currentTarget.files?.[0];
                if (next) selectFile(next);
                event.currentTarget.value = "";
              }} />
            <div className={`converter-file-area${dragging ? " is-dragging" : ""}${file ? " has-file" : ""}`}
              onDragOver={(event) => {
                event.preventDefault();
                event.dataTransfer.dropEffect = busy ? "none" : "copy";
                if (!busy && event.dataTransfer.types.includes("Files")) setDragging(true);
              }}
              onDragLeave={(event) => {
                if (!(event.relatedTarget instanceof Node) || !event.currentTarget.contains(event.relatedTarget)) setDragging(false);
              }} onDrop={drop}>
              {file ? (
                <>
                  <div ref={selectedFile} tabIndex={-1} className="converter-selected">
                    <span className="converter-file-icon"><FileText size={21} aria-hidden="true" /></span>
                    <div className="converter-file"><strong>{file.name}</strong><span>{file.size < 1024 * 1024 ? `${Math.max(1, Math.round(file.size / 1024))} KB` : `${(file.size / (1024 * 1024)).toFixed(2)} MB`}</span></div>
                    <div className="converter-file-actions">
                      <button type="button" className="converter-replace" aria-label="Replace PDF" disabled={busy} onClick={() => input.current?.click()}><RefreshCw size={14} aria-hidden="true" /> Replace</button>
                      <button type="button" title="Remove PDF" aria-label="Remove PDF" className="converter-icon" disabled={busy} onClick={() => selectFile(null)}><X size={17} aria-hidden="true" /></button>
                    </div>
                  </div>
                  <div role="status" className="converter-status">
                    {transfer?.phase === "uploading" && <span>Uploading PDF</span>}
                    {transfer?.phase === "processing" && <span className="converter-processing"><LoaderCircle size={16} className="converter-spinner" aria-hidden="true" /> Extracting and checking transactions</span>}
                    {converted && <div className="converter-result-copy">
                      <strong><CheckCircle2 size={17} aria-hidden="true" /> Workbook ready</strong>
                      <span>{converted.count.toLocaleString()} {converted.count === 1 ? "transaction" : "transactions"} <span aria-hidden="true">/</span> {converted.matched ? "Totals match statement" : "Statement totals unavailable"}</span>
                    </div>}
                  </div>
                  {transfer?.phase === "uploading" && <div className="converter-progress">
                    <progress aria-label="PDF upload progress" max={100} value={transfer.percent ?? undefined} />
                    {transfer.percent !== null && <span aria-hidden="true">{transfer.percent}%</span>}
                  </div>}
                  {needsPassword && <div className="converter-password">
                    <label htmlFor="statement-password"><LockKeyhole size={16} aria-hidden="true" /> PDF password</label>
                    <input id="statement-password" ref={passwordInput} autoComplete="off" type="password" maxLength={256} required value={password} disabled={busy} onChange={(event) => setPassword(event.target.value)} />
                  </div>}
                </>
              ) : (
                <button ref={pickFile} type="button" className="converter-drop" onClick={() => input.current?.click()} aria-label="Browse for a statement PDF" aria-describedby="statement-file-limit">
                  <span className="converter-upload-icon"><Upload size={23} aria-hidden="true" /></span>
                  <strong>Drop a bank statement here</strong>
                  <span className="converter-browse">Browse PDF <ArrowRight size={15} aria-hidden="true" /></span>
                  <span id="statement-file-limit" className="converter-file-limit">One PDF, up to 20 MB</span>
                </button>
              )}
              {error && <p className="converter-message" role="alert"><AlertCircle size={17} aria-hidden="true" />{error}</p>}
            </div>
          </div>
          <div className="converter-settings">
            <label htmlFor="statement-bank">Issuing bank</label>
            <select id="statement-bank" disabled={busy} value={bank} onChange={(event) => {
              setBank(event.target.value);
              setConverted(null);
              setError("");
            }}>
              {statementBanks.map(([key, name]) => <option key={key} value={key}>{name}</option>)}
            </select>
            <div className="converter-output">
              <span className="converter-output-icon"><ArrowDownToLine size={17} aria-hidden="true" /></span>
              <div><strong>Excel workbook</strong><span>One worksheet</span></div>
            </div>
          </div>
        </div>
        <div className="converter-actions">
            {busy && <button type="button" className="converter-button secondary" onClick={stopWaiting}>
              {transfer.phase === "uploading" ? "Cancel upload" : "Stop waiting"}
            </button>}
            {converted ? (
              <a ref={downloadLink} className="converter-button primary" href={converted.url} download={converted.filename}><Download size={17} aria-hidden="true" /> Download Excel</a>
            ) : (
              <button ref={convertButton} type="submit" className="converter-button primary" disabled={!file || busy}>
                <FileSpreadsheet size={17} aria-hidden="true" /> {busy ? "Converting..." : "Convert to Excel"}
              </button>
            )}
        </div>
      </form>
    </section>
  );
}

import { Transaction } from '../types';
import * as pdfjsLib from 'pdfjs-dist/build/pdf';

interface TextItem {
    str: string;
    x: number;
    y: number;
    h: number;
    w: number;
}

interface Row {
    y: number;
    items: TextItem[];
}

interface ColumnDefinition {
    id: string; // 'date' | 'description' | 'debit' | 'credit' | 'balance' | 'amount' | 'unknown'
    xMin: number;
    xMax: number;
    center: number;
}

const Y_TOLERANCE = 4;
const MIN_COLUMN_GAP = 15;

export const runBatch = async (arrayBuffer: ArrayBuffer): Promise<{ transactions: Transaction[], metadata: any }> => {
    if (!pdfjsLib.GlobalWorkerOptions.workerSrc) {
        pdfjsLib.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjsLib.version}/pdf.worker.min.js`;
    }

    try {
        const loadingTask = pdfjsLib.getDocument({ data: arrayBuffer });
        const pdf = await loadingTask.promise;
        console.log(`DEBUG: PDF Loaded. Pages: ${pdf.numPages}`);
        const allTransactions: Transaction[] = [];

        for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
            const page = await pdf.getPage(pageNum);
            const content = await page.getTextContent();

            if (content.items.length === 0) {
                console.warn(`DEBUG: Page ${pageNum} returned no text content.`);
                continue;
            }

            console.log(`DEBUG: Page ${pageNum} Item Count: ${content.items.length}`);
            const sampleText = content.items.slice(0, 5).map((i: any) => i.str).join(" | ");
            console.log(`DEBUG: Page ${pageNum} Sample: ${sampleText}`);

            const viewport = page.getViewport({ scale: 1.0 });
            const pageWidth = Math.ceil(viewport.width);

            const items: TextItem[] = content.items.map((item: any) => ({
                str: item.str,
                x: item.transform[4],
                y: item.transform[5],
                h: item.height,
                w: item.width
            })).filter(i => i.str.trim().length > 0);

            if (items.length === 0) continue;

            items.sort((a, b) => b.y - a.y);
            const rows: Row[] = [];
            let currentRow: Row = { y: items[0].y, items: [items[0]] };

            for (let i = 1; i < items.length; i++) {
                const item = items[i];
                if (Math.abs(item.y - currentRow.y) < Y_TOLERANCE) {
                    currentRow.items.push(item);
                } else {
                    currentRow.items.sort((a, b) => a.x - b.x);
                    rows.push(currentRow);
                    currentRow = { y: item.y, items: [item] };
                }
            }
            currentRow.items.sort((a, b) => a.x - b.x);
            rows.push(currentRow);

            console.log(`DEBUG: Page ${pageNum} Rows Formed: ${rows.length}`);

            const columns = detectColumns(rows, pageWidth);
            console.log(`DEBUG: Page ${pageNum} Columns Detected:`, columns);

            const pageTxns = processRowsToTransactions(rows, columns);
            console.log(`DEBUG: Page ${pageNum} Transactions Found: ${pageTxns.length}`);
            allTransactions.push(...pageTxns);
        }

        return { transactions: allTransactions, metadata: { totalDebit: 0, totalCredit: 0 } };
    } catch (e) {
        console.error("DEBUG: runBatch Error:", e);
        return { transactions: [], metadata: { totalDebit: 0, totalCredit: 0 } };
    }
};

const detectColumns = (rows: Row[], pageWidth: number): ColumnDefinition[] => {
    const histogramLen = Math.ceil(pageWidth) + 10;
    const busy = new Uint8Array(histogramLen).fill(0);

    rows.forEach(row => {
        row.items.forEach(item => {
            const start = Math.max(0, Math.floor(item.x));
            const end = Math.min(histogramLen - 1, Math.floor(item.x + item.w));
            for (let k = start; k < end; k++) busy[k] = 1;
        });
    });

    const columns: ColumnDefinition[] = [];
    let inBlock = false;
    let blockStart = 0;

    for (let i = 0; i < histogramLen; i++) {
        if (busy[i] === 1) {
            if (!inBlock) {
                inBlock = true;
                blockStart = i;
            }
        } else {
            if (inBlock) {
                inBlock = false;
                columns.push({
                    id: 'unknown',
                    xMin: blockStart,
                    xMax: i,
                    center: blockStart + (i - blockStart) / 2
                });
            }
        }
    }

    const viableColumns = columns.filter(c => (c.xMax - c.xMin) > 10);

    let headerRow: Row | null = null;
    let maxMatches = 0;

    const signatures: Record<string, RegExp> = {
        'date': /DATE|DT|TIME/i,
        'description': /DESC|PARTICULARS|DETAILS|NARRATION|TRANSACTION|REMARKS|MEMO/i,
        'debit': /DEBIT|WITHDRAWAL|DR|WK|OUT/i,
        'credit': /CREDIT|DEPOSIT|CR|IN/i,
        'balance': /BALANCE|BAL/i,
        'amount': /AMOUNT|VALUE/i
    };

    for (const row of rows) {
        const txt = row.items.map(i => i.str).join(' ').toUpperCase();
        let matches = 0;
        if (signatures.date.test(txt)) matches++;
        if (signatures.description.test(txt)) matches++;
        if (signatures.balance.test(txt)) matches++;

        if (matches > maxMatches) {
            maxMatches = matches;
            headerRow = row;
        }
    }

    if (headerRow) {
        headerRow.items.forEach(item => {
            const center = item.x + item.w / 2;
            const txt = item.str.toUpperCase();

            const col = viableColumns.find(c => center >= c.xMin && center <= c.xMax);
            if (col) {
                if (signatures.date.test(txt)) col.id = 'date';
                else if (signatures.description.test(txt)) col.id = 'description';
                else if (signatures.debit.test(txt)) col.id = 'debit';
                else if (signatures.credit.test(txt)) col.id = 'credit';
                else if (signatures.balance.test(txt)) col.id = 'balance';
                else if (signatures.amount.test(txt)) col.id = 'amount';
            }
        });
    } else {
        if (viableColumns.length >= 2) {
            viableColumns[0].id = 'date';
            viableColumns[viableColumns.length - 1].id = 'balance';

            let widestIdx = -1;
            let maxW = 0;
            viableColumns.forEach((c, idx) => {
                if (c.id === 'unknown') {
                    const w = c.xMax - c.xMin;
                    if (w > maxW) { maxW = w; widestIdx = idx; }
                }
            });
            if (widestIdx !== -1) viableColumns[widestIdx].id = 'description';
        }
    }

    const hasDate = viableColumns.some(c => c.id === 'date');
    const hasMoney = viableColumns.some(c => c.id === 'debit' || c.id === 'credit' || c.id === 'balance' || c.id === 'amount');

    if (!hasDate || !hasMoney) {
        viableColumns.sort((a, b) => a.xMin - b.xMin);
        if (viableColumns.length > 0) viableColumns[0].id = 'date';
        if (viableColumns.length > 1) viableColumns[viableColumns.length - 1].id = 'balance';

        let widestIdx = -1;
        let maxW = 0;

        for (let i = 1; i < viableColumns.length - 1; i++) {
            const w = viableColumns[i].xMax - viableColumns[i].xMin;
            if (w > maxW) {
                maxW = w;
                widestIdx = i;
            }
        }

        if (widestIdx !== -1) {
            viableColumns[widestIdx].id = 'description';
            const moneyCols = viableColumns.filter((c, idx) => idx > widestIdx && idx < viableColumns.length - 1);
            if (moneyCols.length === 2) {
                moneyCols[0].id = 'debit';
                moneyCols[1].id = 'credit';
            } else if (moneyCols.length === 1) {
                moneyCols[0].id = 'amount';
            }
        }
    }

    console.log("Final Columns:", viableColumns);
    return viableColumns;
};

const processRowsToTransactions = (rows: Row[], columns: ColumnDefinition[]): Transaction[] => {
    const results: Transaction[] = [];
    let currentTxn: Transaction | null = null;

    const cd = {
        date: columns.find(c => c.id === 'date'),
        desc: columns.find(c => c.id === 'description'),
        debit: columns.find(c => c.id === 'debit'),
        credit: columns.find(c => c.id === 'credit'),
        bal: columns.find(c => c.id === 'balance'),
        amount: columns.find(c => c.id === 'amount')
    };

    const dateRegex = new RegExp(
        "^(" +
        "\\d{1,2}[-/\\.]\\w{3}[-/\\.]\\d{2,4}|" +
        "\\d{1,2}[-/\\.]\\d{2}[-/\\.]\\d{2,4}|" +
        "(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\\s\\.,-]+\\d{1,2}(?:st|nd|rd|th)?[\\s\\.,-]+(?:\\d{2,4})?|" +
        "\\d{1,2}[\\s\\.,-]+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\\s\\.,-]+(?:\\d{2,4})?" +
        ")", "i"
    );

    rows.forEach(row => {
        let rowDate = "";
        let rowDescParts: string[] = [];
        let rowDebit = 0;
        let rowCredit = 0;
        let rowBal = 0;
        let foundMoney = false;

        row.items.forEach(item => {
            const cx = item.x + item.w / 2;
            const text = item.str.trim();
            if (!text) return;

            if (cd.date && cx >= cd.date.xMin && cx <= cd.date.xMax) {
                rowDate = text;
            } else if (cd.debit && cx >= cd.debit.xMin && cx <= cd.debit.xMax) {
                const val = parseMoney(text);
                if (val !== null) { rowDebit = Math.abs(val); foundMoney = true; }
            } else if (cd.credit && cx >= cd.credit.xMin && cx <= cd.credit.xMax) {
                const val = parseMoney(text);
                if (val !== null) { rowCredit = Math.abs(val); foundMoney = true; }
            } else if (cd.bal && cx >= cd.bal.xMin && cx <= cd.bal.xMax) {
                const val = parseMoney(text);
                if (val !== null) { rowBal = val; }
            } else if (cd.amount && cx >= cd.amount.xMin && cx <= cd.amount.xMax) {
                const val = parseMoney(text);
                if (val !== null) {
                    if (val < 0) {
                        rowDebit = Math.abs(val);
                    } else {
                        rowCredit = val;
                    }
                    foundMoney = true;
                }
            } else if (cd.desc && cx >= cd.desc.xMin && cx <= cd.desc.xMax) {
                rowDescParts.push(text);
            } else {
                if (parseMoney(text) === null) rowDescParts.push(text);
            }
        });

        const rowDesc = rowDescParts.join(" ").trim();
        const hasDate = dateRegex.test(rowDate);
        const hasAmount = foundMoney && (rowDebit > 0 || rowCredit > 0);

        if (hasDate && hasAmount) {
            if (currentTxn) results.push(currentTxn);

            currentTxn = {
                date: normalizeDate(rowDate),
                description: rowDesc,
                category: "Unallocated",
                debit: rowDebit,
                credit: rowCredit,
                balance: rowBal,
                is_reversal: false
            };
        } else {
            if (currentTxn && !hasDate) {
                if (rowDesc) {
                    currentTxn.description += " " + rowDesc;
                }
            }
        }
    });

    if (currentTxn) results.push(currentTxn);
    return results;
};

const parseMoney = (str: string): number | null => {
    if (!str) return null;
    if (!/[\d\.,]+/.test(str)) return null;

    const isNegative = /^\(.*\)$/.test(str.trim()) || str.includes('-');
    const clean = str.replace(/,/g, '').replace(/[^\d\.]/g, '');

    let num = parseFloat(clean);
    if (isNaN(num)) return null;

    if (isNegative) num = -num;
    return num;
};

const normalizeDate = (raw: string): string => {
    if (/^\d{1,2}[-/\.]\w{3}[-/\.]\d{2,4}$/i.test(raw)) {
        return raw.replace(/[\/\.]/g, '-');
    }

    const d = new Date(raw);
    if (!isNaN(d.getTime())) {
        const day = d.getDate().toString().padStart(2, '0');
        const month = d.toLocaleString('default', { month: 'short' });
        const year = d.getFullYear();
        return `${day}-${month}-${year}`;
    }

    return raw.replace(/[\/\.]/g, '-');
};

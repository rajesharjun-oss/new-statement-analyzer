const BACKEND_URL = 'http://localhost:8000';

const statusEl = document.getElementById('status');
const summaryEl = document.getElementById('summary');
const downloadBtn = document.getElementById('downloadBtn');
const spinner = document.getElementById('spinner');

async function analyzeStatement(file) {
    // Reset UI
    summaryEl.classList.remove('show');
    downloadBtn.classList.remove('show');

    // Show loading state
    statusEl.className = 'active';
    statusEl.textContent = '🔄 Uploading and analyzing statement...';
    spinner.classList.add('show');

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch(`${BACKEND_URL}/analyze`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Server error during analysis');
        }

        const result = await response.json();

        // Hide spinner
        spinner.classList.remove('show');

        // Show success
        statusEl.className = 'success';
        statusEl.textContent = '✅ Analysis complete!';

        // Display summary
        document.getElementById('accountName').textContent = result.summary.accountName;
        document.getElementById('period').textContent = result.summary.period;
        document.getElementById('totalDebit').textContent = `₦${result.summary.totalDebit.toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        document.getElementById('totalCredit').textContent = `₦${result.summary.totalCredit.toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        document.getElementById('transactionCount').textContent = result.summary.transactionCount;
        document.getElementById('validationStatus').textContent = result.summary.validationStatus;

        summaryEl.classList.add('show');

        // Setup download button
        downloadBtn.href = `${BACKEND_URL}${result.downloadUrl}`;
        downloadBtn.classList.add('show');

    } catch (error) {
        console.error('Analysis error:', error);
        spinner.classList.remove('show');
        statusEl.className = 'error';
        statusEl.textContent = `❌ Analysis failed: ${error.message}`;
    }
}

// File input handler
document.getElementById('fileInput').addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
        if (!file.name.endsWith('.pdf')) {
            statusEl.className = 'error';
            statusEl.textContent = '❌ Please select a PDF file';
            return;
        }
        analyzeStatement(file);
    }
});

// Drag and drop support
const uploadArea = document.querySelector('.upload-area');

uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.style.background = '#f8f9ff';
});

uploadArea.addEventListener('dragleave', () => {
    uploadArea.style.background = '';
});

uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.style.background = '';

    const file = e.dataTransfer.files[0];
    if (file && file.name.endsWith('.pdf')) {
        analyzeStatement(file);
    } else {
        statusEl.className = 'error';
        statusEl.textContent = '❌ Please drop a PDF file';
    }
});

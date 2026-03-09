import pdfplumber

with pdfplumber.open('temp_uploads/WEMA test.pdf') as pdf:
    # Page 26
    page = pdf.pages[26]
    words = page.extract_words()
    
    header_keywords = ['ID', 'CHEQUE', 'WITHDRAWALS', 'DEPOSITS', 'BALANCE']
    header_words = [w for w in words if any(k in w['text'].upper().strip() for k in header_keywords)]
    
    print('Header locations:')
    for w in header_words:
        if w['text'].upper() in ['ID', 'WITHDRAWALS', 'DEPOSITS', 'BALANCE']:
            print(f"{w['text']}: x0={w['x0']:.2f}, x1={w['x1']:.2f}")
            
    print('\nLarge amounts:')
    for w in words:
        if '200,000,000' in w['text'] or '150,000,000' in w['text']:
            word_mid = w['x1'] - 5
            print(f"{w['text']}: x0={w['x0']:.2f}, x1={w['x1']:.2f}, word_mid={word_mid:.2f}")

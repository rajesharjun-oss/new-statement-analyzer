import os
import json
import anthropic
from typing import List, Dict, Any, Optional

def get_claude_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    return anthropic.Anthropic(api_key=api_key)

def categorize_with_claude(transactions: List[Dict[str, Any]], available_categories: List[str]) -> List[Dict[str, Any]]:
    """
    Use Claude 3.5 Sonnet to categorize transactions that the rule engine missed.
    """
    client = get_claude_client()
    if not client or not transactions:
        return transactions

    input_data = []
    for t in transactions:
        desc = t.get('remarks', '') or t.get('description', '')
        entity = t.get('entity', 'Unknown')
        amt = t.get('debit', 0) or t.get('credit', 0)
        input_data.append(f"Entity: {entity} | Narration: {desc} | Amount: {amt}")

    categories_list = "\n".join([f"- {c}" for c in available_categories])
    
    prompt = f"""You are a specialized Nigerian financial auditor. Categorize the following transactions into the EXACT categories provided.

CATEGORIES:
{categories_list}

TRANSACTIONS:
{chr(10).join(f'{i+1}. {data}' for i, data in enumerate(input_data))}

INSTRUCTIONS:
1. Return ONLY a JSON array of strings (the category names) in the same order as the input.
2. If unsure, use the most likely category based on the Entity or Narration.
3. Be precise with Nigerian context (e.g., IKEDC/EKEDC -> Utilities, NIP -> Transfer).
4. Do NOT include any markdown formatting, just the raw JSON array.
"""

    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=2048,
            temperature=0,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        content = response.content[0].text.strip()
        # Clean potential markdown
        if content.startswith("```json"):
            content = content.split("```json")[1].split("```")[0].strip()
        elif content.startswith("```"):
            content = content.split("```")[1].split("```")[0].strip()
            
        categories = json.loads(content)
        
        for i, category in enumerate(categories):
            if i < len(transactions):
                if category in available_categories:
                    transactions[i]['category'] = category
                    transactions[i]['confidence'] = 0.98
                    transactions[i]['decision_source'] = "AI_CLAUDE"
                else:
                    # Fallback to Uncategorized if Claude hallucinated a category name
                    transactions[i]['category'] = "Uncategorized Expense" if transactions[i].get('debit', 0) > 0 else "Uncategorized Income"
                    transactions[i]['confidence'] = 0.0
                    transactions[i]['decision_source'] = "AI_CLAUDE_FALLBACK"

    except Exception as e:
        print(f"Claude Categorization Error: {e}")
        
    return transactions

def generate_audit_summary(all_transactions: List[Dict[str, Any]], metadata: Dict[str, Any]) -> str:
    """
    Perform a deep-document audit on the entire statement using Claude's large context window.
    """
    client = get_claude_client()
    if not client or not all_transactions:
        return "Audit summary unavailable: Anthropic client not configured."

    # Prepare a condensed version of all transactions for context
    txn_summary = []
    for t in all_transactions:
        date = t.get('date', 'N/A')
        desc = t.get('remarks', '') or t.get('description', '')
        amt = t.get('credit', 0) if t.get('credit', 0) > 0 else -t.get('debit', 0)
        cat = t.get('category', 'Uncategorized')
        txn_summary.append(f"{date} | {amt:,.2f} | {cat} | {desc}")

    full_txn_text = "\n".join(txn_summary)
    
    prompt = f"""You are a Senior Financial Auditor. Review the following bank statement data and provide a concise 'Deep Audit Summary'.

STATEMENT METADATA:
Bank: {metadata.get('bank', 'Unknown')}
Account Name: {metadata.get('account_name', 'Unknown')}
Period: {metadata.get('start_date', 'N/A')} to {metadata.get('end_date', 'N/A')}
Total Debit: {metadata.get('total_debits', 0):,.2f}
Total Credit: {metadata.get('total_credits', 0):,.2f}

TRANSACTIONS (Date | Amount | Category | Narration):
{full_txn_text}

AUDIT OBJECTIVES:
1. Identify any anomalies (e.g., duplicated charges, missing recurring payments, sudden spikes in spending).
2. Summarize the primary cash flow drivers.
3. Detect potential hidden patterns (e.g. personal transfers disguised as business expenses).
4. Provide 2-3 'High Priority Recommendations' for the business owner.

FORMAT: Use clear headings. Keep the summary under 500 words. Be direct and professional.
"""

    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=4096,
            temperature=0,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return response.content[0].text
    except Exception as e:
        return f"Audit generation failed: {str(e)}"

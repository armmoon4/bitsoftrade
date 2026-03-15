import io
import csv
from .zerodha import normalize_zerodha
from .groww import normalize_groww
from .upstox import normalize_upstox

_HEADER_KEYWORDS = (
    'symbol', 'scrip', 'trade_id', 'stock_name', 'execution_date',
    'order_execution_time', 'instrument', 'isin', 'trade_date', 'date',
    'order_id', 'side', 'trade_num', 'segment', 'series',
)

def extract_rows_from_raw_data(raw_data):
    """
    Skip junk header rows (broker name, account info, blanks) and find the
    real column header row.
    """
    header_idx = None
    for i, row in enumerate(raw_data):
        if not any(row):
            continue  # blank row
        row_lower = [str(item).strip().lower() if item else '' for item in row]
        # Match if ANY cell in this row contains a known header keyword
        if any(any(kw in cell for kw in _HEADER_KEYWORDS) for cell in row_lower if cell):
            header_idx = i
            break

    if header_idx is None or not raw_data:
        return []

    headers = [str(h).strip().lower().replace(' ', '_') for h in raw_data[header_idx]]

    rows = []
    for row in raw_data[header_idx + 1:]:
        if any(row):  # skip entirely empty rows
            row_dict = dict(zip(headers, [str(v).strip() if v is not None else '' for v in row]))
            rows.append(row_dict)
    return rows

def parse_csv(file):
    content = file.read().decode('utf-8', errors='ignore')
    sample = content[:2048]
    delimiter = '\t' if sample.count('\t') > sample.count(',') else ','

    reader = csv.reader(io.StringIO(content), delimiter=delimiter)
    raw_data = list(reader)

    return extract_rows_from_raw_data(raw_data)

def parse_excel(file):
    try:
        import openpyxl
    except ImportError:
        raise ImportError('openpyxl not installed. Run: pip install openpyxl')

    wb = openpyxl.load_workbook(file, data_only=True)
    ws = wb.active
    raw_data = list(ws.iter_rows(values_only=True))

    return extract_rows_from_raw_data(raw_data)

def detect_and_normalize(raw_rows, broker_hint=''):
    """
    Auto-detect broker format from headers or broker_hint,
    then return (broker_name, normalized_rows).
    """
    if not raw_rows:
        return 'unknown', []

    headers = set(raw_rows[0].keys())

    # Zerodha detection
    is_zerodha = (
        broker_hint == 'zerodha' or
        'trade_id' in headers or
        {'order_execution_time', 'series', 'segment', 'trade_type'}.issubset(headers)
    )
    if is_zerodha:
        return 'zerodha', normalize_zerodha(raw_rows)

    # Groww detection
    is_groww = (
        broker_hint == 'groww' or
        'stock_name' in headers or
        {'execution_date_and_time', 'order_status'}.issubset(headers)
    )
    if is_groww:
        return 'groww', normalize_groww(raw_rows)
    
    # Upstox detection
    is_upstox = (
        broker_hint == 'upstox' or
        {'scrip_code', 'trade_num', 'side', 'trade_time'}.issubset(headers)
    )
    if is_upstox:
        return 'upstox', normalize_upstox(raw_rows)

    # Fallback: generic format
    return broker_hint or 'generic', raw_rows
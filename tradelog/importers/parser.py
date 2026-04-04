import io
import csv
from .zerodha import normalize_zerodha
from .groww import normalize_groww
from .upstox import normalize_upstox
from .dhan import normalize_dhan
from .angelone import normalize_angelone

# EXACT cell values that identify a real header row.
# Using exact match (cell == keyword) instead of substring (kw in cell)
# to avoid false matches like "DateOfDownload" containing "date".
_HEADER_EXACT = {
    'symbol', 'scrip', 'trade_id', 'stock_name', 'execution_date',
    'order_execution_time', 'instrument', 'isin', 'trade_date', 'date',
    'order_id', 'side', 'trade_num', 'segment', 'series',
    # Dhan
    'buy/sell', 'trade_price',
    # Angel One (before space→underscore normalisation)
    'scrip/contract', 'buy price', 'sell price',
    # Angel One (after normalisation, kept for safety)
    'buy_price', 'sell_price',
}


def _extract_angelone_date(raw_data, header_idx):
    """
    Angel One CSVs have no Date column in the trade rows.
    The date range lives in the metadata rows above the real header.
    Scan those rows for a StartDate value and return it as YYYY-MM-DD.
    """
    from datetime import date as ddate, datetime
    for row in raw_data[:header_idx]:
        for cell in row:
            if cell is None:
                continue
            cell_str = str(cell).strip()
            # Matches "2026-04-01 00:00:00.0" or "2026-04-01"
            if len(cell_str) >= 10 and cell_str[4:5] == '-' and cell_str[7:8] == '-':
                try:
                    return datetime.strptime(cell_str[:10], '%Y-%m-%d').strftime('%Y-%m-%d')
                except ValueError:
                    continue
    return ddate.today().strftime('%Y-%m-%d')


def extract_rows_from_raw_data(raw_data):
    """
    Skip junk header rows (broker name, account info, blanks) and find the
    real column header row using EXACT cell matching.
    """
    header_idx = None
    for i, row in enumerate(raw_data):
        if not any(row):
            continue
        row_lower = [str(item).strip().lower() if item else '' for item in row]
        # Exact match: the cell value itself must be a known header keyword
        if any(cell in _HEADER_EXACT for cell in row_lower if cell):
            header_idx = i
            break

    if header_idx is None or not raw_data:
        return []

    headers = [str(h).strip().lower().replace(' ', '_') for h in raw_data[header_idx]]

    # Detect Angel One: has buy_price + sell_price + scrip/contract but NO date column
    is_angelone_format = (
        'buy_price' in headers and
        'sell_price' in headers and
        'scrip/contract' in headers and
        'date' not in headers
    )

    angelone_date = None
    if is_angelone_format:
        angelone_date = _extract_angelone_date(raw_data, header_idx)

    rows = []
    for row in raw_data[header_idx + 1:]:
        if any(row):
            row_dict = dict(zip(headers, [str(v).strip() if v is not None else '' for v in row]))
            # Inject the extracted date into every Angel One row
            if is_angelone_format and angelone_date:
                row_dict['date'] = angelone_date
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

    IMPORTANT: Angel One must be checked BEFORE Zerodha because Angel One
    CSVs also contain a 'trade_id' column which would falsely trigger Zerodha.
    """
    if not raw_rows:
        return 'unknown', []

    headers = set(raw_rows[0].keys())

    # ── Angel One (must be before Zerodha — both have 'trade_id')
    is_angelone = (
        broker_hint == 'angelone' or
        {'scrip/contract', 'buy/sell', 'buy_price', 'sell_price'}.issubset(headers)
    )
    if is_angelone:
        return 'angelone', normalize_angelone(raw_rows)

    # ── Zerodha
    is_zerodha = (
        broker_hint == 'zerodha' or
        'trade_id' in headers or
        {'order_execution_time', 'series', 'segment', 'trade_type'}.issubset(headers)
    )
    if is_zerodha:
        return 'zerodha', normalize_zerodha(raw_rows)

    # ── Groww
    is_groww = (
        broker_hint == 'groww' or
        'stock_name' in headers or
        {'execution_date_and_time', 'order_status'}.issubset(headers)
    )
    if is_groww:
        return 'groww', normalize_groww(raw_rows)

    # ── Upstox
    is_upstox = (
        broker_hint == 'upstox' or
        {'scrip_code', 'trade_num', 'side', 'trade_time'}.issubset(headers)
    )
    if is_upstox:
        return 'upstox', normalize_upstox(raw_rows)

    # ── Dhan
    is_dhan = (
        broker_hint == 'dhan' or
        {'name', 'buy/sell', 'trade_price', 'trade_value', 'status'}.issubset(headers)
    )
    if is_dhan:
        return 'dhan', normalize_dhan(raw_rows)

    # ── Fallback
    raise ValueError(
        "Unrecognized broker format. Only Zerodha, Groww, Upstox, Dhan, and Angel One CSVs are supported."
    )
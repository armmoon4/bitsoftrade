from decimal import Decimal, ROUND_HALF_UP


def normalize_default(raw_rows):
    """
    Normalizer for the BitsOfTrade Universal Trade Import Template.

    Expected columns (case-insensitive, spaces normalized to underscores):
        REQUIRED: symbol, entry_price, exit_price, quantity, segment,
                  trade_date, entry_time, exit_time, side
        OPTIONAL: strategy, notes
    """

    # Segment keyword → internal segment code
    _SEGMENT_MAP = {
        'fut':        'FO',
        'futures':    'FO',
        'opt':        'FO',
        'options':    'FO',
        'fo':         'FO',
        'f&o':        'FO',
        'eq':         'EQ',
        'equity':     'EQ',
        'cash':       'EQ',
        'cds':        'CDS',
        'currency':   'CDS',
        'forex':      'CDS',
        'com':        'COM',
        'commodity':  'COM',
        'mcx':        'COM',
    }

    _MARKET_TYPE_MAP = {
        'FO':  'options',
        'EQ':  'indian_market',
        'CDS': 'forex',
        'COM': 'indian_market',
    }

    normalized = []

    for row in raw_rows:
        # ── Required fields ──────────────────────────────────────────────────
        symbol = row.get('symbol', '').strip()
        if not symbol:
            continue

        side_raw = row.get('side', '').strip().lower()
        if side_raw not in ('buy', 'sell'):
            continue

        trade_date = row.get('trade_date', '').strip()
        if not trade_date:
            continue

        entry_price_str = row.get('entry_price', '').replace(',', '').strip()
        exit_price_str  = row.get('exit_price',  '').replace(',', '').strip()
        quantity_str    = row.get('quantity',     '').replace(',', '').strip()

        try:
            entry_price = Decimal(entry_price_str) if entry_price_str else Decimal('0')
            quantity    = Decimal(quantity_str)    if quantity_str    else Decimal('0')
        except Exception:
            continue

        if entry_price == 0 or quantity == 0:
            continue

        exit_price = None
        if exit_price_str:
            try:
                ep = Decimal(exit_price_str)
                if ep != 0:
                    exit_price = ep
            except Exception:
                pass

        # ── Segment ──────────────────────────────────────────────────────────
        segment_raw = row.get('segment', '').strip().lower()
        segment     = _SEGMENT_MAP.get(segment_raw, 'EQ')

        # ── Times (optional — default to empty string) ────────────────────
        entry_time = row.get('entry_time', '').strip()
        exit_time  = row.get('exit_time',  '').strip()

        # Earliest of entry/exit used as the trade timestamp
        trade_time = entry_time or exit_time or ''

        # ── Direction (long / short from side) ────────────────────────────
        direction = 'long' if side_raw == 'buy' else 'short'

        # ── Exchange — default NSE; MCX/commodity → MCX ───────────────────
        exchange = 'MCX' if segment == 'COM' else 'NSE'

        market_type = _MARKET_TYPE_MAP.get(segment, 'indian_market')

        normalized.append({
            'symbol':      symbol,
            'trade_date':  trade_date,
            'time':        trade_time,
            'entry_time':  entry_time,
            'exit_time':   exit_time,
            'direction':   direction,
            'quantity':    str(quantity),
            'entry_price': str(entry_price.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)),
            'exit_price':  str(exit_price.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)) if exit_price is not None else '',
            'fees':        '0',
            'market_type': market_type,
            'exchange':    exchange,
            'segment':     segment,
        })

    return normalized

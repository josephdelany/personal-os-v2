"""Strict local Chase credit CSV preparation, preserving all source observations.

No database or network calls. No canonical transaction identity is inferred.
"""
import base64
import csv
import datetime as dt
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import re
import uuid

import yaml

MAPPING = Path(__file__).resolve().parents[2] / 'config/institutions/v0/chase_credit.yaml'
MAX_BYTES = 1_048_576
MAX_ROWS = 10_000


class CardFileError(ValueError):
    """Recoverable source-file error; messages contain no transaction contents."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def prepare(data: bytes, account_id: str):
    """Return a private import request with original bytes and individually addressable rows.

    The account UUID is an owner-assigned identity, not an account number inferred
    from the filename. Byte and full-row-multiset digests are account-scoped by storage.
    """
    try:
        account = str(uuid.UUID(str(account_id)))
    except (ValueError, TypeError, AttributeError):
        raise CardFileError('an account UUID is required') from None
    if not isinstance(data, bytes) or not data or len(data) > MAX_BYTES:
        raise CardFileError('CSV must contain between 1 byte and 1 MiB')
    mapping = yaml.safe_load(MAPPING.read_text())
    try:
        text = data.decode('utf-8-sig')
    except UnicodeError:
        raise CardFileError('CSV must be UTF-8') from None
    reader = csv.DictReader(io.StringIO(text, newline=''), strict=True)
    columns = mapping['columns']
    try:
        header = reader.fieldnames
    except csv.Error:
        raise CardFileError('malformed CSV header') from None
    if header is None or len(header) != len(columns) or set(header) != set(columns.values()):
        raise CardFileError('unsupported header: use a Chase US credit-card activity CSV')
    rows = []
    try:
        for record in reader:
            ordinal = len(rows) + 1
            if ordinal > MAX_ROWS:
                raise CardFileError('CSV exceeds 10000 rows')
            if None in record or any(value is None for value in record.values()):
                raise CardFileError(f'row {ordinal}: wrong column count')
            if any(len(value) > 4000 for value in record.values()):
                raise CardFileError(f'row {ordinal}: field exceeds 4000 characters')
            if any('\x00' in value for value in record.values()):
                raise CardFileError(f'row {ordinal}: NUL characters are not supported')
            def date(key, optional=False):
                value = record[columns[key]].strip()
                if not value and optional:
                    return None
                try:
                    return dt.datetime.strptime(value, mapping['date_format']).date().isoformat()
                except ValueError:
                    raise CardFileError(f'row {ordinal}: invalid {key}') from None
            amount = record[columns['amount']].strip()
            if not re.fullmatch(r'[+-]?\d+(?:\.\d{1,2})?', amount):
                raise CardFileError(f'row {ordinal}: invalid USD amount')
            number = Decimal(amount)
            if abs(number) > Decimal('1000000000000'):
                raise CardFileError(f'row {ordinal}: amount exceeds input bound')
            if mapping['amount_sign'] != 'negative_is_outflow' or mapping['currency'] != 'USD':
                raise CardFileError('unsupported mapping semantics')
            rows.append(dict(source_row=ordinal, source_record=record,
                             row_digest=digest(canonical(record).encode()),
                             occurred_on=date('occurred_on'), posted_on=date('posted_on', optional=True),
                             amount=str(number.quantize(Decimal('0.01'))),
                             currency=mapping['currency'], source_type=record[columns['source_type']],
                             source_category=record[columns['source_category']],
                             description=record[columns['description']], memo=record[columns['memo']]))
    except csv.Error:
        raise CardFileError('malformed CSV quoting') from None
    if not rows:
        raise CardFileError('CSV contains no activity rows')
    return dict(account_id=account, mapping_version=mapping['mapping_version'],
                source_sha256=digest(data), source_base64=base64.b64encode(data).decode('ascii'),
                content_digest=digest(canonical(sorted(row['row_digest'] for row in rows)).encode()),
                rows=rows)

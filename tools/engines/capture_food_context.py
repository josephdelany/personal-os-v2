"""Private, deterministic context from the transcript used by saved extraction.

Explicit `food from supplier` clauses retain the supplier verbatim. This does not
claim general brand recognition; unsupported/shared context refuses when detected.
"""
import re
from tools.engines.capture_transcription import _private

VERSION = 'capture-food-context-v1'


class ContextUnresolved(ValueError):
    pass


def explicit_supplier(transcript, *, name, evidence, evidence_start, other_starts=()):
    if (not isinstance(transcript,str) or not isinstance(name,str) or not name.strip()
        or not isinstance(evidence,str) or type(evidence_start) is not int
        or evidence_start<0 or transcript[evidence_start:evidence_start+len(evidence)]!=evidence):
        raise ContextUnresolved('unverified_food_context')
    matches=list(re.finditer(r'(?<!\w)'+re.escape(name)+r'(?!\w)',evidence,re.I))
    if len(matches)!=1:
        raise ContextUnresolved('ambiguous_food_context')
    start=evidence_start+matches[0].start()
    query=re.split(r'\s+from\s+',name,maxsplit=1,flags=re.I)[0]
    end=start+len(query)
    # Never consume the next item's evidence as a brand. Sentence boundaries are
    # conservative: punctuation inside a supplier name is unsupported, not guessed.
    next_item=min((v for v in other_starts if v>=end),default=len(transcript))
    sentence_end=re.search(r'[.!?;\n]',transcript[end:])
    stop=min(next_item,end+sentence_end.start() if sentence_end else len(transcript))
    tail=transcript[end:stop]
    match=re.match(r'\s+from\s+(.+?)\s*$',tail,re.I)
    if match is None:
        if re.search(r'\bfrom\b',tail,re.I):
            raise ContextUnresolved('ambiguous_supplier_context')
        left=max((m.end() for m in re.finditer(r'[.!?;\n]',transcript[:start])),default=0)
        right=end+sentence_end.start() if sentence_end else len(transcript)
        if re.search(r'\bfrom\b',transcript[left:right],re.I):
            raise ContextUnresolved('shared_supplier_context')
        return {'query':query,'brand':None,'brand_evidence':None,'brand_evidence_start':None,'context_version':VERSION}
    if sentence_end and stop<next_item and transcript[stop+1:].strip():
        raise ContextUnresolved('ambiguous_supplier_context')
    supplier=match[1].strip()
    # An inter-item conjunction belongs to neither supplier; it is removable
    # only when the next item's verified start supplied the boundary.
    if stop==next_item and next_item<len(transcript):
        supplier=re.sub(r'\s+(?:and|then)\s*$','',supplier,flags=re.I).rstrip(' ,')
    if (not supplier or len(supplier)>512 or not re.fullmatch(r"[\w &'’\-]+",supplier)
        or re.search(r'\b(?:from|not|but|at|yesterday|today|tomorrow)\b',supplier,re.I)):
        raise ContextUnresolved('ambiguous_supplier_context')
    offset=end+match.start(1)
    assert transcript[offset:offset+len(supplier)]==supplier
    return {'query':query,'brand':supplier,'brand_evidence':supplier,'brand_evidence_start':offset,'context_version':VERSION}


def load(cur, *, extraction_request_id, item_index, schema='core'):
    schema=_private(schema)
    cur.execute(f'''SELECT payload FROM {schema}.capture_extraction_attempts WHERE request_id=%s''',
                (extraction_request_id,))
    saved=cur.fetchone()
    if saved is None:
        raise ContextUnresolved('missing_extraction_context')
    transcript=saved[0]['messages'][1]['content']
    cur.execute(f'''SELECT item_index,value,provenance,evidence,evidence_start
        FROM {schema}.capture_extraction_fields WHERE request_id=%s AND name='name' ORDER BY item_index''',
        (extraction_request_id,))
    items=cur.fetchall()
    item=next((row for row in items if row[0]==item_index),None)
    if item is None or item[2]!='extracted':
        raise ContextUnresolved('unverified_food_context')
    # Quantity spans start before the next food name and prevent exporting them.
    cur.execute(f'''SELECT evidence_start FROM {schema}.capture_extraction_fields
        WHERE request_id=%s AND item_index<>%s AND item_index>=0
          AND provenance='extracted' AND evidence_start IS NOT NULL''',
        (extraction_request_id,item_index))
    others=[row[0] for row in cur.fetchall()]
    return explicit_supplier(transcript,name=item[1],evidence=item[3],evidence_start=item[4],other_starts=others)

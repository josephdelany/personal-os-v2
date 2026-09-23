"""Private, deterministic context from the transcript used by saved extraction.

Explicit `food from supplier` clauses and possessive qualifiers outside the food
name in verified evidence retain the supplier verbatim. This does not claim general
brand recognition; unsupported/shared context refuses when detected.
"""
import re
from tools.engines.capture_transcription import _private

VERSION = 'capture-food-context-v3'


class ContextUnresolved(ValueError):
    pass


def _possessive_prefix(transcript,evidence,evidence_start,name_offset,other_starts):
    prefix=evidence[:name_offset]
    if not re.search(r"['’]s\b",prefix,re.I):
        if re.search(r"['’]s\s+$",transcript[:evidence_start+name_offset],re.I):
            raise ContextUnresolved('unverified_supplier_context')
        before=transcript[:evidence_start+name_offset]
        left=max((m.end() for m in re.finditer(r'[.!?;\n]',before)),default=0)
        if re.search(r"['’]s\b",before[left:],re.I):
            raise ContextUnresolved('shared_supplier_context')
        return None
    match=re.fullmatch(r"\s*(?P<brand>[\w][\w &'’\-]*['’]s)\s+",prefix,re.I)
    if match is None:raise ContextUnresolved('ambiguous_supplier_context')
    supplier=match['brand']
    if (len(supplier)>512 or re.search(
        r'\b(?:not|but|from|at|my|your|his|her|their|our|i|we|you|ate|had|bought|ordered|a|an|the|one|two)\b',
        supplier,re.I) or any(evidence_start<=v<evidence_start+name_offset for v in other_starts)):
        raise ContextUnresolved('ambiguous_supplier_context')
    offset=evidence_start+match.start('brand')
    left=max((m.end() for m in re.finditer(r'[.!?;\n]',transcript[:offset])),default=0)
    if re.search(r'\b(?:not|without|rather|instead|my|your|his|her|their|our)\b',transcript[left:offset],re.I):
        raise ContextUnresolved('ambiguous_supplier_context')
    return supplier,offset


def _known_prefix(transcript, name, evidence, evidence_start, name_offset, tokens, foods, other_starts):
    """Recognize only a unique leading supplier established by private source data."""
    candidates=[]
    for token in sorted({t for t in tokens if isinstance(t,str) and t.strip()}):
        match=re.match(r'\s*('+re.escape(token)+r')(?=\s+)',evidence,re.I)
        if match:
            candidates.append(match)
    spans={(m.start(1),m.end(1)) for m in candidates}
    if len(spans)>1:
        raise ContextUnresolved('ambiguous_supplier_context')
    if not spans:
        before=transcript[:evidence_start+name_offset]
        left=max((m.end() for m in re.finditer(r'[.!?;\n]',before)),default=0)
        if any(re.search(r'(?<!\w)'+re.escape(t)+r'(?!\w)',before[left:],re.I)
               for t in tokens if isinstance(t,str) and t.strip()):
            raise ContextUnresolved('shared_supplier_context')
        return None
    begin,end=next(iter(spans))
    supplier=evidence[begin:end]
    food_keys={f.casefold().strip() for f in foods if isinstance(f,str)}
    if supplier.casefold() in food_keys or evidence.strip().casefold() in food_keys:
        raise ContextUnresolved('supplier_food_name_collision')
    if any(evidence_start+begin<=v<evidence_start+end for v in other_starts):
        raise ContextUnresolved('shared_supplier_context')
    if name_offset>=end:
        if evidence[end:name_offset].strip() or end>name_offset:
            raise ContextUnresolved('ambiguous_supplier_context')
        query=name
        query_offset=name_offset
    elif name_offset==begin:
        # A whole-name extraction may include the supplier. Only remove the
        # proven leading token; retain the remaining verbatim food phrase.
        if not name.lower().startswith(supplier.lower()):
            raise ContextUnresolved('ambiguous_supplier_context')
        query=name[len(supplier):].lstrip()
        query_offset=name_offset+len(name)-len(query)
        if not query:
            raise ContextUnresolved('ambiguous_food_context')
    else:
        raise ContextUnresolved('ambiguous_supplier_context')
    offset=evidence_start+begin
    left=max((m.end() for m in re.finditer(r'[.!?;\n]',transcript[:offset])),default=0)
    if re.search(r'\b(?:not|without|rather|instead|my|your|his|her|their|our)\b',transcript[left:offset],re.I):
        raise ContextUnresolved('ambiguous_supplier_context')
    return supplier,offset,query,evidence_start+query_offset


def _verified_name(transcript,name,evidence,evidence_start):
    if (not isinstance(transcript,str) or not isinstance(name,str) or not name.strip()
        or not isinstance(evidence,str) or type(evidence_start) is not int
        or evidence_start<0 or transcript[evidence_start:evidence_start+len(evidence)]!=evidence):
        raise ContextUnresolved('unverified_food_context')
    matches=list(re.finditer(r'(?<!\w)'+re.escape(name)+r'(?!\w)',evidence,re.I))
    if len(matches)!=1:
        raise ContextUnresolved('ambiguous_food_context')
    return matches


def explicit_supplier(transcript, *, name, evidence, evidence_start, other_starts=(),
                      known_suppliers=(),known_foods=(),quantity_spans=()):
    matches=_verified_name(transcript,name,evidence,evidence_start)
    # Evidence may include the explicit article in the spec's "a Big Mac"
    # example, or the separately verified quantity. Neither is a supplier.
    name_offset=matches[0].start()
    drop=0
    article=re.match(r'\s*(?:a|an|the)\s+',evidence,re.I)
    if (article and article.end()<=name_offset and not any(
        re.match(r'\s*'+re.escape(t)+r'(?=\s+)',evidence,re.I)
        for t in known_suppliers if isinstance(t,str) and t.strip())):
        drop=article.end()
    for offset,span in quantity_spans:
        if (type(offset) is int and isinstance(span,str) and span
            and offset==evidence_start+drop and offset+len(span)<=evidence_start+name_offset
            and transcript[offset:offset+len(span)]==span):
            drop+=len(span)
            break
    if drop:
        evidence=evidence[drop:]
        evidence_start+=drop
        matches=list(re.finditer(r'(?<!\w)'+re.escape(name)+r'(?!\w)',evidence,re.I))
    start=evidence_start+matches[0].start()
    known=_known_prefix(transcript,name,evidence,evidence_start,matches[0].start(),known_suppliers,
                        known_foods,other_starts)
    if known:
        supplier,offset,name,start=known
        possessive=(supplier,offset)
    else:
        possessive=_possessive_prefix(transcript,evidence,evidence_start,matches[0].start(),other_starts)
        if possessive is None and evidence[:matches[0].start()].strip():
            raise ContextUnresolved('unrecognized_supplier_context')
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
        if possessive is not None:
            supplier,offset=possessive
            return {'query':query,'brand':supplier,'brand_evidence':supplier,
                    'brand_evidence_start':offset,'context_version':VERSION}
        return {'query':query,'brand':None,'brand_evidence':None,'brand_evidence_start':None,'context_version':VERSION}
    if possessive is not None:
        raise ContextUnresolved('conflicting_supplier_context')
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
    name_match=_verified_name(transcript,item[1],item[3],item[4])[0]
    # Quantity spans start before the next food name and prevent exporting them.
    cur.execute(f'''SELECT evidence_start FROM {schema}.capture_extraction_fields
        WHERE request_id=%s AND item_index<>%s AND item_index>=0
          AND provenance='extracted' AND evidence_start IS NOT NULL''',
        (extraction_request_id,item_index))
    others=[row[0] for row in cur.fetchall()]
    # Only supplier fields establish this vocabulary. A category or a generic
    # cache name is not a brand. Filter in SQL so unrelated cache rows stay there.
    cur.execute(f'''SELECT DISTINCT token FROM {schema}.foods_cache c
        CROSS JOIN LATERAL (
            SELECT c.brand AS token WHERE c.source='joe'
            UNION ALL
            SELECT c.raw->'usda_food'->>'brandOwner'
              WHERE c.source='usda_branded'
                AND jsonb_typeof(c.raw->'usda_food'->'brandOwner')='string'
            UNION ALL
            SELECT c.raw->'usda_food'->>'brandName'
              WHERE c.source='usda_branded'
                AND jsonb_typeof(c.raw->'usda_food'->'brandName')='string'
            UNION ALL
            SELECT trim(value) FROM regexp_split_to_table(
                CASE WHEN c.source='off_product'
                    AND jsonb_typeof(c.raw->'off_product'->'brands')='string'
                    THEN c.raw->'off_product'->>'brands' ELSE '' END, ',') value
        ) tokens
        WHERE token IS NOT NULL AND length(trim(token)) BETWEEN 1 AND 512
          AND strpos(lower(%s),lower(trim(token)))>0''',(transcript,))
    suppliers=[row[0].strip() for row in cur.fetchall()]
    cur.execute(f'''SELECT canonical_name FROM {schema}.foods_cache
        WHERE source='usda_foundation' AND strpos(lower(%s),lower(canonical_name))>0''',(transcript,))
    foods=[row[0] for row in cur.fetchall()]
    cur.execute(f'''SELECT evidence_start,evidence FROM {schema}.capture_extraction_fields
        WHERE request_id=%s AND item_index=%s AND name='quantity' AND provenance='extracted'
          AND evidence_start IS NOT NULL AND evidence IS NOT NULL''',(extraction_request_id,item_index))
    quantities=cur.fetchall()
    context_error=None
    try:
        context=explicit_supplier(transcript,name=item[1],evidence=item[3],evidence_start=item[4],
                                   other_starts=others,known_suppliers=suppliers,known_foods=foods,
                                   quantity_spans=quantities)
    except ContextUnresolved as error:
        if str(error) not in ('unrecognized_supplier_context','supplier_food_name_collision'):
            raise
        context_error=error
        context={'query':item[3],'brand':None,'brand_evidence':None,'brand_evidence_start':None,
                 'context_version':VERSION}
    # Corrections retain the complete supplier scope, including an explicit
    # "from supplier" suffix outside the model-selected evidence. A narrower
    # generic name correction cannot override a named item. Known collisions or
    # unexplained qualifiers inside the full phrase may be settled by Joe.
    candidates=[(item[3],item[4])]
    if context_error is None:
        candidates.append((item[1],item[4]+name_match.start()))
    if context['brand']:
        begin=context['brand_evidence_start'];end=begin+len(context['brand_evidence'])
        left=min(item[4],begin);right=max(item[4]+len(item[3]),end)
        candidates.insert(0,(transcript[left:right],left))
        candidates=[(phrase,start) for phrase,start in candidates if start<=begin and start+len(phrase)>=end]
    from tools.engines import nutrition
    for phrase in dict.fromkeys(phrase for phrase,_ in candidates):
        try:
            owned,_=nutrition.lookup_cached(cur,phrase,schema,owner_only=True)
        except nutrition.Unresolved:
            raise ContextUnresolved('ambiguous_owner_correction') from None
        if owned is not None:
            return {**context,'query':phrase,'owner_correction':True}
    if context_error is not None:
        raise context_error
    return context

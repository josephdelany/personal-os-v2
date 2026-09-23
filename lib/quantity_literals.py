"""Deterministic proof of stated numbers; no approximate portion mappings."""
import math
import re
from decimal import Decimal
from fractions import Fraction

SMALL = dict(zip(('zero one two three four five six seven eight nine ten eleven '
                  'twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen').split(), range(20)))
TENS = dict(zip('twenty thirty forty fifty sixty seventy eighty ninety'.split(), range(20,100,10)))
COUNT_UNITS = frozenset(('each','item','items','serving','servings','piece','pieces'))
VAGUE_QUANTIFIERS = ('most of','a few bites','some of','a bit of','half-ish','a couple of',
                     'part of','picked at')
EXPLICIT_FRACTIONS = {'half':0.5,'a half':0.5,'quarter':0.25,'a quarter':0.25,
                      'third':1/3,'a third':1/3,'three quarters':0.75}


def _under100(words):
    if len(words)==1:
        return SMALL.get(words[0], TENS.get(words[0]))
    if len(words)==2 and words[0] in TENS and words[1] in SMALL and 0<SMALL[words[1]]<10:
        return TENS[words[0]]+SMALL[words[1]]
    return None


def _under1000(words):
    if len(words)>=2 and words[1]=='hundred' and words[0] in SMALL and 0<SMALL[words[0]]<10:
        base=SMALL[words[0]]*100
        tail=words[2:]
        if not tail:
            return base
        if tail[0]=='and':
            tail=tail[1:]
        rest=_under100(tail)
        return base+rest if rest is not None and rest>0 else None
    return _under100(words)


def _cardinal(words):
    words=list(words)
    if words and words[0] in ('a','an'):
        words[0]='one'
    total=0
    for scale,size in (('million',1000000),('thousand',1000)):
        if scale not in words:
            continue
        if words.count(scale)!=1:
            return None
        at=words.index(scale)
        head=_under1000(words[:at])
        if head is None or head<=0:
            return None
        total+=head*size
        words=words[at+1:]
        if not words:
            return total
        if words[0]=='and':
            words=words[1:]
            if not words:
                return None
    tail=_under1000(words)
    return total+tail if tail is not None and (not total or tail>0) else None


def parse_number(text):
    """Return the exact rational stated by a whole phrase, or None."""
    if not isinstance(text,str):
        return None
    text=text.strip().lower()
    if re.fullmatch(r'\d+(?:\.\d+)?',text):
        return Fraction(Decimal(text))
    if not re.fullmatch(r'[a-z]+(?:(?:\s+|-)[a-z]+)*',text):
        return None
    words=text.replace('-',' ').split()
    if 'point' in words:
        if words.count('point')!=1:
            return None
        at=words.index('point'); whole=_cardinal(words[:at]); tail=words[at+1:]
        if whole is None or not tail or any(w not in SMALL or SMALL[w]>9 for w in tail):
            return None
        return Fraction(Decimal(str(whole)+'.'+''.join(str(SMALL[w]) for w in tail)))
    denominators={'half':2,'halves':2,'quarter':4,'quarters':4,'third':3,'thirds':3}
    if words[-1] in denominators:
        denominator=denominators[words[-1]]
        prefix=words[:-1]; whole=0
        if 'and' in prefix:
            at=len(prefix)-1-prefix[::-1].index('and')
            whole=_cardinal(prefix[:at]); prefix=prefix[at+1:]
            if whole is None:
                return None
        numerator=_cardinal(prefix) if prefix else 1
        if numerator is None or numerator<=0:
            return None
        if (numerator==1) != (words[-1] in ('half','quarter','third')):
            return None
        return Fraction(whole)+Fraction(numerator,denominator)
    value=_cardinal(words)
    return Fraction(value) if value is not None else None


def matches_number(value, text):
    if isinstance(value,bool) or not isinstance(value,(int,float,Decimal)):
        return False
    try:
        if not math.isfinite(value) or value<0:
            return False
    except (ValueError,OverflowError):
        return False
    parsed=parse_number(text)
    if parsed is None:
        return False
    if Fraction(Decimal(str(value)))==parsed:
        return True
    # A recurring explicit fraction has no exact finite float representation.
    # Accept only its deterministic float, never a fitted tolerance or rounding.
    denominator=parsed.denominator
    for prime in (2,5):
        while denominator%prime==0:
            denominator//=prime
    return denominator!=1 and float(parsed)==value


def number_phrase(text):
    """Remove grammatical links used between a fraction and its unit/name."""
    text=text.strip()
    return re.sub(r'\s+(?:of\s+(?:a|an|one)|a|an)$','',text,flags=re.I) if re.search(
        r'\b(?:half|halves|quarter|quarters|third|thirds)\b',text,re.I) else text


def quantity_label(value,evidence,labels=()):
    """Return the verified suffix (empty for a bare number), or None."""
    if not isinstance(evidence,str):
        return None
    if matches_number(value,evidence):
        return ''
    for label in sorted(set(labels),key=len,reverse=True):
        if not label:
            continue
        match=re.fullmatch(r'(.+?)(\s*)'+re.escape(label)+r'\s*',evidence,re.I)
        if (match and (match[2] or match[1][-1].isdigit())
                and matches_number(value,number_phrase(match[1]))):
            return label
    return None


def vague_phrase(evidence):
    return isinstance(evidence,str) and any(re.search(r'(?<!\w)'+re.escape(q)+r'(?!\w)',evidence,re.I)
                                           for q in VAGUE_QUANTIFIERS)

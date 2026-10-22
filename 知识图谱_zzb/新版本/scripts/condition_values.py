"""Parse only literal, bounded scalar/range values; never turn material names into units."""
import re
N=r'[+\-−]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-−]?\d+|\s*[×xX·*]\s*10\s*\^?\s*[+\-−]?\d+)?'
NUM=re.compile(r'(?<![\w.\-−+])'+N+r'(?![\w.])')
RANGE=re.compile(r'(?P<left>'+N+r')\s*(?:~|–|—|至|到|to|-)\s*(?P<right>'+N+r')',re.I)
SCALAR_RAW=re.compile(r'^\s*(?P<n>'+N+r')\s*(?P<unit>[^\d]*?)\s*$')
# Units must be dimensional tokens, not arbitrary words such as PEG, NBT or sample names.
UNITS={'%','ppm','ppb','M','mM','μM','µM','uM','nM','mol/L','mol L^-1','mol L−1','g/L','mg/L','μg/L','µg/L',
       'g L^-1','mg L^-1','g L−1','mg L−1','K','°C','℃','V','mV','eV','kJ/mol','KJ/mol','J/mol',
       's','ms','min','h','hr','hours','Hz','kHz','MHz','rpm','r/min','r min^-1','mm','cm','m','nm','μm','µm','um','mV/s','mV/sec','V/s',
       'A','mA','μA','µA','A/cm2','mA/cm2','mA cm^-2','mA cm−2','A dm^-2','A/dm2','ASD','Ω','mΩ',
       'mC','C','mC/cm2','mC cm^-2','mL','L','mL/min','mmol/L','g','mg'}
def valid_unit(unit):return isinstance(unit,str) and unit.strip() in UNITS
def _unit(hint,tail,text):
    tail=(tail or '').strip()
    for candidate in sorted(UNITS,key=len,reverse=True):
        if tail.startswith(candidate):
            rest=tail[len(candidate):]
            compound_continues=re.match(r'[/^_²³−-]|\\s+(?:cm|dm|m|s|sec|min|L|mol)\\s*(?:[0-9^−-]|$)',rest)
            if not re.match(r'[A-Za-z0-9μµ/^_²³−-]',rest) and not compound_continues:return candidate
    if valid_unit(hint) and re.search(r'(?<![A-Za-zμµ])'+re.escape(hint.strip())+r'(?![A-Za-z0-9μµ])',text):return hint.strip()
    return None
def _numbers(text):
    # Match the complete signed tokens, including numbers immediately followed by a unit.
    return list(re.finditer(r'(?<![\w.^\-−+])'+N+r'(?![\d.])',text))
def _q(raw,kind,unit):
    return {'value_raw':raw,'value_kind':kind,'unit_raw':unit,'unit_status':'reported' if unit else 'unresolved'}
def parse_range(text,unit_hint=None):
    if not isinstance(text,str):return None
    ranges=list(RANGE.finditer(text))
    if len(ranges)!=1:return None
    match=ranges[0]
    if _numbers(text[:match.start()]+' '+text[match.end():]):return None
    # A single 10^-3 scalar must never be mistaken for the range 10 to -3.
    if '^' in text[:match.start()+1] or re.search(r'10\s*\^',match.group(0)):return None
    unit=_unit(unit_hint,text[match.end():].strip().rstrip('.,;'),text)
    return _q(match.group(0),'range',unit)
def parse_numeric(text,unit_hint=None):
    if not isinstance(text,str) or parse_range(text,unit_hint):return None
    found=_numbers(text)
    if len(found)!=1:return None
    match=found[0];tail=text[match.end():].strip().rstrip('.,;')
    unit=_unit(unit_hint,tail,text)
    return _q(match.group(0),'numeric',unit)
def classify_condition(raw_value,quote,unit_hint=None):
    raw_value='' if raw_value is None else str(raw_value)
    quote=quote or ''
    fallback=_q(raw_value,'qualitative',_unit(unit_hint,None,quote))
    # Do not collapse inequalities, uncertainty, a list, or prose into an unconstrained scalar.
    if re.search(r'[<>≤≥±,;]|at least|at most|more than|less than|above|below',raw_value,re.I):return fallback
    ranged_raw=RANGE.fullmatch(raw_value.strip())
    if not ranged_raw:
        rr=RANGE.match(raw_value.strip())
        ranged_raw=rr if rr and valid_unit(raw_value.strip()[rr.end():].strip()) else None
    if ranged_raw:
        ranged=parse_range(quote,unit_hint)
        if ranged and RANGE.fullmatch(ranged['value_raw']).groupdict()==ranged_raw.groupdict():
            return ranged
        return fallback
    rawmatch=SCALAR_RAW.fullmatch(raw_value)
    if not rawmatch or (rawmatch.group('unit').strip() and not valid_unit(rawmatch.group('unit'))):return fallback
    numeric=parse_numeric(quote,unit_hint)
    if numeric and numeric['value_raw']==rawmatch.group('n'):
        if not numeric['unit_raw'] and re.search(r'potential|voltage|电势|电位',quote,re.I):return fallback
        return numeric
    return fallback
def numeric_bounds(quantity):
    """Return source-literal scalar/range bounds for filters, without changing stored text."""
    raw=(quantity.get('value_raw') or '').strip().replace('−','-')
    if quantity.get('value_kind')=='numeric' and re.fullmatch(r'[+\-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?',raw):
        val=float(raw);return (val,val)
    if quantity.get('value_kind')=='range':
        match=RANGE.fullmatch(raw)
        if match:
            try:return (float(match.group('left')),float(match.group('right')))
            except ValueError:return None
    return None

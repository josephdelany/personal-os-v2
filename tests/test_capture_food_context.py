"""Verbatim supplier context; no source calls or personal rows."""
import pytest
from tools.engines.capture_food_context import explicit_supplier,ContextUnresolved


def parse(text,name='bar',**kw):
    return explicit_supplier(text,name=name,evidence=name,evidence_start=text.index(name),**kw)


@pytest.mark.parametrize('supplier',["Examplo Foods","McDonald's",'Salt and Straw','Store & Co'])
def test_REQ_NUT_013_supplier_is_verbatim_and_offset_bound(supplier):
    text='one bar from '+supplier
    result=parse(text)
    assert result['query']=='bar' and result['brand']==supplier
    start=result['brand_evidence_start']
    assert text[start:start+len(result['brand_evidence'])]==supplier


def test_REQ_NUT_013_explicit_supplier_inside_name_does_not_become_food_query():
    result=parse('one bar from Examplo',name='bar from Examplo')
    assert result['query']=='bar' and result['brand']=='Examplo'


def test_REQ_NUT_016_separate_items_do_not_export_next_quantity_as_brand():
    text='one bar from Examplo and two shakes from Other'
    result=parse(text,other_starts=[text.index('two'),text.index('shakes')])
    assert result['brand']=='Examplo'


@pytest.mark.parametrize('text',[
    'one bar not from Examplo','one bar from Examplo at noon',
    'one bar from St. Louis','one bar from Examplo but not Other',
])
def test_REQ_NUT_016_ambiguous_supplier_is_not_discarded_to_allow_generic_food(text):
    with pytest.raises(ContextUnresolved):parse(text)


def test_REQ_NUT_016_shared_supplier_does_not_silently_make_first_item_generic():
    text='one bar and two shakes from Examplo'
    with pytest.raises(ContextUnresolved,match='shared_supplier_context'):
        parse(text,other_starts=[text.index('two'),text.index('shakes')])


def test_REQ_CAP_053_context_rejects_a_fabricated_evidence_span():
    with pytest.raises(ContextUnresolved,match='unverified_food_context'):
        explicit_supplier('one bar from Examplo',name='bar',evidence='bar',evidence_start=0)


@pytest.mark.parametrize('supplier',["Examplo's",'Examplo’s',"Trader Joe's"])
def test_REQ_NUT_013_possessive_qualifier_in_verified_evidence_is_preserved(supplier):
    evidence=supplier+' burger';text='one '+evidence
    result=explicit_supplier(text,name='burger',evidence=evidence,evidence_start=4)
    assert result['query']=='burger' and result['brand']==supplier
    assert result['brand_evidence']==supplier and result['brand_evidence_start']==4
    assert text[result['brand_evidence_start']:result['brand_evidence_start']+len(supplier)]==supplier


@pytest.mark.parametrize('text,evidence',[
    ("one Examplo's burger","burger"),
    ("not Examplo's burger","not Examplo's burger"),
    ("my friend's burger","my friend's burger"),
    ("my friend's burger","friend's burger"),
    ("Examplo's burger from Other","Examplo's burger"),
])
def test_REQ_NUT_016_possessive_context_cannot_silently_become_generic(text,evidence):
    with pytest.raises(ContextUnresolved):
        explicit_supplier(text,name='burger',evidence=evidence,evidence_start=text.index(evidence))


def test_REQ_NUT_013_possessive_part_of_food_name_is_not_reclassified_as_supplier():
    result=parse("one shepherd's pie",name="shepherd's pie")
    assert result['query']=="shepherd's pie" and result['brand'] is None


def test_REQ_NUT_016_shared_possessive_does_not_make_later_item_generic():
    text="Examplo's burger and fries"
    with pytest.raises(ContextUnresolved,match='shared_supplier_context'):
        explicit_supplier(text,name='fries',evidence='fries',evidence_start=text.index('fries'))

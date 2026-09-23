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


@pytest.mark.parametrize('name',['burger','Examplo burger'])
def test_REQ_NUT_013_known_supplier_prefix_keeps_verbatim_context(name):
    result=explicit_supplier('one Examplo burger',name=name,evidence='Examplo burger',
                             evidence_start=4,known_suppliers=('Examplo',))
    assert result['query']=='burger' and result['brand']=='Examplo'
    assert result['brand_evidence_start']==4 and result['brand_evidence']=='Examplo'


def test_REQ_NUT_016_unknown_qualifier_cannot_be_dropped_for_generic_lookup():
    with pytest.raises(ContextUnresolved,match='unrecognized_supplier_context'):
        explicit_supplier('one Examplo burger',name='burger',evidence='Examplo burger',evidence_start=4)


@pytest.mark.parametrize('text,name,evidence,tokens',[
    ('Examplo Foods burger','burger','Examplo Foods burger',('Examplo','Examplo Foods')),
    ('my Examplo burger','burger','Examplo burger',('Examplo',)),
    ('not Examplo burger','burger','Examplo burger',('Examplo',)),
    ('Examplo burger','burger','burger',('Examplo',)),
    ('Examplo burger and fries','fries','fries',('Examplo',)),
])
def test_REQ_NUT_016_known_supplier_ambiguity_and_narrowed_evidence_refuse(text,name,evidence,tokens):
    with pytest.raises(ContextUnresolved):
        explicit_supplier(text,name=name,evidence=evidence,evidence_start=text.index(evidence),
                          known_suppliers=tokens)


def test_REQ_CAP_053_acceptance_article_and_verified_quantity_are_not_suppliers():
    result=explicit_supplier('I ate a Big Mac',name='Big Mac',evidence='a Big Mac',evidence_start=6)
    assert result['query']=='Big Mac' and result['brand'] is None
    result=explicit_supplier('one burger',name='burger',evidence='one burger',evidence_start=0,
                             quantity_spans=((0,'one'),))
    assert result['query']=='burger' and result['brand'] is None
    result=explicit_supplier('two Examplo burgers',name='burgers',evidence='two Examplo burgers',
                             evidence_start=0,quantity_spans=((0,'two'),),known_suppliers=('Examplo',))
    assert result['brand']=='Examplo' and result['brand_evidence_start']==4


@pytest.mark.parametrize('foods',[('apple',),('apple pie',)])
def test_REQ_NUT_016_catalogued_food_and_brand_collision_requires_review(foods):
    with pytest.raises(ContextUnresolved,match='supplier_food_name_collision'):
        explicit_supplier('apple pie',name='apple pie',evidence='apple pie',evidence_start=0,
                          known_suppliers=('Apple',),known_foods=foods)

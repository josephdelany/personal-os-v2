"""Verified food quantities reach the deterministic resolver without unit guesses."""
import pytest
from tools.engines.capture_resolution import _quantity
from tools.engines.nutrition import Unresolved


def fields(value,unit,evidence,*,unit_provenance='extracted'):
    return {(0,'quantity'):{'value':value,'provenance':'extracted','evidence':evidence,'reason':None},
            (0,'quantity_unit'):{'value':unit,'provenance':unit_provenance,'evidence':evidence,'reason':None}}


@pytest.mark.parametrize('value,unit,evidence,grams',[
    (150,'grams','150 grams',150),(0.15,'kg','0.15 kg',150),
    (500,'mg','500 mg',0.5),(2,'oz','2 oz',56.69904625),
    (1,'lb','1 lb',453.59237),
])
def test_REQ_CAP_053_REQ_NUT_032_verified_mass_reaches_resolver_as_grams(value,unit,evidence,grams):
    assert _quantity(fields(value,unit,evidence),0,'fixture food')=={'grams':pytest.approx(grams)}


@pytest.mark.parametrize('value,unit,evidence,provenance',[
    (150,'grams','150 grams','inferred'),
    (150,'g','150 ml and 200 g','extracted'),
    (12,'oz','12 fluid oz','extracted'),
    (150,None,'150 grams','inferred'),
    (150,None,'150 kilograms','inferred'),
    (150,None,'150 milligrams','inferred'),
    (150,None,'150 teaspoons','inferred'),
    (2,None,'2 servings','inferred'),
    (2,'items','2 servings','extracted'),
    (150,'ml','150 ml','extracted'),
    (0,'g','0 g','extracted'),
    (-1,'g','-1 g','extracted'),
    (float('nan'),'g','1 g','extracted'),
    (float('inf'),'g','1 g','extracted'),
    (True,'g','1 g','extracted'),
    (150,'g','150 g or 200 g','extracted'),
])
def test_REQ_CAP_054_REQ_NUT_032_uncertain_or_conflicting_dimensions_never_become_mass(value,unit,evidence,provenance):
    with pytest.raises(Unresolved):
        _quantity(fields(value,unit,evidence,unit_provenance=provenance),0,'fixture food')


@pytest.mark.parametrize('value,unit,text,expected',[
    (2,None,'two',{'item_count':2}),
    (2,'items','2 items',{'item_count':2}),
    (2,'servings','2 servings',{'servings':2}),
])
def test_REQ_NUT_050_count_and_serving_dimensions_remain_distinct(value,unit,text,expected):
    assert _quantity(fields(value,unit,text),0,'fixture food')==expected


@pytest.mark.parametrize('value,unit,target,expected',[
    (150,'grams','g',150), (0.15,'kilograms','g',150),
    (2,'ounces','g',56.69904625), (1,'pounds','g',453.59237),
    (0.25,'liters','ml',250), (12,'milliliters','ml',12),
])
def test_REQ_NUT_019_pint_conversion_retains_physical_dimension(value,unit,target,expected):
    from lib.mass_units import convert_quantity
    result=convert_quantity(value,unit)
    assert result['unit']==target
    assert result['value']==pytest.approx(expected)
    assert result['provenance']=='extracted'


@pytest.mark.parametrize('value,unit',[(1,'g/ml'),(1,'g ** 2'),(1,'cup'),
    (float('inf'),'g'),(-1,'kg'),(True,'g'),(1,'unknown'),(1,'Mg'),(1,'ML'),
    (10**400,'g'),(1e308,'kg')])
def test_REQ_NUT_019_unapproved_or_invalid_unit_expressions_refuse(value,unit):
    from lib.mass_units import convert_quantity
    with pytest.raises(ValueError):
        convert_quantity(value,unit)


@pytest.mark.parametrize('unit,text', [('g','150g'),('grams','150 grams')])
def test_REQ_CAP_053_REQ_NUT_019_compact_literal_mass_pair(unit,text):
    assert _quantity(fields(150,unit,text),0,'fixture food')=={'grams':pytest.approx(150)}


def test_REQ_NUT_019_verified_volume_requires_density_for_food_mass():
    with pytest.raises(Unresolved) as error:
        _quantity(fields(0.25,'liters','0.25liters'),0,'fixture food')
    assert error.value.reason=='volume_density_unavailable'


@pytest.mark.parametrize('offset,expected',[(0,'extracted'),(1,'inferred')])
def test_REQ_CAP_053_054_compact_pair_still_requires_exact_transcript_span(offset,expected):
    from tools.engines.capture_extraction import validated_fields
    text='150g fixture food'
    response={'success':True,'result':{'response':{'items':[{
        'name':'fixture food','evidence':'fixture food','evidence_start':5,
        'quantity':150,'quantity_unit':'g','quantity_evidence':'150g',
        'quantity_evidence_start':offset}],
        'temporal_evidence':None,'temporal_evidence_start':None}}}
    saved=validated_fields(response,text)
    for field in saved:
        if field['name'] in ('quantity','quantity_unit'):
            assert field['provenance']==expected
            if expected=='inferred':
                assert field['value'] is None
                assert field['reason']=='span_mismatch'


def test_REQ_NUT_019_source_serving_symbols_do_not_fold_mega_into_milli():
    from tools.engines import nutrition_off, nutrition_usda
    assert nutrition_off.serving_mass({'serving_quantity':1,'serving_quantity_unit':'Mg'})[0] is None
    assert nutrition_usda._serving_mass({'servingSize':1,'servingSizeUnit':'Mg'})[0] is None

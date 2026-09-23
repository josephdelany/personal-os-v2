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

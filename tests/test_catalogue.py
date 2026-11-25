from pathlib import Path

import pytest

from weekly_picker.catalogue import load_csv, normalise_equipment

ROOT = Path(__file__).resolve().parent.parent
real_catalogue = pytest.mark.skipif(not (ROOT / "alo-scoring").exists(), reason="the real catalogue is private")


def test_normalise_equipment_merges_synonyms():
    assert normalise_equipment("Block; bands; Pilates Ball") == {"blocks", "resistance bands", "pilates ball"}
    assert normalise_equipment("weights; resistance band; ball") == {"weights", "resistance bands", "pilates ball"}


def test_optional_items_ignored_and_none_is_empty():
    assert normalise_equipment("blanket (optional); strap") == {"yoga strap"}
    assert normalise_equipment("none") == frozenset()
    assert normalise_equipment("") == frozenset()


def test_unknown_items_kept_as_is_lowercased():
    assert normalise_equipment("Sliders") == {"sliders"}


def test_load_csv_handles_messy_rows(tmp_path):
    p = tmp_path / "c.csv"
    p.write_text(
        "id,title,mins,difficulty,intensity,style,categories,equipment,focus,series,description,url\n"
        "1,A,20,beginner,None,yoga_hatha,Yoga; Single Classes,,,False,,https://x/1\n"
    )
    [c] = load_csv(p)
    assert c.intensity is None and c.focus is None and c.description == "" and c.equipment == frozenset()
    assert c.categories == ("Yoga", "Single Classes") and c.instructor is None


@real_catalogue
def test_load_real_catalogue_count():
    assert len(load_csv(ROOT / "alo-scoring" / "alo_classes.csv")) == 4746


@pytest.mark.parametrize("raw, expected", [
    ("Core", "core"), ("core", "core"), ("Arms", "arms"), ("Legs; booty", "legs"), ("booty; Legs", "booty"),
    ("Arms; Core", "arms"), ("lower body", "legs"), ("upper body", "arms"), ("total body", "full body"),
    ("glutes", "booty"), ("hamstrings", "legs"), ("shoulders", "arms"), ("", None), ("something odd", None),
])
def test_focus_is_normalised_to_the_five_areas(tmp_path, raw, expected):
    p = tmp_path / "c.csv"
    p.write_text("id,title,mins,difficulty,intensity,style,categories,equipment,focus,series,description,url\n"
                 f'1,A,20,beginner,2,yoga_hatha,Yoga,,"{raw}",False,d,https://x/1\n')
    assert load_csv(p)[0].focus == expected


@real_catalogue
def test_every_real_focus_is_one_of_the_five_or_unknown():
    focuses = {c.focus for c in load_csv(ROOT / "alo-scoring" / "alo_classes.csv")}
    assert focuses <= {"full body", "core", "legs", "arms", "booty", None}

"""B18 §A/§B — the workout capture and render contract (REQ-WKT-001..022).

`strength.py` computes e1RM, volume and ACWR. This is what may be captured, how a correction
outranks a guess, and what a surface may say about the result.
"""
import datetime as dt

import pytest

from tools.engines.workout_contract import (CAPTURE_PATHS, CaptureRefused, COVERAGE_WINDOW_DAYS,
                                            RenderViolation, SET_FIELDS, SetRecord,
                                            WORKOUT_TIER, check_capture_path, check_workout_copy,
                                            coverage, deterministic_render, log_rest_day,
                                            measure_tier, objective_function, point_in_time,
                                            record_set, render_numeral, resolve_exercise,
                                            supersede)

ALIASES = {"bench": "barbell_bench_press", "bench press": "barbell_bench_press",
           "barbell bench": "barbell_bench_press", "bb bench": "barbell_bench_press"}


def test_REQ_WKT_002_the_pwa_never_captures_a_workout():
    assert CAPTURE_PATHS == ("ios_shortcut", "manual_logger")
    for path in CAPTURE_PATHS:
        assert check_capture_path(path)
    for bad in ("pwa", "PWA", "getUserMedia", "browser_microphone"):
        with pytest.raises(CaptureRefused, match="REQ-WKT-002"):
            check_capture_path(bad)


def test_REQ_WKT_001_the_set_is_the_unit_and_a_session_total_is_not_enough():
    """5x5 at 225 and 1x25 at 135 are the same volume and completely different training. Once the
    sets are collapsed the distinction cannot be recovered."""
    assert set(SET_FIELDS) == {"exercise", "load", "reps", "rpe"}
    s = record_set(exercise="barbell_bench_press", load=225, reps=5, rpe=8)
    assert s.load == 225 and s.reps == 5
    with pytest.raises(ValueError, match="REQ-WKT-001"):
        record_set(exercise="x", load=225, reps=5)


def test_REQ_WKT_006_four_spellings_resolve_to_one_entity():
    """Left as free text they are four series with a quarter of the data each — and nothing
    detects that, because four sparse trends look exactly like four exercises Joe does rarely."""
    resolved = {resolve_exercise(r, ALIASES)["exercise"]
                for r in ("Bench", "bench press", "Barbell Bench", "BB bench")}
    assert resolved == {"barbell_bench_press"}


def test_REQ_WKT_006_an_unmapped_movement_is_reviewed_not_given_its_own_series():
    out = resolve_exercise("zercher good morning", ALIASES)
    assert out["exercise"] is None and out["needs_review"] is True
    assert "exercise done rarely" in out["note"]


def test_REQ_WKT_006_020_a_human_answer_outranks_the_alias_map():
    out = resolve_exercise("bench", ALIASES, human_confirmed="dumbbell_bench_press")
    assert out["exercise"] == "dumbbell_bench_press"
    assert out["resolved_by"] == "human" and out["outranks_automated"] is True


def test_REQ_WKT_001_the_raw_text_is_kept_beside_the_canonical_entity():
    out = resolve_exercise("BB bench", ALIASES)
    assert out["exercise"] == "barbell_bench_press" and out["raw_exercise"] == "BB bench"


def test_REQ_WKT_020_a_correction_supersedes_and_an_automated_value_cannot_overwrite_it():
    """Superseding rather than updating, so "what did the log say before Joe fixed it" still has
    an answer — the only way to tell a mis-transcription from a change of mind."""
    original = record_set(exercise="barbell_bench_press", load=225, reps=5, rpe=8)
    old, new = supersede(original, load=235, corrected_by="joe")
    assert old.superseded_by == "next" and old.load == 225
    assert new.load == 235 and new.corrected_by == "joe"
    with pytest.raises(ValueError, match="REQ-WKT-020"):
        supersede(new, load=200, corrected_by="engine")


def test_REQ_WKT_019_a_rest_day_is_observed_absent_and_an_unlogged_day_is_not():
    """"I chose not to train" and "no data" are different facts, and only the first is evidence
    about training. An ACWR that reads them alike will call one of them detraining."""
    rest = log_rest_day(dt.date(2026, 9, 10), deliberate=True)
    assert rest["presence"] == "observed_absent"
    assert rest["is_evidence_about_training"] is True
    gap = log_rest_day(dt.date(2026, 9, 11), deliberate=False)
    assert gap["presence"] == "unknown" and gap["is_evidence_about_training"] is False


def test_REQ_WKT_019_the_presence_vocabulary_is_closed():
    with pytest.raises(ValueError, match="REQ-WKT-019"):
        SetRecord(exercise="x", load=1, reps=1, rpe=1, presence="skipped")


def test_REQ_WKT_013_a_set_recorded_after_the_window_closed_does_not_enter_the_measure():
    """A set ABOUT a day inside the window that was RECORDED after it closed is knowledge the
    measure did not have. Letting it in makes a historical figure change when somebody backfills,
    and then the number Joe saw last week is not the number he sees now."""
    close = dt.date(2026, 9, 7)
    known = dt.datetime(2026, 9, 8, 0, 0)
    sets = [
        {"day": dt.date(2026, 9, 5), "recorded_at": dt.datetime(2026, 9, 5, 20)},
        {"day": dt.date(2026, 9, 5), "recorded_at": dt.datetime(2026, 9, 20, 9)},
        {"day": dt.date(2026, 9, 9), "recorded_at": dt.datetime(2026, 9, 7, 9)},
    ]
    kept = point_in_time(sets, window_close=close, known_at=known)
    assert len(kept) == 1 and kept[0]["recorded_at"] == dt.datetime(2026, 9, 5, 20)


def test_REQ_WKT_014_016_no_streak_no_compliance_score_on_any_workout_surface():
    """Strength is a trend toward a stated objective, not an attendance record. Joe's capture has
    stopped twice this year through no act of his — a streak would have scored both as lapses."""
    assert check_workout_copy("Bench e1RM is trending up: 253-262 lb.") == ()
    for bad in ("12 day streak", "your compliance is 60%", "your run is broken",
                "perfect week", "3 consecutive days"):
        assert check_workout_copy(bad), bad


def test_REQ_WKT_014_broke_alone_is_not_banned_because_of_what_it_means_here():
    """"Broken" is attendance language; "broke" is not, in a strength context. "You broke a
    personal record" is exactly what this surface exists to say, so banning the stem would refuse
    the sentence the objective function is about."""
    assert check_workout_copy("You broke your previous best at 245 lb.") == ()
    assert check_workout_copy("Your run is broken.")


def test_REQ_WKT_021_no_causal_or_experimental_strength_claim():
    for bad in ("Volume caused the gain", "e1RM rose because you slept more",
                "This proves the programme works"):
        v = check_workout_copy(bad)
        assert any("REQ-WKT-021" in x for x in v), bad


def test_REQ_WKT_021_a_workout_measure_is_DESCRIPTIVE():
    out = measure_tier({"measure": "strength_e1rm_lb", "value": [253, 262]})
    assert out["tier"] == WORKOUT_TIER == "DESCRIPTIVE"
    assert "not an experiment" in out["note"]


def test_REQ_WKT_016_coverage_is_a_rolling_figure_with_nothing_to_break():
    c = coverage(3)
    assert c["window_days"] == COVERAGE_WINDOW_DAYS == 7
    assert c["coverage_pct"] == pytest.approx(42.9, abs=0.1)
    assert c["streak"] is None and c["breakable"] is False


def test_REQ_WKT_015_every_workout_numeral_traces_to_a_stored_value():
    """The render layer formats. It does not divide, average, convert or total — each of those is
    a computation, and a computation performed at render time has no stored result to trace to."""
    stored = {"e1rm_low": 253.12, "e1rm_high": 262.5}
    assert render_numeral(253.12, stored_fields=stored, unit="lb") == "253.12 lb"
    with pytest.raises(RenderViolation, match="REQ-WKT-015"):
        render_numeral(257.81, stored_fields=stored, unit="lb")   # the midpoint, computed here


def test_REQ_WKT_015_a_numeral_renders_with_its_unit():
    with pytest.raises(RenderViolation, match="REQ-WKT-015"):
        render_numeral(253.12, stored_fields={"a": 253.12}, unit=None)


def test_REQ_WKT_017_the_figures_survive_the_language_layer_being_down():
    """A surface that goes blank when the model is unavailable has made the model load-bearing
    for facts that were computed without it."""
    out = deterministic_render({"e1rm": [253, 262]}, language_layer_available=False)
    assert out["rendered"] is True and out["path"] == "deterministic_template"
    assert deterministic_render({}, language_layer_available=True)["path"] == "model"


def test_REQ_WKT_022_the_objective_is_strength_AND_body_composition_together():
    """Either alone is gameable in a direction Joe does not want: e1RM rises with bodyweight, and
    body composition improves by eating less and lifting less."""
    out = objective_function({"e1rm_trend": "up"}, {"trend": "flat"})
    assert out["objective"] == ("strength_progression", "body_composition")
    assert "gameable" in out["note"]
    assert out["tier"] == "DESCRIPTIVE"

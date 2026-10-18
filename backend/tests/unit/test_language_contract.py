"""Partial preference writes reject ambiguous values before persistence."""

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from inspector.foundation import PreferenceInput, SettingsInput


@pytest.mark.parametrize(
    "model,field,valid",
    [
        (PreferenceInput, "language", "pl"),
        (PreferenceInput, "theme_mode", "dark"),
        (SettingsInput, "default_language", "pl"),
        (SettingsInput, "default_theme_mode", "light"),
        (SettingsInput, "branding", "Synthetic Inspector"),
        (SettingsInput, "additional_security_measures", False),
    ],
)
def test_partial_inputs_accept_one_changed_field_and_reject_null(model, field, valid):
    payload = {"expected_revision": 3, field: valid}
    parsed = model.model_validate(payload)
    assert parsed.model_dump(exclude_unset=True) == payload
    validator = Draft202012Validator(model.model_json_schema())
    assert validator.is_valid(payload)
    assert not validator.is_valid({"expected_revision": 3})
    assert not validator.is_valid({**payload, field: None})
    with pytest.raises(ValidationError):
        model.model_validate({**payload, field: None})
    with pytest.raises(ValidationError):
        model.model_validate({"expected_revision": 3})


@pytest.mark.parametrize("model", [PreferenceInput, SettingsInput])
def test_partial_inputs_reject_mass_assignment_and_invalid_revision(model):
    field = "language" if model is PreferenceInput else "default_language"
    with pytest.raises(ValidationError):
        model.model_validate({"expected_revision": 1, field: "pl", "role": "administrator"})
    for invalid in ("1", True, 0, -1, None):
        with pytest.raises(ValidationError):
            model.model_validate({"expected_revision": invalid, field: "pl"})


@pytest.mark.parametrize("invalid", ["PL", "de", "Polski", "", 1, True, [], {}])
def test_only_supported_language_codes_are_accepted(invalid):
    for model, field in ((PreferenceInput, "language"), (SettingsInput, "default_language")):
        with pytest.raises(ValidationError):
            model.model_validate({"expected_revision": 1, field: invalid})
    with pytest.raises(ValidationError):
        SettingsInput.model_validate({"expected_revision": 1, "default_language": "default"})

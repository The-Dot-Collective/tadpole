"""Tests for person_matching_synth.config module."""

import pytest
from pathlib import Path
from person_matching_synth.config import GeneratorConfig, ErrorType, default_weights


class TestGeneratorConfigValidation:
    """Test GeneratorConfig.__post_init__ validation."""

    def test_default_weights_structure(self):
        """default_weights returns a dict with valid ErrorType keys per field."""
        weights = default_weights()
        # All whitelist fields must be present
        expected_fields = {"firstname", "surname", "dateofbirth", "licencenumber", "postcode", "line1", "line2"}
        assert set(weights.keys()) == expected_fields
        # Every inner dict must have at least one non-negative weight and all keys must be ErrorType
        for field, wdict in weights.items():
            assert len(wdict) > 0
            for err_type, weight in wdict.items():
                assert isinstance(err_type, ErrorType)
                assert weight >= 0

    def test_valid_default_config(self):
        """Default GeneratorConfig values are valid and constructible."""
        config = GeneratorConfig()
        assert config.seed == 42
        assert config.n_persons == 1_000
        assert config.error_rate == 0.15
        assert config.dl_presence_rate == 0.95
        assert config.dl_benign_suffix_mutation_rate == 0.10
        assert config.sk_collision_rate == 0.01
        assert config.max_errors_per_appearance == 2
        assert config.allow_unrecoverable_appearances is False
        assert config.locale == "en_GB"
        assert config.emit_ground_truth is True

    def test_error_rate_bounds(self):
        """error_rate must be in [0.0, 1.0]."""
        with pytest.raises(ValueError, match="error_rate"):
            GeneratorConfig(error_rate=-0.1)
        with pytest.raises(ValueError, match="error_rate"):
            GeneratorConfig(error_rate=1.1)

    def test_quotes_per_person_bounds(self):
        """quotes_per_person_min <= quotes_per_person_max and both >= 1."""
        with pytest.raises(ValueError, match="quotes_per_person_min"):
            GeneratorConfig(quotes_per_person_min=0)
        with pytest.raises(ValueError, match="quotes_per_person_min"):
            GeneratorConfig(quotes_per_person_min=10, quotes_per_person_max=5)
        # Valid case
        config = GeneratorConfig(quotes_per_person_min=2, quotes_per_person_max=5)
        assert config.quotes_per_person_min == 2
        assert config.quotes_per_person_max == 5

    def test_n_persons_positive(self):
        """n_persons must be >= 1."""
        with pytest.raises(ValueError, match="n_persons"):
            GeneratorConfig(n_persons=0)
        with pytest.raises(ValueError, match="n_persons"):
            GeneratorConfig(n_persons=-10)

    def test_max_errors_nonnegative(self):
        """max_errors_per_appearance must be >= 0."""
        with pytest.raises(ValueError, match="max_errors_per_appearance"):
            GeneratorConfig(max_errors_per_appearance=-1)

    def test_rate_bounds_various(self):
        """All rate parameters must be in [0.0, 1.0]."""
        with pytest.raises(ValueError, match="dl_presence_rate"):
            GeneratorConfig(dl_presence_rate=1.5)
        with pytest.raises(ValueError, match="dl_benign_suffix_mutation_rate"):
            GeneratorConfig(dl_benign_suffix_mutation_rate=-0.1)
        with pytest.raises(ValueError, match="sk_collision_rate"):
            GeneratorConfig(sk_collision_rate=2.0)

    def test_error_type_weights_keys_must_be_subset_of_whitelist(self):
        """error_type_weights keys must be a subset of FIELD_WHITELIST keys."""
        from person_matching_synth.fields import FIELD_WHITELIST
        valid_fields = set(FIELD_WHITELIST.keys())
        # Invalid field key
        bad_weights = {"invalid_field": {ErrorType.TYPO: 1.0}}
        with pytest.raises(ValueError, match="error_type_weights"):
            GeneratorConfig(error_type_weights=bad_weights)
        # Valid structure but extra field (duplicate key check is not the issue; field must be valid)
        # This checks that all top-level keys are valid field names
        bad_weights2 = {"firstname": {ErrorType.TYPO: 1.0}, "not_a_field": {ErrorType.TYPO: 1.0}}
        with pytest.raises(ValueError, match="error_type_weights"):
            GeneratorConfig(error_type_weights=bad_weights2)

    def test_error_type_weights_inner_keys_must_match_whitelist(self):
        """Inner dict keys must be subset of that field's whitelist."""
        from person_matching_synth.fields import FIELD_WHITELIST
        weights = default_weights()
        # Tamper: add MISSING_TOKEN to firstname (not permitted for firstname per §4.2)
        weights["firstname"][ErrorType.MISSING_TOKEN] = 1.0
        with pytest.raises(ValueError, match="error_type_weights"):
            GeneratorConfig(error_type_weights=weights)

    def test_error_type_weights_nonnegative(self):
        """Weights must be non-negative."""
        weights = default_weights()
        weights["firstname"][ErrorType.TYPO] = -1.0
        with pytest.raises(ValueError, match="error_type_weights"):
            GeneratorConfig(error_type_weights=weights)

    def test_error_type_weights_sum_positive(self):
        """At least one weight per field must be > 0."""
        weights = default_weights()
        weights["firstname"] = {ErrorType.TYPO: 0.0, ErrorType.TRANSPOSITION: 0.0}
        with pytest.raises(ValueError, match="error_type_weights"):
            GeneratorConfig(error_type_weights=weights)

    def test_output_dir_path(self):
        """output_dir is accepted as Path; no validation beyond writability at generation time."""
        config = GeneratorConfig(output_dir=Path("./custom_out"))
        assert config.output_dir == Path("./custom_out")

from app.core.security import generate_result_id, safe_result_path, validate_result_id


# --- validate_result_id ---


def test_valid_uuid4_passes():
    assert validate_result_id("550e8400-e29b-41d4-a716-446655440000") is True


def test_generated_id_passes_validation():
    result_id = generate_result_id()
    assert validate_result_id(result_id) is True


def test_uppercase_uuid4_passes():
    assert validate_result_id("550E8400-E29B-41D4-A716-446655440000") is True


def test_incremental_id_rejected():
    assert validate_result_id("1") is False
    assert validate_result_id("12345") is False


def test_random_string_rejected():
    assert validate_result_id("hello-world") is False
    assert validate_result_id("not-a-uuid-at-all") is False


def test_empty_string_rejected():
    assert validate_result_id("") is False


def test_directory_traversal_rejected():
    assert validate_result_id("../../etc/passwd") is False
    assert validate_result_id("../../../foo") is False
    assert validate_result_id("..%2F..%2Fetc%2Fpasswd") is False


def test_uuid_with_traversal_prefix_rejected():
    assert validate_result_id("../550e8400-e29b-41d4-a716-446655440000") is False


def test_non_v4_uuid_rejected():
    # UUID v1 (version digit is 1, not 4)
    assert validate_result_id("550e8400-e29b-11d4-a716-446655440000") is False


# --- generate_result_id ---


def test_generate_result_id_format():
    result_id = generate_result_id()
    assert validate_result_id(result_id) is True


def test_generated_ids_are_unique():
    ids = {generate_result_id() for _ in range(100)}
    assert len(ids) == 100


# --- safe_result_path ---


def test_safe_result_path_valid_id(tmp_path):
    result_id = generate_result_id()
    path = safe_result_path(str(tmp_path), result_id)
    assert path is not None
    assert path.endswith(f"{result_id}.json")
    assert str(tmp_path) in path


def test_safe_result_path_traversal_returns_none(tmp_path):
    assert safe_result_path(str(tmp_path), "../../etc/passwd") is None
    assert safe_result_path(str(tmp_path), "../../../foo") is None


def test_safe_result_path_invalid_id_returns_none(tmp_path):
    assert safe_result_path(str(tmp_path), "not-valid") is None
    assert safe_result_path(str(tmp_path), "12345") is None
    assert safe_result_path(str(tmp_path), "") is None


def test_safe_result_path_stays_within_data_dir(tmp_path):
    result_id = generate_result_id()
    path = safe_result_path(str(tmp_path), result_id)
    assert path is not None
    assert path.startswith(str(tmp_path.resolve()))

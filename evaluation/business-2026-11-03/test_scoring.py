from run_benchmark import score


def test_duplicate_occurrences_are_not_collapsed():
    case = {
        "gold": [{"class": "org", "text": "ACME"}, {"class": "org", "text": "ACME"}]
    }
    payload = {
        "document": {
            "text": "ACME ACME",
            "extractions": [
                {
                    "extraction_class": "org",
                    "extraction_text": "ACME",
                    "char_interval": {"start_pos": 0, "end_pos": 4},
                }
            ],
        }
    }
    result = score(case, payload)
    assert (result["tp"], result["fp"], result["fn"]) == (1, 0, 1)


def test_grounded_partial_name_does_not_count_as_exact_entity():
    result = score(
        {"gold": [{"class": "person", "text": "Personne Alpha"}]},
        {
            "document": {
                "text": "Personne Alpha",
                "extractions": [
                    {
                        "extraction_class": "person",
                        "extraction_text": "Alpha",
                        "char_interval": {"start_pos": 9, "end_pos": 14},
                    }
                ],
            }
        },
    )
    assert (result["tp"], result["fp"], result["fn"]) == (0, 1, 1)
    assert result["source_grounded"] == result["offset_valid"] == 1


def test_unicode_offsets_use_code_points_and_whitespace_is_normalized():
    result = score(
        {"gold": [{"class": "org", "text": "Été Alpha"}]},
        {
            "document": {
                "text": "😀 Été\nAlpha",
                "extractions": [
                    {
                        "extraction_class": "org",
                        "extraction_text": "Été Alpha",
                        "char_interval": {"start_pos": 2, "end_pos": 11},
                    }
                ],
            }
        },
    )
    assert result["tp"] == 1
    assert result["offset_valid"] == 1


def test_empty_document_does_not_create_true_positives():
    result = score(
        {"gold": []}, {"document": {"text": "texte neutre", "extractions": []}}
    )
    assert result["tp"] == result["fp"] == result["fn"] == 0

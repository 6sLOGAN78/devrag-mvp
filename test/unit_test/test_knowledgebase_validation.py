"""Input policy of the dataset service that needs no database (plan 03-14; KB-01, KB-02, KB-04, D-19)."""
from __future__ import annotations

import pytest

from api.db.services import knowledgebase_service as kb
from api.db.services.service_errors import Kind, ServiceError
from common.settings import UploadSettings

pytestmark = pytest.mark.unit


def _record(**over) -> kb.DatasetRecord:
    base = {
        "id": "a" * 32, "tenant_id": "b" * 32, "name": "n", "description": "", "avatar": "", "language": "English", "embd_id": "m@P",
        "tenant_embd_id": "c" * 32, "parser_id": "naive", "parser_config": dict(kb.DEFAULT_PARSER_CONFIG), "permission": "me",
        "created_by": "d" * 32, "doc_num": 0, "chunk_num": 0, "token_num": 0, "create_time": 1, "update_time": 2,
    }  # fmt: skip
    return kb.DatasetRecord(**{**base, **over})


def test_the_lock_name_for_a_tenant_is_42_characters():
    assert kb.create_lock_name("f" * 32) == "kb-create:" + "f" * 32
    assert len(kb.create_lock_name("f" * 32)) == 42


def test_parser_ids_are_the_fourteen_documented_chunkers_with_naive_first():
    assert kb.PARSER_IDS[0] == "naive" and len(set(kb.PARSER_IDS)) == 14
    assert {"qa", "paper", "book", "laws", "table", "tag", "audio", "one"} <= set(kb.PARSER_IDS)


def test_a_valid_request_is_normalised_and_the_config_merged_over_the_defaults():
    fields = kb._validate(kb.CreateRequest(name="  Docs  ", parser_config={"chunk_token_num": 256}))
    assert fields.name == "Docs" and fields.parser_id == "naive" and fields.permission == "me" and fields.language == "English"
    assert fields.parser_config["chunk_token_num"] == 256 and fields.parser_config["pages"] == [[1, 1000000]]
    assert kb.DEFAULT_PARSER_CONFIG["chunk_token_num"] == 512, "the defaults are not mutated by a merge"


@pytest.mark.parametrize(
    "req",
    [
        kb.CreateRequest(name=""),
        kb.CreateRequest(name="   "),
        kb.CreateRequest(name="n" * 129),
        kb.CreateRequest(name=5),  # type: ignore[arg-type]
        kb.CreateRequest(name="n", parser_id="bogus"),
        kb.CreateRequest(name="n", permission="all"),
        kb.CreateRequest(name="n", permission=""),
        kb.CreateRequest(name="n", language=" "),
        kb.CreateRequest(name="n", language="L" * 33),
        kb.CreateRequest(name="n", description="d" * 2001),
        kb.CreateRequest(name="n", description=3),  # type: ignore[arg-type]
        kb.CreateRequest(name="n", avatar="a" * 200_001),
        kb.CreateRequest(name="n", parser_config={"k": "v" * 4100}),
        kb.CreateRequest(name="n", parser_config=[1]),  # type: ignore[arg-type]
        kb.CreateRequest(name="n", parser_config={"k": object()}),
    ],
)
def test_bad_input_is_dataset_invalid_and_never_echoed(req):
    with pytest.raises(ServiceError) as err:
        kb._validate(req)
    assert err.value.kind is Kind.INVALID and err.value.reason == "dataset_invalid"
    assert "v" * 50 not in err.value.message and "d" * 50 not in err.value.message


def test_like_wildcards_and_the_escape_character_are_escaped():
    assert kb._escape_like("100%_a\\b") == "100\\%\\_a\\\\b"


def test_the_dto_lists_its_keys_and_adds_limits_only_on_request():
    plain = kb.dataset_dto(_record(), embedding_dimension=8)
    assert "upload_limits" not in plain and plain["embedding_dimension"] == 8
    assert not {"status", "source", "location"} & set(plain)
    limits = kb.dataset_dto(_record(), embedding_dimension=None, include_limits=UploadSettings())["upload_limits"]
    assert set(limits) == {"max_file_bytes", "max_files_per_request", "max_documents", "allowed_extensions"}
    assert isinstance(limits["allowed_extensions"], list) and "pdf" in limits["allowed_extensions"]

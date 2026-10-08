from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.db.services import superuser_service
from common.security import emails

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
VECTORS = json.loads((ROOT / "test" / "fixtures" / "email_canonical_vectors.json").read_text(encoding="utf-8"))["canonical"]


@pytest.mark.parametrize("vec", VECTORS, ids=[v["id"] for v in VECTORS])
def test_canonical_email_matches_the_shared_vectors(vec):
    assert emails.canonical_email(vec["input"]) == vec["canonical"]
    assert emails.canonical_email(vec["canonical"]) == vec["canonical"]
    if vec["canonical"]:
        assert emails.new_account_email_chars(vec["canonical"]) is vec["new_ok"]


def test_superuser_seed_uses_the_one_canonical_rule():
    assert superuser_service.normalise_email("Ａdmin@Example.TEST ") == "admin@example.test"


@pytest.mark.parametrize("email", ["ádmin@example.test", "ádmin@example.test", "admin@exámple.test"])
def test_superuser_seed_refuses_an_address_a_new_account_could_not_use(email):
    with pytest.raises(superuser_service.SuperuserConfigError) as err:
        superuser_service.validate_credentials(email, "fake-password-1234")
    assert "SUPERUSER_EMAIL" in str(err.value)

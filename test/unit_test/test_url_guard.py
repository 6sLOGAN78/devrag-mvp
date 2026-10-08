"""Outbound provider base-URL guard (plan 03-02, SSRF, Pitfall 13, D-15, D-16). No test touches the network."""
from __future__ import annotations

import pytest

from common.net.url_guard import (
    INTERNAL_SERVICE_HOSTS,
    UnsafeBaseUrl,
    ValidatedUrl,
    assert_unchanged,
    validate_base_url,
)

pytestmark = pytest.mark.unit

PUBLIC_V4 = "104.18.2.115"
PUBLIC_V6 = "2606:4700::6812:273"


def table(mapping: dict[str, list[str]]):
    """Injected resolver: an unknown host is unresolvable, exactly like a failed lookup."""

    def resolve(host: str, port: int) -> list[str]:
        try:
            return list(mapping[host])
        except KeyError:
            raise OSError("no such host") from None

    return resolve


def no_dns(host: str, port: int) -> list[str]:
    raise AssertionError(f"an IP literal must be judged without a lookup (asked for {host})")


PUBLIC_HOSTS = table({"openrouter.ai": [PUBLIC_V4], "api.openai.com": [PUBLIC_V4, PUBLIC_V6]})


def reason_of(url: str, *, allow_private: bool = False, resolve=None, deny_hosts=()) -> str:
    with pytest.raises(UnsafeBaseUrl) as caught:
        validate_base_url(url, allow_private=allow_private, deny_hosts=deny_hosts, resolve=resolve or PUBLIC_HOSTS)
    return caught.value.reason


# --- accepted -----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected_url", "host", "port"),
    [
        ("https://openrouter.ai/api/v1", "https://openrouter.ai/api/v1", "openrouter.ai", 443),
        ("https://api.openai.com/v1/", "https://api.openai.com/v1", "api.openai.com", 443),
        ("  HTTPS://OpenRouter.AI./api/v1/  ", "HTTPS://OpenRouter.AI./api/v1", "openrouter.ai", 443),
        ("http://openrouter.ai:8080/v1", "http://openrouter.ai:8080/v1", "openrouter.ai", 8080),
    ],
    ids=["https_host", "trailing_slash_stripped", "case_and_trailing_dot", "explicit_port"],
)
def test_public_urls_are_accepted(url: str, expected_url: str, host: str, port: int) -> None:
    result = validate_base_url(url, allow_private=False, resolve=PUBLIC_HOSTS)
    assert isinstance(result, ValidatedUrl)
    assert (result.url, result.host, result.port) == (expected_url, host, port)
    assert result.addresses and all(isinstance(a, str) for a in result.addresses)


def test_public_ip_literal_is_accepted_without_a_lookup() -> None:
    result = validate_base_url("https://8.8.8.8/v1", allow_private=False, resolve=no_dns)
    assert result.addresses == ("8.8.8.8",)


def test_the_default_resolver_is_used_for_an_ip_literal_without_dns() -> None:
    assert validate_base_url("https://1.1.1.1/v1", allow_private=False).host == "1.1.1.1"


# --- always denied ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("file:///etc/passwd", "scheme"),
        ("ftp://openrouter.ai/x", "scheme"),
        ("gopher://openrouter.ai/x", "scheme"),
        ("openrouter.ai/api/v1", "scheme"),
        ("http://user:pw@openrouter.ai/v1", "userinfo"),
        ("http://user@openrouter.ai/v1", "userinfo"),
        ("https://openrouter.ai/v1#frag", "fragment"),
        ("https://openrouter.ai/v1#", "fragment"),
        ("http:///v1", "host"),
        ("http://:8080/v1", "host"),
        ("http://openrouter.ai\\@127.0.0.1/", "host"),
        ("http://open router.ai/", "host"),
        ("http://openrouter.ai:99999/", "host"),
        ("http://openrouter.ai:0/", "host"),
        ("http://0.0.0.0/", "host"),
        ("http://[::]/", "host"),
        ("http://224.0.0.1/", "host"),
    ],
    ids=[
        "file", "ftp", "gopher", "no_scheme", "userinfo", "userinfo_without_password", "fragment", "empty_fragment",
        "empty_host", "port_only", "backslash", "space_in_host", "port_too_large", "port_zero", "unspecified_v4",
        "unspecified_v6", "multicast",
    ],
)
@pytest.mark.parametrize("allow_private", [False, True], ids=["strict", "private_allowed"])
def test_malformed_and_dangerous_forms_are_always_denied(url: str, reason: str, allow_private: bool) -> None:
    assert reason_of(url, allow_private=allow_private) == reason


@pytest.mark.parametrize(
    "url",
    [
        pytest.param("http://169.254.169.254/latest/meta-data", id="metadata_v4"),
        pytest.param("http://[fe80::1]/", id="link_local_v6"),
        pytest.param("http://[fe80::1%25eth0]/", id="link_local_v6_zone"),
        pytest.param("http://2852039166/", id="decimal"),
        pytest.param("http://0xa9fea9fe/", id="hex"),
        pytest.param("http://0xA9.0xFE.0xA9.0xFE/", id="hex_dotted"),
        pytest.param("http://0251.0376.0251.0376/", id="octal"),
        pytest.param("http://169.254.43518/", id="short_form"),
        pytest.param("http://[::ffff:169.254.169.254]/", id="mapped"),
        pytest.param("http://[::ffff:a9fe:a9fe]/", id="mapped_hex"),
        pytest.param("http://[::169.254.169.254]/", id="ipv4_compatible"),
        pytest.param("http://[64:ff9b::a9fe:a9fe]/", id="nat64"),
        pytest.param("http://[2002:a9fe:a9fe::1]/", id="six_to_four"),
        pytest.param("http://[fd00:ec2::254]/", id="aws_ipv6_metadata"),
        pytest.param("http://metadata.example/", id="link_local_hostname"),
    ],
)
@pytest.mark.parametrize("allow_private", [False, True], ids=["strict", "private_allowed"])
def test_link_local_and_metadata_spellings_are_denied_after_resolution(url: str, allow_private: bool) -> None:
    resolve = table({"metadata.example": ["169.254.169.254"]})
    assert reason_of(url, allow_private=allow_private, resolve=resolve) == "link_local"


@pytest.mark.parametrize("name", sorted(INTERNAL_SERVICE_HOSTS) + ["MySQL", "ES01", "Redis.", "MINIO"])
@pytest.mark.parametrize("allow_private", [False, True], ids=["strict", "private_allowed"])
def test_internal_service_names_are_denied_even_when_they_resolve_publicly(name: str, allow_private: bool) -> None:
    resolve = table({name.lower().rstrip("."): [PUBLIC_V4]})
    assert reason_of(f"http://{name}:9200/", allow_private=allow_private, resolve=resolve) == "internal_service"


def test_internal_service_hosts_are_the_project_names() -> None:
    assert INTERNAL_SERVICE_HOSTS == frozenset({"mysql", "redis", "es01", "minio", "mailpit", "app"})


@pytest.mark.parametrize("allow_private", [False, True], ids=["strict", "private_allowed"])
def test_caller_supplied_deny_hosts_are_denied(allow_private: bool) -> None:
    resolve = table({"models.corp.example": [PUBLIC_V4]})
    assert reason_of("https://Models.Corp.Example/v1", allow_private=allow_private, resolve=resolve, deny_hosts=["models.corp.example"]) == "internal_service"
    assert reason_of("https://8.8.4.4/v1", allow_private=allow_private, resolve=no_dns, deny_hosts=["8.8.4.4"]) == "internal_service"


def test_a_host_with_several_records_is_denied_if_any_record_is_denied() -> None:
    resolve = table({"rebind.example": [PUBLIC_V4, "169.254.169.254"], "mixed.example": [PUBLIC_V4, "10.0.0.7"]})
    assert reason_of("https://rebind.example/v1", allow_private=True, resolve=resolve) == "link_local"
    assert reason_of("https://mixed.example/v1", allow_private=False, resolve=resolve) == "private"


def test_an_unresolvable_host_is_denied() -> None:
    assert reason_of("https://nowhere.invalid/v1") == "unresolvable"
    assert reason_of("https://empty.example/v1", resolve=table({"empty.example": []})) == "unresolvable"
    assert reason_of("https://garbage.example/v1", resolve=table({"garbage.example": ["not-an-address"]})) == "unresolvable"


# --- private ranges: only with allow_private -----------------------------------------------------------------------------


PRIVATE_URLS = [
    pytest.param("http://localhost:11434/v1", id="localhost"),
    pytest.param("http://LOCALHOST./v1", id="localhost_trailing_dot"),
    pytest.param("http://127.0.0.1:11434/v1", id="loopback_v4"),
    pytest.param("http://127.1/v1", id="loopback_short"),
    pytest.param("http://2130706433/v1", id="loopback_decimal"),
    pytest.param("http://[::1]:11434/v1", id="loopback_v6"),
    pytest.param("http://[::ffff:127.0.0.1]/v1", id="loopback_mapped"),
    pytest.param("http://10.1.2.3/v1", id="rfc1918_10"),
    pytest.param("http://172.17.0.1:11434/v1", id="host_gateway"),
    pytest.param("http://192.168.1.20/v1", id="rfc1918_192"),
    pytest.param("http://[fd12:3456::1]/v1", id="unique_local"),
    pytest.param("http://100.64.0.9/v1", id="carrier_grade_nat"),
    pytest.param("http://lan.example/v1", id="private_hostname"),
]


@pytest.mark.parametrize("url", PRIVATE_URLS)
def test_private_and_loopback_targets_are_denied_by_default(url: str) -> None:
    assert reason_of(url, allow_private=False, resolve=table({"lan.example": ["192.168.7.7"]})) == "private"


@pytest.mark.parametrize("url", PRIVATE_URLS)
def test_private_and_loopback_targets_are_accepted_when_allowed(url: str) -> None:
    result = validate_base_url(url, allow_private=True, resolve=table({"lan.example": ["192.168.7.7"]}))
    assert result.addresses


def test_localhost_is_judged_without_a_lookup() -> None:
    assert validate_base_url("http://localhost:11434/v1", allow_private=True, resolve=no_dns).addresses


# --- messages never echo the URL ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://user:hunter2-FAKE@openrouter.ai/v1",
        "http://169.254.169.254/latest/sk-or-v1-FAKEFAKEFAKEFAKEFAKE0009",
        "ftp://secret-host-FAKE.example/x",
        "https://openrouter.ai/v1#sk-FAKEFAKEFAKEFAKEFAKEFAKE0010",
        "https://nowhere.invalid/sk-FAKEFAKEFAKEFAKEFAKEFAKE0011",
    ],
)
def test_the_error_message_never_contains_the_url(url: str) -> None:
    with pytest.raises(UnsafeBaseUrl) as caught:
        validate_base_url(url, allow_private=False, resolve=PUBLIC_HOSTS)
    text = f"{caught.value} {caught.value!r} {caught.value.args}"
    for piece in ("hunter2", "FAKE", "169.254", "nowhere", "secret-host", "openrouter"):
        assert piece not in text
    assert caught.value.reason in {"scheme", "userinfo", "fragment", "host", "link_local", "internal_service", "private", "unresolvable"}


def test_unsafe_base_url_is_a_value_error_with_a_reason() -> None:
    err = UnsafeBaseUrl("private")
    assert isinstance(err, ValueError) and err.reason == "private"


# --- call-time re-validation (DNS rebinding) ------------------------------------------------------------------------------


def test_assert_unchanged_passes_when_the_addresses_stay_allowed() -> None:
    first = validate_base_url("https://openrouter.ai/api/v1", allow_private=False, resolve=PUBLIC_HOSTS)
    again = assert_unchanged(first, "https://openrouter.ai/api/v1", allow_private=False, deny_hosts=(), resolve=PUBLIC_HOSTS)
    assert again.addresses == first.addresses


@pytest.mark.parametrize(
    ("moved_to", "reason"),
    [("169.254.169.254", "link_local"), ("10.0.0.5", "private"), ("::ffff:169.254.169.254", "link_local")],
    ids=["to_metadata", "to_private", "to_mapped_metadata"],
)
def test_assert_unchanged_denies_a_host_that_moved_to_a_denied_address(moved_to: str, reason: str) -> None:
    first = validate_base_url("https://openrouter.ai/api/v1", allow_private=False, resolve=PUBLIC_HOSTS)
    with pytest.raises(UnsafeBaseUrl) as caught:
        assert_unchanged(first, "https://openrouter.ai/api/v1", allow_private=False, deny_hosts=(), resolve=table({"openrouter.ai": [moved_to]}))
    assert caught.value.reason == reason


def test_assert_unchanged_judges_the_same_rules_as_validate() -> None:
    first = validate_base_url("http://localhost:11434/v1", allow_private=True, resolve=no_dns)
    with pytest.raises(UnsafeBaseUrl) as caught:
        assert_unchanged(first, "http://localhost:11434/v1", allow_private=False, deny_hosts=(), resolve=no_dns)
    assert caught.value.reason == "private"

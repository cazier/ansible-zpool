# pylint: disable=invalid-name,wildcard-import,protected-access,unused-argument

from ward import test, raises

from tests.conftest import test_data
from cazier.zfs.plugins.modules.utils import _match, _pairs, _get_disk, _get_type


@test("utils: _pairs")  # type: ignore[misc]
def _() -> None:

    for i, (j, k) in enumerate(_pairs(map(str, range(10)))):
        assert str(i * 2) == str(j)
        assert str((i * 2) + 1) == str(k)


for item in test_data()("match"):

    @test("utils: _match: {title}")  # type: ignore[misc]
    def _(string: str = item["input"], expected: dict[str, str] = item["expected"], title: str = item["name"]) -> None:
        pattern = r"(?P<a>\d+)-(?P<b>\d+)-(?P<c>\d+)"

        assert _match(string, pattern) == expected


for item in test_data()("get_disk"):

    @test("utils: _get_disk: {title}")  # type: ignore[misc]
    def _(string: str = item["input"], expected: str = item["expected"], title: str = item["name"]) -> None:
        assert _get_disk(string) == expected


@test("utils: _get_disk: multiple partition error")  # type: ignore[misc]
def _() -> None:
    with raises(TypeError) as exception:
        _get_disk("\t/dev/disk/by-id/disk-part2\t9")
    assert "Only using whole disk (or sparse images) is supported at this time" in str(exception.raised)


for item in test_data()("get_type"):

    @test("utils: _get_type: {title}")  # type: ignore[misc]
    def _(string: str = item["input"], expected: str = item["expected"], title: str = item["name"]) -> None:
        assert _get_type(string) == expected

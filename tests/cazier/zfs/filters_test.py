# pylint: disable=invalid-name,wildcard-import,protected-access,unused-argument

import typing as t

from ward import test, fixture

from tests.conftest import test_data
from cazier.zfs.plugins.filter.zfs import FilterModule


@fixture
def _module() -> FilterModule:
    return FilterModule()


for item in test_data()("filters"):

    @test("converting snapshots: {name}")  # type: ignore[misc]
    def _(module: FilterModule = _module, data: dict[str, t.Any] = item, name: str = item["name"]) -> None:
        frequency = data["frequency"]
        expectation = data["expectation"]

        assert module.snapshot(frequency) == expectation

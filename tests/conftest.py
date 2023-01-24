import typing as t
import pathlib

import yaml
from ward import Scope, fixture


@fixture(scope=Scope.Global)  # type: ignore[misc]
def test_data() -> t.Callable[[str], t.Any]:
    data: dict[str, t.Any] = {}

    for file in pathlib.Path(__file__).parent.joinpath("config").glob("*.yaml"):
        data.update(**yaml.safe_load(file.read_text(encoding="utf8")))

    def wrapped(test_name: str) -> t.Any:
        return data[test_name]

    return wrapped

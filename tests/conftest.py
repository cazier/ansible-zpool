import typing as t
import pathlib

import yaml
from ward.hooks import hook
from ward.config import Config

# pylint: disable=unused-argument,global-statement


TEST_DATA: dict[str, t.Any] = {}


@hook  # type: ignore[misc]
def before_session(config: Config) -> None:
    global TEST_DATA
    TEST_DATA = yaml.safe_load(pathlib.Path(__file__).parent.joinpath("test_data.yaml").read_text(encoding="utf8"))

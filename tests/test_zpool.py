import typing as t
import pathlib

import yaml
from ward import test, raises

from cazier.zfs.plugins.modules.zpool import get_zpool_data  # pylint: disable=import-error

data: dict[str, t.Any] = yaml.safe_load(
    pathlib.Path(__file__).parent.joinpath("test_data.yaml").read_text(encoding="utf8")
)

for name, _input, expected in map(dict.values, data[__name__]):

    @test(f"parsing zpool list: {name}")  # pylint: disable=cell-var-from-loop
    def _(console: str = _input, output: dict[str, t.Any] = expected) -> None:  # type: ignore[assignment]
        assert get_zpool_data(console) == output


@test("parsing failures")
def _() -> None:
    with raises(TypeError) as exception:
        get_zpool_data(
            """
test	27.2T	420K	27.2T	-	-	0%	0%	1.00x	ONLINE	-
	/tmp/01.raw	9.08T	141K	9.08T	-	-	0%	0.00%	-	ONLINE
	/dev/disk/by-id/scsi-SATA_SN9300G_SERIAL-part1	9.08T	142K	9.08T	-	-	0%	0.00%	-	ONLINE
	/dev/disk/by-id/scsi-SATA_SN9300G_SERIAL-part2	9.08T	142K	9.08T	-	-	0%	0.00%	-	ONLINE
"""
        )
    assert "Only using whole disk (or sparse images) is supported" in str(exception.raised)

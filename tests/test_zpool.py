import typing as t
import pathlib

import yaml
from ward import test, raises

from cazier.zfs.plugins.modules.zpool import ztype_to_create, console_to_ztype  # pylint: disable=import-error

data: dict[str, t.Any] = yaml.safe_load(
    pathlib.Path(__file__).parent.joinpath("test_data.yaml").read_text(encoding="utf8")
)

for item in data[__name__]:

    # pylint: disable-next=cell-var-from-loop
    @test(f"parsing zpool list: {item['name']}")  # type: ignore[misc]
    def _(console: str = item["console"], _list: dict[str, t.Any] = item["list"]) -> None:
        assert console_to_ztype(console) == _list


@test("parsing failures")  # type: ignore[misc]
def _() -> None:
    with raises(TypeError) as exception:
        console_to_ztype(
            """
test	27.2T	420K	27.2T	-	-	0%	0%	1.00x	ONLINE	-
	/tmp/01.raw	9.08T	141K	9.08T	-	-	0%	0.00%	-	ONLINE
	/dev/disk/by-id/scsi-SATA_SN9300G_SERIAL-part1	9.08T	142K	9.08T	-	-	0%	0.00%	-	ONLINE
	/dev/disk/by-id/scsi-SATA_SN9300G_SERIAL-part2	9.08T	142K	9.08T	-	-	0%	0.00%	-	ONLINE
"""
        )
    assert "Only using whole disk (or sparse images) is supported" in str(exception.raised)


for item in data[__name__]:

    # pylint: disable-next=cell-var-from-loop
    @test(f"zpool create command: {item['name']}")  # type: ignore[misc]
    def _(create: str = item["create"], _list: dict[str, t.Any] = item["list"]) -> None:

        assert " ".join(ztype_to_create(_list)) == create

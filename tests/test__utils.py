import typing as t

from ward import test, raises

from tests.conftest import TEST_DATA
from cazier.zfs.plugins.modules._utils import Vdev, Zpool

# pylint: disable=invalid-name

FILE = __name__.replace("test_", "")

for item in TEST_DATA[FILE]:

    # pylint: disable-next=cell-var-from-loop
    @test(f"parsing zpool list: {item['name']}")  # type: ignore[misc]
    def _(console: str = item["console"], _list: dict[str, t.Any] = item["list"]) -> None:
        assert Zpool.parse_console(console).dump() == _list


@test("parsing failures")  # type: ignore[misc]
def _() -> None:
    with raises(TypeError) as exception:
        Zpool.parse_console(
            """
test	27.2T	420K	27.2T	-	-	0%	0%	1.00x	ONLINE	-
	/tmp/01.raw	9.08T	141K	9.08T	-	-	0%	0.00%	-	ONLINE
	/dev/disk/by-id/scsi-SATA_SN9300G_SERIAL-part1	9.08T	142K	9.08T	-	-	0%	0.00%	-	ONLINE
	/dev/disk/by-id/scsi-SATA_SN9300G_SERIAL-part2	9.08T	142K	9.08T	-	-	0%	0.00%	-	ONLINE
"""
        )
    assert "Only using whole disk (or sparse images) is supported" in str(exception.raised)


for item in TEST_DATA[FILE]:

    # pylint: disable-next=cell-var-from-loop
    @test(f"zpool create command: {item['name']}")  # type: ignore[misc]
    def _(console: str = item["console"], create: str = item["create"]) -> None:
        assert " ".join(Zpool.parse_console(console).create_command()) == create


@test("vdevs")  # type: ignore[misc]
def _() -> None:
    a = Vdev()
    b = Vdev()

    assert a == b
    assert a != {"type": "raidz1", "disks": ["drive0.raw", "drive1.raw", "drive2.raw"]}
    assert not a

    a.append("drive0.raw")
    assert a
    assert a != b

    b.append("drive1.raw", "drive0.raw")
    a.append("drive1.raw")

    assert a.dump() != b.dump()
    assert a == b
    assert hash(a) == hash(b)

    a.type = "raidz1"
    assert a != b

    a.clear()
    assert a == Vdev()
    assert a.dump() == {"disks": []}

    assert b.creation() == ["drive1.raw", "drive0.raw"]

    c = Vdev(type="raidz1", disks=["drive0.raw", "drive1.raw", "drive2.raw"])
    assert c.dump() == {"type": "raidz1", "disks": ["drive0.raw", "drive1.raw", "drive2.raw"]}

    assert c.creation() == ["raidz1", "drive0.raw", "drive1.raw", "drive2.raw"]

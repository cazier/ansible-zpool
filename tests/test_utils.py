# pylint: disable=invalid-name, wildcard-import, protected-access

import typing as t

from ward import test, xfail, raises

from tests.conftest import TEST_DATA
from cazier.zfs.plugins.modules._utils import *
from cazier.zfs.plugins.modules._utils import _Pool, _match, _pairs, _get_disk, _get_type

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


@xfail
@test("vdevs: todo")  # type: ignore[misc]
def _() -> None:
    a = Vdev(["drive0.raw", "drive1.raw"])

    assert a.dump() == a


@test("pools: generic and redundant")  # type: ignore[misc]
def _() -> None:
    a = _Pool("a")
    b = _Pool("b")

    assert a == b
    assert not a

    vdev = a.new()
    assert vdev.dump() == {"disks": []}
    vdev.append("drive0.raw")

    assert a
    assert a != b
    assert a.dump() == [{"disks": ["drive0.raw"]}]

    vdev2 = b.new()
    vdev2.append("drive1.raw", "drive0.raw")

    vdev.append("drive1.raw")

    assert a.dump() != b.dump()
    assert a == b

    assert vdev == vdev2
    assert vdev.dump() != vdev2.dump()
    assert vdev in a
    assert vdev2 in a

    storage = StoragePool(vdevs=[Vdev(["drive0.raw", "drive1.raw", "drive2.raw"], type="raidz1")])
    assert storage.creation() == ["raidz1", "drive0.raw", "drive1.raw", "drive2.raw"]
    storage._check_redundancy(Vdev([], type=None))

    assert all(vdev.type is not None for vdev in storage.vdevs)

    log = LogPool(vdevs=[Vdev(["drive0.raw", "drive1.raw"])])
    assert log.dump() == [{"disks": ["drive0.raw", "drive1.raw"], "type": "stripe"}]
    assert log.creation() == ["log", "drive0.raw", "drive1.raw"]

    assert all(vdev.type is not None for vdev in log.vdevs)


@test("pools: non-redundant")  # type: ignore[misc]
def _() -> None:
    cache = CachePool(vdevs=[Vdev(["drive0.raw", "drive1.raw"])])
    assert cache.creation() == ["cache", "drive0.raw", "drive1.raw"]
    cache._check_redundancy(Vdev(["drive2.raw"]))

    with raises(ValueError) as exception:
        cache.append(Vdev(["drive2.raw"]))
    assert "Cannot add new vdevs to a CachePool. The existing vdev can only be extended." in str(exception.raised)

    cache.extend("drive2.raw")
    cache.extend(Vdev(["drive3.raw"]))
    assert cache.creation() == ["cache", "drive0.raw", "drive1.raw", "drive2.raw", "drive3.raw"]

    with raises(ValueError) as exception:
        CachePool(vdevs=[Vdev(["drive0.raw", "drive1.raw"], type="raidz1")])
    assert "Non-redundant pools (i.e., class: CachePool) cannot have a type argument." in str(exception.raised)

    assert all(vdev.type is None for vdev in cache.vdevs)

    spare = SparePool(vdevs=[Vdev(["drive0.raw", "drive1.raw"])])
    assert spare.creation() == ["spare", "drive0.raw", "drive1.raw"]

    assert all(vdev.type is None for vdev in spare.vdevs)

    with raises(ValueError) as exception:
        spare.append(Vdev(["drive2.raw"]))
    assert "Cannot add new vdevs to a SparePool. The existing vdev can only be extended." in str(exception.raised)

    spare.extend("drive2.raw")
    spare.extend(Vdev(["drive3.raw"]))
    assert spare.creation() == ["spare", "drive0.raw", "drive1.raw", "drive2.raw", "drive3.raw"]

    with raises(ValueError) as exception:
        SparePool(vdevs=[Vdev(["drive0.raw", "drive1.raw"], type="raidz1")])
    assert "Non-redundant pools (i.e., class: SparePool) cannot have a type argument." in str(exception.raised)


@xfail
@test("pools: todo")  # type: ignore[misc]
def _() -> None:
    a = _Pool("a", [Vdev(["drive0.raw", "drive1.raw"])])

    assert a.dump() == a
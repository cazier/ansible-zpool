# pylint: disable=invalid-name,wildcard-import,protected-access,unused-argument

import typing as t

from ward import test, xfail, raises

from tests.conftest import test_data
from cazier.zfs.plugins.modules.utils import Vdev, Zpool, LogPool, CachePool, SparePool, StoragePool, _Pool

for item in test_data()("utils"):

    @test("parsing zpool list: {name}")  # type: ignore[misc]
    def _(console: str = item["console"], _list: dict[str, t.Any] = item["list"], name: str = item["name"]) -> None:
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


for item in test_data()("utils"):

    @test("zpool create command: {name}")  # type: ignore[misc]
    def _(console: str = item["console"], create: str = item["create"], name: str = item["name"]) -> None:
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
    a = _Pool()
    b = _Pool()

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
    a = _Pool([Vdev(["drive0.raw", "drive1.raw"])])

    assert a.dump() == a


@test("diffs")  # type: ignore[misc]
def _() -> None:
    a = Vdev()
    b = Vdev(["drive0.raw", "drive1.raw", "drive2.raw"])
    c = Vdev(["drive0.raw", "drive2.raw"])
    d = Vdev(["drive1.raw", "drive3.raw"])

    assert a - b == set()
    assert a.difference(b) == set()

    assert b - a == {"drive0.raw", "drive1.raw", "drive2.raw"}
    assert b - c == {"drive1.raw"}
    assert c - b == set()

    assert c ^ d == {"drive0.raw", "drive2.raw", "drive1.raw", "drive3.raw"}
    assert c.symmetric_difference(d) == {"drive0.raw", "drive2.raw", "drive1.raw", "drive3.raw"}

    assert Vdev() ^ Vdev() == set()

    with raises(ValueError) as expected:
        _ = Vdev(type="striped") ^ Vdev(type="mirror")
    assert "Diffing of vdevs with different types is not supported." in str(expected.raised)

    e = _Pool()
    f = _Pool([Vdev(["drive0.raw"]), Vdev(["drive1.raw"]), Vdev(["drive2.raw"])])
    g = _Pool([Vdev(["drive0.raw"]), Vdev(["drive2.raw"])])
    h = _Pool([Vdev(["drive1.raw"]), Vdev(["drive3.raw"])])

    assert e - f == set()
    assert e.difference(f) == set()

    assert f - e == {Vdev(["drive0.raw"]), Vdev(["drive1.raw"]), Vdev(["drive2.raw"])}
    assert f - g == {Vdev(["drive1.raw"])}
    assert g - f == set()

    assert g ^ h == {Vdev(["drive0.raw"]), Vdev(["drive1.raw"]), Vdev(["drive2.raw"]), Vdev(["drive3.raw"])}
    assert g.symmetric_difference(h) == {
        Vdev(["drive0.raw"]),
        Vdev(["drive1.raw"]),
        Vdev(["drive2.raw"]),
        Vdev(["drive3.raw"]),
    }

    assert _Pool() ^ _Pool() == set()

    with raises(ValueError) as expected:
        _ = StoragePool() ^ _Pool()
    assert "Diffing of different pool types is not supported." in str(expected.raised)

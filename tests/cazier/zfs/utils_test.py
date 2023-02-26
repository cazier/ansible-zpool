# pylint: disable=invalid-name,wildcard-import,protected-access,unused-argument

import typing as t

from ward import test, raises

from tests.conftest import test_data
from cazier.zfs.plugins.module_utils.utils import Vdev, Zpool, Option, LogPool, CachePool, SparePool, StoragePool, _Pool

for _item in test_data()("utils"):

    @test("parsing zpool list: {name}")  # type: ignore[misc]
    def _(console: str = _item["console"], _list: dict[str, t.Any] = _item["list"], name: str = _item["name"]) -> None:
        assert Zpool.from_string(console).dump() == _list


@test("parsing failures")  # type: ignore[misc]
def _() -> None:
    with raises(TypeError) as expected:
        Zpool.from_string(
            """
test	27.2T	420K	27.2T	-	-	0%	0%	1.00x	ONLINE	-
	/tmp/01.raw	9.08T	141K	9.08T	-	-	0%	0.00%	-	ONLINE
	/dev/disk/by-id/scsi-SATA_SN9300G_SERIAL-part1	9.08T	142K	9.08T	-	-	0%	0.00%	-	ONLINE
	/dev/disk/by-id/scsi-SATA_SN9300G_SERIAL-part2	9.08T	142K	9.08T	-	-	0%	0.00%	-	ONLINE
"""
        )
    assert "Only using whole disk (or sparse images) is supported" in str(expected.raised)

    with raises(ValueError) as expected:  # type: ignore[assignment]
        Zpool.from_string(
            """
test
	/tmp/01.raw	9.08T	141K	9.08T	-	-	0%	0.00%	-	ONLINE
	/dev/disk/by-id/scsi-SATA_SN9300G_SERIAL-part1	9.08T	142K	9.08T	-	-	0%	0.00%	-	ONLINE
"""
        )
    assert "Could not match a zpool name from the console text." in str(expected.raised)

    with raises(TypeError) as expected:
        Zpool.from_string(
            """
test	27.2T	420K	27.2T	-	-	0%	0%	1.00x	ONLINE	-
	exception	9.08T	141K	9.08T	-	-	0%	0.00%	-	ONLINE
	error	9.08T	142K	9.08T	-	-	0%	0.00%	-	ONLINE
	failure	9.08T	142K	9.08T	-	-	0%	0.00%	-	ONLINE
"""
        )
    assert "Couldn't parse the zpool list data properly." in str(expected.raised)

    with raises(ValueError) as expected:  # type: ignore[assignment]
        Zpool.from_string(
            """
cannot open 'failure': no such pool
"""
        )
    assert "There was no pool found with the name failure." in str(expected.raised)


for _item in test_data()("utils"):

    @test("parsing data dicts: {name}")  # type: ignore[misc]
    def _(_list: dict[str, t.Any] = _item["list"], name: str = _item["name"]) -> None:
        assert Zpool.from_dict(_list).dump() == _list


for _item in test_data()("utils"):

    @test("zpool create command: {name}")  # type: ignore[misc]
    def _(console: str = _item["console"], create: str = _item["create"], name: str = _item["name"]) -> None:
        assert " ".join(Zpool.from_string(console).create_command()) == create


for _item in test_data()("options"):

    @test("parsing zpool options: {name}")  # type: ignore[misc]
    def _(item: dict[str, t.Any] = _item, name: str = _item["name"]) -> None:
        zpool = Zpool.from_string(item["console"], item["options"])
        assert zpool == Zpool.from_dict(zpool.dump())

        assert zpool.dump() == item["list"]
        assert " ".join(zpool.create_command()) == item["create"]


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

    # Equality from non-identical types
    assert a.dump() == a
    assert a != {"disks": 0}

    assert a.from_dict(a.dump()) == a

    assert b == ["drive0.raw", "drive1.raw"]
    assert b == {"drive0.raw", "drive1.raw"}
    assert b == ("drive0.raw", "drive1.raw")

    assert a != object()

    a.clear()
    assert a == Vdev()
    assert a.dump() == {"disks": []}

    assert b.creation() == ["drive1.raw", "drive0.raw"]

    c = Vdev(type="raidz1", disks=["drive0.raw", "drive1.raw", "drive2.raw"])
    assert c.dump() == {"type": "raidz1", "disks": ["drive0.raw", "drive1.raw", "drive2.raw"]}

    assert c.creation() == ["raidz1", "drive0.raw", "drive1.raw", "drive2.raw"]

    with raises(TypeError) as expected:
        Vdev(disks=0)  # type: ignore[arg-type]
    assert "A Vdev must have an iterable as the disks argument." in str(expected.raised)


@test("pools: generic")  # type: ignore[misc]
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
    assert a.dump() == {"": [{"disks": ["drive0.raw"]}]}

    vdev2 = b.new()
    vdev2.append("drive1.raw", "drive0.raw")

    vdev.append("drive1.raw")

    assert a.dump() != b.dump()
    assert a == b

    assert vdev == vdev2
    assert vdev.dump() != vdev2.dump()
    assert vdev in a
    assert vdev2 in a


@test("pools: redundant")  # type: ignore[misc]
def _() -> None:
    storage = StoragePool(vdevs=[Vdev(["drive0.raw", "drive1.raw"], type="raidz1")])
    assert storage.creation() == ["raidz1", "drive0.raw", "drive1.raw"]
    storage._check_redundancy(Vdev([], type=None))

    vdev3 = storage.new()
    vdev3.append("drive10.raw", "drive11.raw")
    assert vdev3.type == "stripe"

    # Equality from non-identical types
    assert storage.dump() == storage
    assert storage != {"storage": 0}
    assert storage == {
        "storage": [
            {"disks": ["drive0.raw", "drive1.raw"], "type": "raidz1"},
            {"disks": ["drive10.raw", "drive11.raw"], "type": "stripe"},
        ]
    }

    assert storage == [
        {"disks": ["drive0.raw", "drive1.raw"], "type": "raidz1"},
        {"disks": ["drive10.raw", "drive11.raw"], "type": "stripe"},
    ]
    assert storage == (
        {"disks": ["drive0.raw", "drive1.raw"], "type": "raidz1"},
        {"disks": ["drive10.raw", "drive11.raw"], "type": "stripe"},
    )

    assert storage.from_dict(storage.dump()) == storage

    assert storage != object()

    vdev4 = storage.new("raidz3")
    vdev4.append("drive20.raw")
    assert vdev4.type == "raidz3"

    assert storage.dump() == {
        "storage": [
            {"disks": ["drive0.raw", "drive1.raw"], "type": "raidz1"},
            {"disks": ["drive10.raw", "drive11.raw"], "type": "stripe"},
            {"disks": ["drive20.raw"], "type": "raidz3"},
        ],
    }

    assert storage.from_dict(storage.dump()) == storage
    assert all(vdev.type is not None for vdev in storage.vdevs)

    assert storage.devices == {"drive0.raw", "drive1.raw", "drive10.raw", "drive11.raw", "drive20.raw"}

    log = LogPool(vdevs=[Vdev(["drive0.raw", "drive1.raw"])])
    assert log.dump() == {"logs": [{"disks": ["drive0.raw", "drive1.raw"], "type": "stripe"}]}
    assert log.creation() == ["log", "drive0.raw", "drive1.raw"]

    assert log.from_dict(log.dump()) == log
    assert all(vdev.type is not None for vdev in log.vdevs)

    with raises(TypeError) as expected:
        _Pool([{"disks": ["drive0.raw"]}])  # type: ignore[list-item]
    assert "A _Pool cannot be initialized with non-Vdevs. Use .from_dict() to create from a" in str(expected.raised)

    with raises(TypeError) as expected:
        _Pool.from_dict({})
    assert "Could not create a _Pool from this input data: The input data has no pools." in str(expected.raised)

    with raises(TypeError) as expected:
        StoragePool.from_dict({"storage": [], "log": []})
    assert "Could not create a StoragePool from this input data: There were too many pools." in str(expected.raised)

    with raises(AttributeError) as expected:  # type: ignore[assignment]
        _Pool.from_dict({"Invalid Pool Type": []})
    assert "Could not find the requested pool type in the module." in str(expected.raised)


@test("pools: non-redundant")  # type: ignore[misc]
def _() -> None:
    cache = CachePool(vdevs=[Vdev(["drive0.raw", "drive1.raw"])])
    assert cache.creation() == ["cache", "drive0.raw", "drive1.raw"]
    cache._check_redundancy(Vdev(["drive2.raw"]))

    with raises(ValueError) as expected:
        cache.append(Vdev(["drive2.raw"]))
    assert "Cannot add new vdevs to a CachePool. The existing vdev can only be extended." in str(expected.raised)

    cache.extend("drive2.raw")
    cache.extend(Vdev(["drive3.raw"]))
    assert cache.creation() == ["cache", "drive0.raw", "drive1.raw", "drive2.raw", "drive3.raw"]

    with raises(ValueError) as expected:
        CachePool(vdevs=[Vdev(["drive0.raw", "drive1.raw"], type="raidz1")])
    assert "Non-redundant pools (i.e., class: CachePool) cannot have a type argument." in str(expected.raised)

    assert cache.from_dict(cache.dump()) == cache
    assert all(vdev.type is None for vdev in cache.vdevs)

    spare = SparePool(vdevs=[Vdev(["drive0.raw", "drive1.raw"])])
    assert spare.creation() == ["spare", "drive0.raw", "drive1.raw"]

    assert spare.from_dict(spare.dump()) == spare
    assert all(vdev.type is None for vdev in spare.vdevs)

    with raises(ValueError) as expected:
        spare.append(Vdev(["drive2.raw"]))
    assert "Cannot add new vdevs to a SparePool. The existing vdev can only be extended." in str(expected.raised)

    spare.extend("drive2.raw")
    spare.extend(Vdev(["drive3.raw"]))
    assert spare.creation() == ["spare", "drive0.raw", "drive1.raw", "drive2.raw", "drive3.raw"]

    with raises(ValueError) as expected:
        SparePool(vdevs=[Vdev(["drive0.raw", "drive1.raw"], type="raidz1")])
    assert "Non-redundant pools (i.e., class: SparePool) cannot have a type argument." in str(expected.raised)


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


@test("zpools")  # type: ignore[misc]
def _() -> None:
    a = Zpool("a")
    b = Zpool("a")

    assert not a

    assert list(a.names) == ["storage", "logs", "cache", "spare"]
    assert list(map(id, a.pools)) == [id(a.storage), id(a.logs), id(a.cache), id(a.spare)]

    assert list(map(lambda k: (k[0], id(k[1])), iter(a))) == [
        ("storage", id(a.storage)),
        ("logs", id(a.logs)),
        ("cache", id(a.cache)),
        ("spare", id(a.spare)),
    ]

    assert id(a.get_pool("storage")) == id(a.storage)

    assert a == b
    assert not a

    v = a.storage.new("raidz1")
    v.append("drive0.raw", "drive1.raw", "drive2.raw")

    assert a != b

    b = Zpool.from_dict(a.dump())
    b.storage.vdevs[0].disks.reverse()

    assert a == b

    b.spare.append(Vdev(disks=["drive3.raw"]))
    b.logs.append(Vdev(disks=["drive4.raw", "drive5.raw", "drive6.raw", "drive7.raw"], type="mirror"))

    assert b.devices == {
        "drive0.raw",
        "drive1.raw",
        "drive2.raw",
        "drive3.raw",
        "drive4.raw",
        "drive5.raw",
        "drive6.raw",
        "drive7.raw",
    }

    string = """
test	27.2T	420K	27.2T	-	-	0%	0%	1.00x	ONLINE	-
\t/tmp/01.raw	9.08T	141K	9.08T	-	-	0%	0.00%	-	ONLINE
\t/dev/disk/by-id/scsi-SATA_SN9300G_SERIAL-part1	9.08T	142K	9.08T	-	-	0%	0.00%	-	ONLINE
\t/tmp/03.raw	9.08T	137K	9.08T	-	-	0%	0.00%	-	ONLINE
"""
    c = Zpool.from_string(string)

    assert c == c.dump()
    assert c != {}

    assert c == string
    assert c != ""

    assert c != object()

    d = Zpool.from_dict(c.dump())
    d.spare.new().append("spare.raw")

    assert c != d

    d.name = "d"
    assert c != d


@test("zpools")  # type: ignore[misc]
def _() -> None:
    a = Option("ashift", "12")
    b = Option("ashift", "")

    assert a != b

    b.value = "12"
    assert a == b

    b.source = "local"
    assert a == b

    assert a != {"property": False}
    assert a != object()

    c = Option.from_dict({"ashift": "12"})
    d = Option.from_dict({"property": "ashift", "value": "12", "source": "-"})

    assert a == c
    assert c == d

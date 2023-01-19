import re
import typing as t
import itertools
import dataclasses

_VdevHint = dict[str, str | list[str]]
_PoolHint = list[_VdevHint]


def _pairs(iterable: t.Iterable[str]) -> t.Iterator[tuple[str, str]]:
    """Recipe to get overlapping pairs of items from an iterable: (ABCD) -> AB, CD, EF, ...

    Args:
        iterable (t.Iterable[str]): iterable of values

    Yields:
        tuple[str, str]: pairwise elements from the iterable
    """
    for first, second in zip(*[iter(iterable)] * 2, strict=True):
        yield first, second


def _match(line: str, pattern: str, flags: int = 0) -> dict[str, str | None]:
    """Helper function to try to match a pattern, or return ``None`` if no match is found

    Args:
        line (str): input string
        pattern (str): regular expression pattern
        flags (int): regex flags

    Returns:
        t.Optional[str]: the matched string content, or None, if no match was found
    """
    if match := re.match(pattern, line, flags=flags):
        return match.groupdict()

    return {}


def _get_disk(line: str) -> t.Optional[str]:
    """Attempts to match a zpool list line for a drive/disk. This looks for an indentation along
    with a leading `/` (slash).

    If the result is a disk (found beneath /dev/disk/by-*), the result will be just the disk
    name (i.e., scsi-SATA_SN9300G_SERIAL). If the result is a raw/sparse image, the full path
    is returned (i.e., /tmp/subfolder/sparse.raw)

    Args:
        line (str): zpool list line

    Raises:
        TypeError: When a disk is used, without it being the entire disk (i.e., one partition
            not numbered `1`) an exception is raised.

    Returns:
        t.Optional[str]: The final component of the disk name
    """
    match = _match(
        line,
        r"""^                                      # Start of the line
            \t                                     # Leading tab (indentation)
            (?P<prefix>\/)                         # Capture only strings starting with a slash
            (?P<dev>dev\/disk\/by-\w+\/)?          # Optional /dev/disk (ignoring /by-*/)
            (?P<disk>.*?)                          # Capture for disk or raw image name
            (?P<partition>-part(?P<number>\d+)|)   # Capture a partition number, if it exists. Otherwise ""
            \t                                     # Tab signifying the end of the name
            [\d-]                                  # Disk usage numbers
            """,
        flags=re.VERBOSE,
    )

    if match == {}:
        return None

    if (number := match.pop("number")) and int(number) != 1:
        raise TypeError("Only using whole disk (or sparse images) is supported at this time.")

    prefix, dev, disk, partition = match.values()

    if not number and not dev:
        disk = f"{prefix}{disk}"

    if number and not dev:
        disk = f"{prefix}{disk}{partition}"

    return disk


def _get_type(line: str) -> t.Optional[str]:
    """Attempts to match a zpool list line for the vdev type (raidz1, mirror, etc.)

    Args:
        line (str): zpool list line

    Returns:
        t.Optional[str]: The vdev type
    """
    return _match(line, r"\t(?P<type>raidz(?:1|2|3)|mirror)-\d+\t\d").get("type")


@dataclasses.dataclass(eq=False)
class Vdev:
    disks: list[str] = dataclasses.field(default_factory=list)
    type: t.Optional[str] = None

    def __eq__(self, __o: object) -> bool:
        if not isinstance(__o, self.__class__):
            return False

        if self.type != __o.type:
            return False

        if set(self.disks) != set(__o.disks):
            return False

        return True

    def __hash__(self) -> int:
        return hash((self.type, *sorted(self.disks)))

    def __bool__(self) -> bool:
        return len(self.disks) > 0

    def __sub__(self, other: "Vdev") -> set[str]:
        if self.type != other.type:
            raise ValueError("Diffing of vdevs with different types is not supported.")

        return set(self.disks).difference(other.disks)

    def difference(self, other: "Vdev") -> set[str]:
        return self - other

    def __xor__(self, other: "Vdev") -> set[str]:
        return (self - Vdev()).union(other - Vdev())

    def symmetric_difference(self, other: "Vdev") -> set[str]:
        return self ^ other

    def append(self, *items: str) -> None:
        self.disks.extend(items)

    def clear(self) -> None:
        self.disks.clear()
        self.type = Vdev.type

    def dump(self) -> _VdevHint:
        data: _VdevHint = {"disks": self.disks}

        if self.type:
            data["type"] = self.type

        return data

    def creation(self) -> list[str]:
        cmd = []

        if self:
            if self.type and self.type != "stripe":
                cmd.append(self.type)

            cmd.extend(self.disks)

        return cmd


@dataclasses.dataclass(eq=False)
class _Pool:
    name: str = dataclasses.field(default="", init=False)  # This is intentionally blank, as it gets set by the subclass
    redundancy: bool = dataclasses.field(default=False, init=False)
    vdevs: list[Vdev] = dataclasses.field(default_factory=list)
    _default_vdev_: t.Optional[str] = dataclasses.field(default=None, init=False)

    @classmethod
    def _check_redundancy(cls, *items: Vdev) -> None:
        if not cls.redundancy and any(item.type for item in items):
            raise ValueError(f"Non-redundant pools (i.e., class: {cls.__name__}) cannot have a type argument.")

    def __post_init__(self) -> None:
        for vdev in self.vdevs:
            self._check_redundancy(vdev)

            if vdev.type is None:
                vdev.type = self._default_vdev_

    def __eq__(self, __o: object) -> bool:
        if not isinstance(__o, self.__class__):
            return False

        if set(self.vdevs) != set(__o.vdevs):
            return False

        return True

    def __contains__(self, element: Vdev) -> bool:
        return element in self.vdevs

    def __bool__(self) -> bool:
        return any(bool(vdev) for vdev in self.vdevs)

    def __sub__(self, other: "_Pool") -> set[Vdev]:
        if type(self) != type(other):  # pylint: disable=unidiomatic-typecheck
            raise ValueError("Diffing of different pool types is not supported.")

        return set(self.vdevs).difference(other.vdevs)

    def difference(self, other: "_Pool") -> set[Vdev]:
        return self - other

    def __xor__(self, other: "_Pool") -> set[Vdev]:
        return (self - _Pool()).union(other - _Pool())

    def symmetric_difference(self, other: "_Pool") -> set[Vdev]:
        return self ^ other

    def _append(self, *items: Vdev) -> None:
        self._check_redundancy(*items)
        self.vdevs.extend(items)

    def append(self, *items: Vdev) -> None:
        if len(self.vdevs) > 0:
            raise ValueError(
                f"Cannot add new vdevs to a {self.__class__.__name__}. The existing vdev can only be extended."
            )

        self._append(*items)

    def extend(self, *items: Vdev | str) -> None:
        new: list[str] = []

        for item in items:
            if isinstance(item, Vdev):
                self._check_redundancy(item)
                new.extend(item.disks)

            else:
                new.append(item)

        self.vdevs[-1].append(*new)

    def new(self, _type: t.Optional[str] = None) -> Vdev:
        self._check_redundancy((vdev := Vdev(type=_type)))
        self.append(vdev)

        return vdev

    def dump(self) -> _PoolHint:
        return [vdev.dump() for vdev in self.vdevs if vdev]

    @property
    def create(self) -> list[str]:
        return [self.name]

    def creation(self) -> list[str]:
        cmd = []

        if self:
            cmd.extend(self.create)

            for vdev in self.vdevs:
                cmd.extend(vdev.creation())

        return cmd


@dataclasses.dataclass
class _Redundant(_Pool):
    redundancy: bool = dataclasses.field(default=True, init=False)
    _default_vdev_: str = dataclasses.field(default="stripe", init=False)

    def new(self, _type: t.Optional[str] = None) -> Vdev:
        if _type is None:
            _type = _Redundant._default_vdev_

        return super().new(_type)

    def append(self, *items: Vdev) -> None:
        self._append(*items)


@dataclasses.dataclass
class StoragePool(_Redundant):
    name: str = "storage"

    @property
    def create(self) -> list[str]:
        return []


@dataclasses.dataclass
class LogPool(_Redundant):
    name: str = "logs"

    @property
    def create(self) -> list[str]:
        return ["log"]


@dataclasses.dataclass
class CachePool(_Pool):
    name: str = "cache"


@dataclasses.dataclass
class SparePool(_Pool):
    name: str = "spare"


@dataclasses.dataclass
class Zpool:
    name: str = dataclasses.field(metadata={"dump": False})
    storage: StoragePool = dataclasses.field(default_factory=StoragePool)
    logs: LogPool = dataclasses.field(default_factory=LogPool)
    cache: CachePool = dataclasses.field(default_factory=CachePool)
    spare: SparePool = dataclasses.field(default_factory=SparePool)

    def get_pool(self, name: str | dataclasses.Field[_Pool]) -> StoragePool | LogPool | CachePool | SparePool:
        if isinstance(name, dataclasses.Field):
            name = name.name

        return t.cast(t.Union[StoragePool, LogPool, CachePool, SparePool], getattr(self, name))

    @property
    def pools(self) -> t.Iterator[dataclasses.Field[_Pool]]:
        yield from (field for field in dataclasses.fields(self) if field.metadata.get("dump", True))

    @property
    def names(self) -> t.Iterator[str]:
        yield from (field.name for field in dataclasses.fields(self) if field.metadata.get("dump", True))

    def dump(self) -> dict[str, str | _PoolHint]:
        data: dict[str, str | _PoolHint] = {"name": self.name}

        for field in self.pools:
            if pool := self.get_pool(field.name):
                data[field.name] = pool.dump()

        return data

    @classmethod
    def parse_console(cls, console: str) -> "Zpool":
        lines = console.strip().splitlines()
        name = _match(lines.pop(0), r"(?P<name>.+?)\s\d").get("name")

        if not name:
            raise ValueError("Could not match a zpool name from the console text.")

        zpool = cls(name)

        sections: dict[str, str] = {
            k.strip(): v
            for k, v in _pairs(["storage"] + re.split(r"^(logs|cache|spare).*$", "\n".join(lines), flags=re.MULTILINE))
        }

        for key in zpool.names:
            pool = zpool.get_pool(key)

            vdev = pool.new()

            if key == "storage":
                section = sections["storage"]

            else:
                section = sections.get(key, "")

            for current, future in itertools.pairwise(section.splitlines() + ["<terminator>"]):
                if current in ("<terminator>", ""):
                    continue

                if disk := _get_disk(current):
                    vdev.disks.append(disk)

                elif _type := _get_type(current):
                    vdev.type = _type

                else:
                    raise TypeError("Couldn't parse the zpool list data properly.")

                if (_type := _get_type(future)) or future == "<terminator>":
                    if isinstance(pool, _Redundant):
                        vdev = pool.new()

        return zpool

    def create_command(self) -> list[str]:
        """Convert a set of input data to a list containing the variables for the `zpool create`
        command.

        Returns:
            list[str]: creation command line arguments
        """
        cmd = [self.name]

        for pool in self.names:
            cmd.extend(self.get_pool(pool).creation())

        return cmd

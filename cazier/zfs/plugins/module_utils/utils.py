import re
import typing as t
import itertools
import dataclasses

_VdevHint = dict[str, str | list[str]]
_PoolHint = dict[str, list[_VdevHint]]
_OptionHint = dict[str, str]
_ZpoolHint = dict[str, str | list[_VdevHint] | list[_OptionHint]]

_PoolsHint = t.Union["StoragePool", "LogPool", "CachePool", "SparePool"]


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

    def __post_init__(self) -> None:
        if not isinstance(self.disks, t.Iterable):
            raise TypeError(f"A {self.__class__.__name__} must have an iterable as the disks argument.")

        self.disks = list(self.disks)

    def __eq__(self, __o: object) -> bool:
        if isinstance(__o, dict):
            try:
                __o = Vdev.from_dict(__o)

            except:  # pylint: disable=bare-except
                return False

        if isinstance(__o, (list, set, tuple)):
            __o = Vdev(disks=list(__o))

        if not isinstance(__o, type(self)):
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

    @classmethod
    def from_dict(cls, data: _VdevHint) -> "Vdev":
        return cls(type=data.get("type"), disks=data.get("disks", []))  # type: ignore[arg-type]


@dataclasses.dataclass
class _Pool:
    name: str = dataclasses.field(default="", init=False)
    redundancy: bool = dataclasses.field(default=False, init=False)
    vdevs: list[Vdev] = dataclasses.field(default_factory=list)
    _default_vdev_: t.Optional[str] = dataclasses.field(default=None, init=False)

    @classmethod
    def _check_redundancy(cls, *items: Vdev) -> None:
        if not cls.redundancy and any(item.type for item in items):
            raise ValueError(f"Non-redundant pools (i.e., class: {cls.__name__}) cannot have a type argument.")

    def __post_init__(self) -> None:
        for vdev in self.vdevs:
            if not isinstance(vdev, Vdev):
                raise TypeError(
                    f"A {self.__class__.__name__} cannot be initialized with non-Vdevs. "
                    "Use .from_dict() to create from a container."
                )
            self._check_redundancy(vdev)

            if vdev.type is None:
                vdev.type = self._default_vdev_

    def __eq__(self, __o: object) -> bool:
        if isinstance(__o, dict):
            try:
                __o = self.from_dict(__o)

            except:  # pylint: disable=bare-except
                return False

        if isinstance(__o, (list, tuple)):
            __o = self.from_dict({self.name: list(__o)})

        if not isinstance(__o, type(self)):
            return False

        if set(self.vdevs) != set(__o.vdevs):
            return False

        return True

    def __contains__(self, element: Vdev) -> bool:
        return element in self.vdevs

    def __bool__(self) -> bool:
        return any(bool(vdev) for vdev in self.vdevs)

    def __sub__(self, other: "_Pool") -> set[Vdev]:
        if not isinstance(other, type(self)):
            raise ValueError("Diffing of different pool types is not supported.")

        return set(self.vdevs).difference(other.vdevs)

    def difference(self, other: "_Pool") -> set[Vdev]:
        return self - other

    def __xor__(self, other: "_Pool") -> set[Vdev]:
        return (self - _Pool()).union(other - _Pool())

    def symmetric_difference(self, other: "_Pool") -> set[Vdev]:
        return self ^ other

    @property
    def devices(self) -> set[str]:
        return {disk for vdev in self.vdevs for disk in vdev.disks}

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
        return {self.name: [vdev.dump() for vdev in self.vdevs if vdev]}

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

    @classmethod
    def from_dict(cls, data: _PoolHint) -> _PoolsHint:
        if len(keys := list(data.items())) > 1:
            raise TypeError(f"Could not create a {cls.__name__} from this input data: There were too many pools.")

        if len(keys) == 0:
            raise TypeError(f"Could not create a {cls.__name__} from this input data: The input data has no pools.")

        [[_type, disks]] = keys

        return _find_pool(_type)([Vdev.from_dict(disk) for disk in disks])


@dataclasses.dataclass(eq=False)
class _Redundant(_Pool):
    redundancy: bool = dataclasses.field(default=True, init=False)
    _default_vdev_: str = dataclasses.field(default="stripe", init=False)

    def new(self, _type: t.Optional[str] = None) -> Vdev:
        if _type is None:
            _type = _Redundant._default_vdev_

        return super().new(_type)

    def append(self, *items: Vdev) -> None:
        self._append(*items)


@dataclasses.dataclass(eq=False)
class StoragePool(_Redundant):
    name: str = dataclasses.field(default="storage", init=False)

    @property
    def create(self) -> list[str]:
        return []


@dataclasses.dataclass(eq=False)
class LogPool(_Redundant):
    name: str = dataclasses.field(default="logs", init=False)

    @property
    def create(self) -> list[str]:
        return ["log"]


@dataclasses.dataclass(eq=False)
class CachePool(_Pool):
    name: str = dataclasses.field(default="cache", init=False)


@dataclasses.dataclass(eq=False)
class SparePool(_Pool):
    name: str = dataclasses.field(default="spare", init=False)


def _find_pool(_type: str) -> type[_PoolsHint]:
    try:
        return t.cast(
            type[_PoolsHint], {"storage": StoragePool, "logs": LogPool, "cache": CachePool, "spare": SparePool}[_type]
        )

    except KeyError as exception:
        raise AttributeError("Could not find the requested pool type in the module.") from exception


@dataclasses.dataclass
class Option:
    property: str
    value: str
    source: str = "-"

    @classmethod
    def from_string(cls, console: str) -> dict[str, "Option"]:
        pattern = re.compile(r"(?P<name>\S+)\t(?P<property>\S+)\t(?P<value>\S+)\t(?P<source>\S+)")

        result: dict[str, Option] = {}

        for _, _property, *data in pattern.findall(console):
            result[_property] = Option(_property, *data)

        return result

    @classmethod
    def from_dict(cls, data: _OptionHint) -> "Option":
        if "property" in data.keys():
            option = cls(**data)

        else:
            [(_property, value)] = data.items()
            option = cls(_property, value)

        return option

    def __eq__(self, __o: object) -> bool:
        if isinstance(__o, dict):
            try:
                __o = self.from_dict(__o)

            except:  # pylint: disable=bare-except
                return False

        if not isinstance(__o, type(self)):
            return False

        return self.property == __o.property and self.value == __o.value

    def dump(self) -> _OptionHint:
        return dataclasses.asdict(self)

    def create(self) -> list[str]:
        return ["-o", f"{self.property}={self.value}"]


@dataclasses.dataclass
class Zpool:
    name: str
    storage: StoragePool = dataclasses.field(default_factory=StoragePool)
    logs: LogPool = dataclasses.field(default_factory=LogPool)
    cache: CachePool = dataclasses.field(default_factory=CachePool)
    spare: SparePool = dataclasses.field(default_factory=SparePool)
    options: dict[str, Option] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        self._sanitize()

    def __bool__(self) -> bool:
        return any(bool(p) for p in self.pools)

    def __iter__(self) -> t.Iterator[tuple[str, _Pool]]:
        yield from zip(self.names, self.pools)

    def _sanitize(self) -> None:
        for pool in self.pools:
            pool.vdevs = [vdev for vdev in pool.vdevs if vdev]

    def __eq__(self, __o: object) -> bool:
        if isinstance(__o, dict):
            try:
                __o = self.from_dict(__o)

            except:  # pylint: disable=bare-except
                return False

        elif isinstance(__o, str):
            try:
                __o = self.from_string(__o)

            except:  # pylint: disable=bare-except
                return False

        if not isinstance(__o, type(self)):
            return False

        if self.name != __o.name:
            return False

        for name in self.names:
            if self.get_pool(name) != __o.get_pool(name):
                return False

        return True

    @property
    def devices(self) -> set[str]:
        return {disk for pool in self.pools for disk in pool.devices}

    def get_pool(self, name: str) -> _PoolsHint:
        return t.cast(_PoolsHint, getattr(self, name))

    @property
    def pools(self) -> t.Iterator[_Pool]:
        yield from map(self.get_pool, self.names)

    @property
    def names(self) -> t.Iterator[str]:
        yield from (field.name for field in dataclasses.fields(self) if issubclass(field.type, _Pool))

    def dump(self) -> _ZpoolHint:
        data: _ZpoolHint = {"name": self.name}

        for pool_type in self.names:
            if pool := self.get_pool(pool_type):
                data[pool_type] = pool.dump()[pool_type]

        if self.options:
            options: list[dict[str, str]] = []

            for option in self.options.values():
                options.append(option.dump())

            data["options"] = options

        return data

    @classmethod
    def from_string(cls, console: str, options: str = "") -> "Zpool":  #  pylint: disable=too-many-locals
        if search := re.search(r"cannot open '(.*?)': no such pool", console):
            raise ValueError(f"There was no pool found with the name {search.group(1)}.")

        lines = console.strip().splitlines()
        name = _match(lines.pop(0), r"^(?P<name>.+?)\s\d").get("name")

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

        zpool._sanitize()
        zpool.options = Option.from_string(options)
        return zpool

    @classmethod
    def from_dict(cls, data: _ZpoolHint) -> "Zpool":
        zpool = cls(t.cast(str, data["name"]))

        for key in zpool.names:
            for vdev in t.cast(list[_VdevHint], data.get(key, {})):
                _vdev = zpool.get_pool(key).new(t.cast(t.Optional[str], vdev.get("type")))
                _vdev.append(*vdev.get("disks", []))

        for option in t.cast(list[_OptionHint], data.get("options", [])):
            _option = Option.from_dict(option)
            zpool.options[_option.property] = _option

        zpool._sanitize()
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

        for option in self.options.values():
            cmd.extend(option.create())

        return cmd

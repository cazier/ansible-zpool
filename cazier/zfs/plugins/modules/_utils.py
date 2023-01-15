import re
import typing as t
import itertools
import dataclasses

_VdevHint = dict[str, str | list[str]]
_PoolHint = list[_VdevHint]


def _pairs(iterable: t.Iterable[str]) -> t.Iterator[tuple[str, str]]:
    """Recipe to get overlapping pairs of items from an iterable: (ABCD) -> AB, BC, CD

    Args:
        iterable (t.Iterable[str]): iterable of values

    Yields:
        tuple[str, str]: pairwise elements from the iterable
    """
    for first, second in zip(*[iter(iterable)] * 2, strict=True):
        yield first, second


def _match(line: str, pattern: str, flags: int = 0) -> tuple[t.Optional[str], ...]:
    """Helper function to try to match a pattern, or return ``None`` if no match is found

    Args:
        line (str): input string
        pattern (str): regular expression pattern
        flags (int): regex flags

    Returns:
        t.Optional[str]: the matched string content, or None, if no match was found
    """
    if match := re.match(pattern, line, flags=flags):
        return match.groups()

    return (None,)


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
        r"""^                         # Start of the line
            \t                        # Leading tab (indentation)
            (\/)                      # Capture only strings starting with a slash
            (?:dev\/disk\/by-\w+\/)?  # Optional /dev/disk (ignoring /by-*/)
            (.*?)                     # Capture for disk or raw image name
            (?:-part(\d+)|)           # Capture a partition number, if it exists. Otherwise ""
            \t                        # Tab signifying the end of the name
            [\d-]                     # Disk usage numbers
            """,
        flags=re.VERBOSE,
    )

    if not match[0]:
        return None

    prefix, disk, part = match

    if part and int(part) != 1:
        raise TypeError("Only using whole disk (or sparse images) is supported at this time.")

    if not part:
        disk = f"{prefix}{disk}"

    return disk


def _get_type(line: str) -> t.Optional[str]:
    """Attempts to match a zpool list line for the vdev type (raidz1, mirror, etc.)

    Args:
        line (str): zpool list line

    Returns:
        t.Optional[str]: The vdev type
    """
    return _match(line, r"\t(raidz(?:1|2|3)|mirror)-\d+\t\d")[0]


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
        return hash((self.type, *set(self.disks)))

    def __bool__(self) -> bool:
        return len(self.disks) > 0

    def append(self, item: str) -> None:
        self.disks.append(item)

    def clear(self) -> None:
        self.disks.clear()

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
    name: str
    vdevs: list[Vdev] = dataclasses.field(default_factory=list)

    def __eq__(self, __o: object) -> bool:
        if not isinstance(__o, self.__class__):
            return False

        if set(self.vdevs) != set(__o.vdevs):
            return False

        return True

    def __bool__(self) -> bool:
        return any(bool(vdev) for vdev in self.vdevs)

    def append(self, item: Vdev) -> None:
        self.vdevs.append(item)

    def new(self) -> Vdev:
        self.append((vdev := Vdev()))

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
class StoragePool(_Pool):
    name: str = "storage"
    redundancy: bool = True

    @property
    def create(self) -> list[str]:
        return []


@dataclasses.dataclass
class LogPool(_Pool):
    name: str = "logs"
    redundancy: bool = True

    @property
    def create(self) -> list[str]:
        return ["log"]


@dataclasses.dataclass
class CachePool(_Pool):
    name: str = "cache"
    redundancy: bool = False


@dataclasses.dataclass
class SparePool(_Pool):
    name: str = "spare"
    redundancy: bool = False


@dataclasses.dataclass()
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
        [name] = _match(lines.pop(0), r"(.+?)\s\d")

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
                    if vdev:
                        if not vdev.type and pool.redundancy:
                            vdev.type = "stripe"

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

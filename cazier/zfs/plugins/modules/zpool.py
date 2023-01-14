import re
import typing as t
import itertools
import collections

Storage = dict[str, list[str] | str]
ZType = dict[str, Storage]


def get_zpool_data(console: str) -> ZType:
    def pairs(iterable: t.Iterable[str]) -> t.Iterator[tuple[str, str]]:
        """Recipe to get overlapping pairs of items from an iterable: (ABCD) -> AB, BC, CD

        Args:
            iterable (t.Iterable[str]): iterable of values

        Yields:
            tuple[str, str]: pairwise elements from the iterable
        """
        for first, second in zip(*[iter(iterable)] * 2, strict=True):
            yield first, second

    def _match(line: str, pattern: str) -> tuple[t.Optional[str], ...]:
        """Helper function to try to match a pattern, or return ``None`` if no match is found

        Args:
            line (str): input string
            pattern (str): regular expression pattern

        Returns:
            t.Optional[str]: the matched string content, or None, if no match was found
        """
        if _match := re.match(pattern, line):
            return _match.groups()

        return (None,)

    def _get_disk(line: str) -> t.Optional[str]:
        """Attempts to match a zpool list line for a drive/disk. This looks for an indentation along
        with a leading `/` (slash).

        Args:
            line (str): zpool list line

        Raises:
            TypeError: When a disk is used, without it being the entire disk (i.e., one partition
                not numbered `1`) an exception is raised.

        Returns:
            t.Optional[str]: The final component of the disk name
        """
        disk, *part = _match(line, r"\t(?:\/.+)+\/(.*?)(?:-part(\d+)|)\t[\d-]")

        if part and part != [None] and int(t.cast(str, part[0])) != 1:
            raise TypeError("Only using whole disk (or sparse images) is supported at this time.")

        return disk

    def _get_type(line: str) -> t.Optional[str]:
        """Attempts to match a zpool list line for the vdev type (raidz1, mirror, etc.)

        Args:
            line (str): zpool list line

        Returns:
            t.Optional[str]: The vdev type
        """
        return _match(line, r"\t(raidz(?:1|2|3)|mirror)-\d+\t\d")[0]

    zpool: dict[str, str | list[Storage]] = collections.defaultdict(list)
    storage: Storage = collections.defaultdict(list)

    lines = console.strip().splitlines()
    zpool["name"] = t.cast(str, _match(lines.pop(0), r"(.+?)\s\d")[0])

    sections: dict[str, str] = {
        k.strip(): v
        for k, v in pairs(["storage"] + re.split(r"^(logs|cache|spare).*$", "\n".join(lines), flags=re.MULTILINE))
    }

    for key in ("storage", "logs", "cache", "spare"):
        storage.clear()

        if key == "storage":
            section = sections["storage"]

        else:
            section = sections.get(key, "")

        for current, future in itertools.pairwise(section.splitlines() + ["<terminator>"]):
            if current in ("<terminator>", ""):
                continue

            if disk := _get_disk(current):
                storage["disks"].append(disk)  # type: ignore[union-attr]

            elif _type := _get_type(current):
                storage["type"] = _type

            else:
                raise TypeError("Couldn't parse the zpool list data properly.")

            if (_type := _get_type(future)) or future == "<terminator>":
                if storage:
                    if not storage.get("type") and key not in ("spare", "cache"):
                        storage["type"] = "stripe"

                    zpool[key].append(dict(storage))  # type: ignore[union-attr]

                    storage.clear()

    return dict(zpool)  # type: ignore[arg-type]

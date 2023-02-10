# pylint: disable=invalid-name,wildcard-import,protected-access,unused-argument

import os
import typing as t
import pathlib as p
import tempfile
import subprocess
import dataclasses

import yaml
import paramiko
from ward import Scope, test, fixture

from cazier.zfs.plugins.filter.zfs import FilterModule
from cazier.zfs.plugins.module_utils.utils import Option

try:
    import dotenv

    dotenv.load_dotenv()

except ImportError:
    pass

client = paramiko.SSHClient()


@fixture(scope=Scope.Global)  # type: ignore[misc]
def target() -> t.Iterator[dict[str, t.Any]]:
    # These are all loaded from the .env file using the dotenv package.
    host = os.getenv("ANSIBLE_WARD_HOST", "localhost")
    user = os.getenv("ANSIBLE_WARD_USER", "root")
    password = os.getenv("ANSIBLE_WARD_PASS")
    connection = os.getenv("ANSIBLE_WARD_CONNECTION", "local")

    system = {"ansible_host": host, "ansible_user": user, "ansible_connection": connection}

    if password:
        system["ansible_password"] = password

    inventory = {"all": {"children": {"test_device": {"hosts": {"system": system}}}}}

    if os.getenv("GITHUB_ACTIONS"):
        for file in range(1, 21):
            _execu(["truncate", "-s", "93M", str(p.Path("/tmp", f"{file:02d}.raw"))], check=True)

        yield inventory
        return

    client.set_missing_host_key_policy(paramiko.AutoAddPolicy)
    client.connect(host, username=user, password=password)

    _execu(["cd /tmp; for n in {01..20}; do truncate -s 93M $n.raw; done"], check=True)

    yield inventory

    _execu(["rm -f /tmp/*.raw"], check=True)


@fixture(scope=Scope.Module)  # type: ignore[misc]
def ansibledir(inventory: dict[str, t.Any] = target) -> t.Iterator[p.Path]:
    with tempfile.TemporaryDirectory() as tmpdir:
        directory = p.Path(tmpdir)
        collections = directory.joinpath("collections/ansible_collections")

        collections.mkdir(parents=True, exist_ok=True)
        collections.joinpath("cazier").symlink_to(p.Path("cazier").absolute(), target_is_directory=True)

        directory.joinpath("inventory.yaml").write_text(yaml.dump(inventory), encoding="utf8")

        conf = f"[defaults]\ninventory = inventory.yaml\ncollections_paths = {collections.parent}"

        config = directory.joinpath("ansible.cfg")
        config.write_text(conf, encoding="utf8")

        os.environ["ANSIBLE_CONFIG"] = str(config)

        yield directory


@fixture(scope=Scope.Module)  # type: ignore[misc]
def test_data() -> dict[str, t.Any]:
    inputs = p.Path(__file__).parent.joinpath("config", "integration.yaml").read_text(encoding="utf8")

    return t.cast(dict[str, t.Any], yaml.safe_load(inputs))


@fixture(scope=Scope.Test)  # type: ignore[misc]
def cleanup() -> t.Iterator[None]:
    yield

    _execu(["zpool", "destroy", "test"], check=False)


@dataclasses.dataclass
class Command:
    stdout: t.Optional[str]
    stderr: t.Optional[str]
    returncode: int


def _execu(command: list[str], check: bool = True, cwd: t.Optional[p.Path] = None, local: bool = False) -> Command:
    if os.getenv("GITHUB_ACTIONS") or local:
        process = subprocess.run(args=command, encoding="utf8", check=check, capture_output=True, cwd=cwd)
        return Command(process.stdout, process.stderr, process.returncode)

    if cwd:
        command = [f"cd {cwd};"] + command

    _, stdout, stderr = client.exec_command(" ".join(command))

    out = stdout.read().decode("utf8").strip() or None
    err = stderr.read().decode("utf8").strip() or None
    rc = 1 if err else 0

    if check and rc != 0:
        raise subprocess.CalledProcessError(rc, command, out, err)

    return Command(out, err, rc)


def _exists(name: str) -> bool:
    out = _execu(["zpool", "list", name], check=False)

    return out.returncode == 0 and (out.stderr is None or "no such pool" not in out.stderr)


def _get_zpool_options(name: str) -> dict[str, Option]:
    out = _execu(["zpool", "get", "-Hp", "-o", "all", "all", name], check=False)

    if out.returncode != 0 or out.stdout is None:
        return {}

    return Option.from_string(out.stdout)


def _get_zfs_options(name: str) -> dict[str, Option]:
    out = _execu(["zfs", "get", "-Hp", "-o", "all", "all", name], check=False)

    if out.returncode != 0 or out.stdout is None:
        return {}

    return Option.from_string(out.stdout)


def _ansible(data: dict[str, t.Any], ansible: p.Path) -> None:
    result = data["result"]

    playbook = ansible.joinpath("test_playbook.yaml")
    playbook.write_text(yaml.dump(data["playbook"]), encoding="utf8")

    out = _execu(["ansible-playbook", str(playbook), "-l", "test_device"], check=False, cwd=ansible, local=True)

    if result["failure"]:
        assert out.returncode != 0

        if msg := result.get("message"):
            assert out.stdout and msg in out.stdout

    else:
        print(out.stdout)
        assert out.returncode == 0
        assert out.stdout and "changed=0" not in out.stdout

    assert result["exists"] == _exists("test")


def _options(data: list[dict[str, t.Any]]) -> None:
    opts = _get_zpool_options("test")

    for option in map(Option.from_dict, data):
        assert option == opts[option.property]


def _snapshot_filter(data: list[str]) -> None:
    opts = _get_zfs_options("test/test")

    for name, enabled in FilterModule().snapshot(data).items():
        assert opts[name].value == "on" if enabled else "off"


for feature in ("present/absent", "options", "filters"):
    for item in test_data()[feature]:

        @test("integration: {feat}: {name}", tags=["ansible"])  # type: ignore[misc]
        def _(
            ansible: p.Path = ansibledir,
            data: dict[str, dict[str, t.Any]] = item,
            feat: str = feature,
            name: str = item["name"],
            _: None = cleanup,
        ) -> None:
            _ansible(data, ansible)

            if "options" in data["result"].keys():
                _options(data["result"]["options"])

            for kind, values in data["result"].get("filters", {}).items():
                if kind == "snapshots":
                    _snapshot_filter(values)

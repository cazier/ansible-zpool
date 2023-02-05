# pylint: disable=invalid-name,wildcard-import,protected-access,unused-argument

import os
import typing as t
import pathlib as p
import tempfile
import subprocess

import yaml
from ward import Scope, test, fixture

from cazier.zfs.plugins.module_utils.utils import Option


@fixture(scope=Scope.Module)  # type: ignore[misc]
def rootdir() -> t.Iterator[p.Path]:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = p.Path(tmpdir)

        for file in range(1, 21):
            sparse = path.joinpath(f"{file:02d}.raw")
            subprocess.run(["/usr/bin/truncate", "-s", "9300G", str(sparse)], check=True)

        yield path


@fixture(scope=Scope.Module)  # type: ignore[misc]
def ansibledir() -> t.Iterator[p.Path]:
    with tempfile.TemporaryDirectory() as tmpdir:
        directory = p.Path(tmpdir)
        collections = directory.joinpath("collections/ansible_collections")

        collections.mkdir(parents=True, exist_ok=True)
        collections.joinpath("cazier").symlink_to(p.Path("cazier").absolute(), target_is_directory=True)

        directory.joinpath("inventory.cfg").write_text("[test_device]\nlocalhost\n", encoding="utf8")

        conf = f"[defaults]\ninventory = inventory.cfg\ncollections_paths = {collections.parent}"

        config = directory.joinpath("ansible.cfg")
        config.write_text(conf, encoding="utf8")

        os.environ["ANSIBLE_CONFIG"] = str(config)

        yield directory


@fixture(scope=Scope.Module)  # type: ignore[misc]
def test_data() -> dict[str, t.Any]:
    inputs = p.Path(__file__).parent.joinpath("config", "integration.yaml").read_text(encoding="utf8")

    return t.cast(dict[str, t.Any], yaml.safe_load(inputs)["integration"])


def _exists(name: str) -> bool:
    out = subprocess.run(["zpool", "list", name], check=False)

    return out.returncode == 0 and (out.stderr is None or "no such pool" not in out.stderr.decode(encoding="utf8"))


def _options(name: str) -> dict[str, Option]:
    out = subprocess.run(["zpool", "get", "-Hp", "-o", "'all'", "'all'", name], check=False)

    if out.returncode != 0:
        return {}

    return Option.from_string(out.stdout.decode("utf8"))


for item in test_data():

    @test("integration: {name}", tags=["ansible"])  # type: ignore[misc]
    def _(sparse: p.Path = rootdir, ansible: p.Path = ansibledir, data: t.Any = item, name: str = item["name"]) -> None:
        tasks = data["tasks"]
        result = data["result"]
        pool = data["pool_name"]

        playbook = ansible.joinpath("test_playbook.yaml")
        playbook.write_text(yaml.dump(tasks).replace("<__PATH__>", str(sparse)), encoding="utf8")

        out = subprocess.run(
            ["ansible-playbook", str(playbook), "-l", "test_device", "-v", "-c", "local", "-vvv"],
            capture_output=True,
            check=False,
            cwd=ansible,
        )

        if result["failure"]:
            assert out.returncode != 0

            if msg := result.get("message"):
                assert out.stdout and msg in out.stdout.decode("utf8")

        else:
            assert out.returncode == 0

        assert result["exists"] == _exists(pool)

        if options := data.get("options"):
            for key, value in options.items():
                assert _options(pool)[key] == value

# pylint: disable=invalid-name,wildcard-import,protected-access,unused-argument

import os
import typing as t
import pathlib
import tempfile
import subprocess

import yaml
from ward import Scope, test, fixture


@fixture(scope=Scope.Module)  # type: ignore[misc]
def rootdir() -> t.Iterator[pathlib.Path]:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = pathlib.Path(tmpdir)

        for file in range(1, 21):
            sparse = path.joinpath(f"{file:02d}.raw")
            subprocess.run(["/usr/bin/truncate", "-s", "9300G", str(sparse)], check=True)

        yield path


@fixture(scope=Scope.Module)  # type: ignore[misc]
def ansibledir() -> t.Iterator[pathlib.Path]:
    with tempfile.TemporaryDirectory() as tmpdir:
        directory = pathlib.Path(tmpdir)
        collections = directory.joinpath("collections/ansible_collections")

        collections.mkdir(parents=True, exist_ok=True)
        collections.joinpath("cazier").symlink_to(pathlib.Path("cazier").absolute(), target_is_directory=True)

        directory.joinpath("inventory.cfg").write_text("[test_device]\nlocalhost\n", encoding="utf8")

        conf = f"[defaults]\ninventory = inventory.cfg\ncollections_paths = {collections.parent}"

        config = directory.joinpath("ansible.cfg")
        config.write_text(conf, encoding="utf8")

        os.environ["ANSIBLE_CONFIG"] = str(config)

        yield directory


@fixture(scope=Scope.Module)  # type: ignore[misc]
def test_data() -> dict[str, t.Any]:
    inputs = pathlib.Path(__file__).parent.joinpath("config", "integration.yaml").read_text(encoding="utf8")

    return t.cast(dict[str, t.Any], yaml.safe_load(inputs)["integration"])


def _exists(name: str) -> bool:
    out = subprocess.run(["zpool", "list", name], check=False)

    return out.returncode == 0 and (out.stderr is None or "no such pool" not in out.stderr.decode(encoding="utf8"))


for item in test_data():

    @test("integration", tags=["ansible"])  # type: ignore[misc]
    def _(
        sparse_files: pathlib.Path = rootdir,
        ansible: pathlib.Path = ansibledir,
        data: t.Any = item,
        name: str = item["name"],
    ) -> None:
        inputs = data["inputs"]
        result = data["result"]

        playbook = ansible.joinpath("test_playbook.yaml")
        playbook.write_text(yaml.dump(inputs).replace("<__PATH__>", str(sparse_files)), encoding="utf8")

        out = subprocess.run(
            ["ansible-playbook", str(playbook), "-l", "test_device", "-v", "-c", "local"],
            capture_output=True,
            check=False,
            cwd=ansible,
        )

        if out.returncode != 0:
            if out.stdout:
                print('=' * 80, 'stdout')
                print(out.stdout.decode('utf8'))
            
            if out.stderr:
                print('=' * 80, 'stderr')
                print(out.stderr.decode('utf8'))
            
            assert False

        assert result["exists"] and _exists("test")

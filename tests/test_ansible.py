# pylint: disable=invalid-name,wildcard-import,protected-access,unused-argument

import os
import typing as t
import pathlib
import tempfile
import subprocess

import yaml
from ward import Scope, test, fixture

from tests.conftest import test_data

STEPS = yaml.safe_load(
    """
- name: test my new module
  hosts: all
  tasks:
  - name: run the new module
    become: true
    cazier.zfs.zpool:
      name: test
      zpool:
        storage:
        - disks:
          - /tmp/01.raw
          - /tmp/02.raw
          - /tmp/03.raw
          type: raidz1
        - disks:
          - /tmp/04.raw
          - /tmp/05.raw
          - /tmp/06.raw
          type: raidz1
      state: absent
      force: true
    register: testout
"""
)


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

        conf = f"[defaults]\ninventory = inventory.cfg\nremote_user = root\ncollections_paths = {collections.parent}"

        config = directory.joinpath("ansible.cfg")
        config.write_text(conf, encoding="utf8")

        os.environ["ANSIBLE_CONFIG"] = str(config)

        yield directory


for item in test_data()("integration")[:1]:

    @test("integration", tags=["ansible"])  # type: ignore[misc]
    def _(
        root: pathlib.Path = rootdir, ansible: pathlib.Path = ansibledir, data: t.Any = item, name: str = item["name"]
    ) -> None:
        inputs = data["inputs"]
        result = data["result"]

        playbook = ansible.joinpath("test_playbook.yaml")
        playbook.write_text(yaml.dump(STEPS), encoding="utf8")

        out = subprocess.run(["ansible-playbook", str(playbook), "-l", "test_device", "-v"], cwd=ansible)
        print(out.stdout or out.stderr)
        assert out.stdout.decode("utf8") == ""

import re
import typing as t

try:
    from cazier.zfs.plugins.module_utils import utils

except ImportError:
    if not t.TYPE_CHECKING:
        from ansible_collections.cazier.zfs.plugins.module_utils import utils

from ansible.module_utils.basic import AnsibleModule  # type: ignore[import]

SUPPORTED_ZFS_VERSION = "2.1.4"

DOCUMENTATION = """
---
module: zpool
short_description: Manage zpools
description:
  - Manages ZFS zpools, in a primarily dangerous and/or destructive manner...
options:
  name:
    description:
      - The name of the generated zpool e.g. C(storage_pool).
    required: true
    type: str
  state:
    description:
      - Whether to create (C(present)), or destroy (C(absent)) a zpool.
    choices: [ absent, present ]
    required: true
    type: str
  zpool:
    description:
      - Zpool pool details for the new device
  force:
    description:
      - Allows the destruction of a zpool. Use caution as this is a destructive process.
    type: bool
author:
- Brendan Cazier
"""


class Zpool:
    _remote: t.Optional[utils.Zpool] = None

    def __init__(self, module: AnsibleModule) -> None:
        self.module = module

        self.check = self.module.check_mode
        self.name = self.module.params["name"]

        self.force = self.module.params.get("force", False) and self.module.params.get("absolutely_force", False)

        self.desired = utils.Zpool.from_dict({**self.module.params["zpool"], "name": self.name})

        self._binary = self.module.get_bin_path("zpool", required=True)
        self._check_package()

    def _run_command(self, command: list[str], *args: t.Any, **kwargs: t.Any) -> tuple[int, str, str]:
        if command[0] != self._binary:
            command = [self._binary] + command

        if "check_rc" not in kwargs:
            kwargs["check_rc"] = True

        rc, stdout, stderr = self.module.run_command(command, *args, **kwargs)  # pylint: disable=invalid-name

        if kwargs["check_rc"] and (rc != 0 or stderr):
            self.module.fail_json(msg=f"An error occurred while running the zpool bin: `{stderr}`")

        elif stderr and not stdout:
            stdout, stderr = stderr, stdout

        return rc, stdout, stderr

    def _check_package(self) -> None:
        _, stdout, _ = self._run_command([self._binary, "--version"])

        if not re.search(rf"zfs-(?:kmod-)?{SUPPORTED_ZFS_VERSION}", stdout):
            self.module.fail_json(
                msg=f"This collection only supports zfs v.{SUPPORTED_ZFS_VERSION}, but only found: {stdout}"
            )

    def _list(self, name: str, check_rc: bool = True) -> str:
        _, stdout, _ = self._run_command([self._binary, "list", "-vPH", "-o", "name,size", name], check_rc=check_rc)

        return stdout

    @property
    def remote(self) -> t.Optional[utils.Zpool]:
        if not self._remote:
            try:
                self._remote = utils.Zpool.from_string(self._list(self.name, check_rc=False))

            except ValueError:
                return None

        return self._remote

    @property
    def goal(self) -> utils.Zpool:
        return utils.Zpool.from_string(self._list(self.name))

    def exists(self) -> bool:
        return self.remote is not None

    def create(self) -> None:
        self._run_command([self._binary, "create"] + self.desired.create_command())

    def destroy(self) -> None:
        self._run_command([self._binary, "destroy", self.name])


def main() -> None:
    module = AnsibleModule(
        argument_spec=dict(
            name=dict(type="str", required=True),
            zpool=dict(
                type="dict",
                required=True,
                options=dict(
                    storage=dict(type="list", required=True),
                    logs=dict(type="list", required=False, default=[]),
                    cache=dict(type="list", required=False, default=[]),
                    spare=dict(type="list", required=False, default=[]),
                    options=dict(type="list", required=False, default=[]),
                ),
            ),
            state=dict(type="str", default="present", choices=["absent", "present"]),
            force=dict(type="bool", default=False),
        ),
        supports_check_mode=True,
    )

    zpool = Zpool(module)

    result = {"name": module.params["name"], "state": module.params["state"]}

    if module.params["state"] == "present":
        if zpool.remote:
            if zpool.desired == zpool.remote:
                result["changed"] = False

            else:
                module.fail_json(f"The zpool {zpool.name} on the target host does not match the input parameters")

        else:
            zpool.create()
            result["changed"] = True

    else:
        if zpool.remote:
            if module.params.get("force", False):
                zpool.destroy()
                result["changed"] = True

            else:
                module.fail_json(f"The zpool {zpool.name} exists, but cannot be destroyed without the `force` flag")

    module.exit_json(**result)


if __name__ == "__main__":
    main()

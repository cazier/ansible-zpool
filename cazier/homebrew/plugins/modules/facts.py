import re
import pathlib

from ansible.module_utils.basic import AnsibleModule  # type: ignore[import]


def main() -> None:
    module = AnsibleModule(argument_spec={}, supports_check_mode=True)

    ansible_facts: dict[str, str | bool] = {"changed": False}

    path = module.get_bin_path(
        "zpool",
        opt_dirs=[
            "/opt/homebrew/bin",  # ARM macOS
            "/usr/local/bin",  # Intel macOS
            "/home/linuxbrew/.linuxbrew/bin",  # Linuxbrew
        ],
    )

    if not path:
        ansible_facts["homebrew_installed"] = False
        module.exit_json(**ansible_facts)

    ansible_facts["homebrew_installed"] = True
    ansible_facts["homebrew_prefix"] = str(pathlib.Path(path).parents[1])

    rc, stdout, stderr = module.run_command([path, "--version"])  # pylint: disable=invalid-name

    if rc != 0:
        module.fail_json(msg=f"An error occurred executing the brew binary: `{stderr}`")

    match = re.match(r"^Homebrew (?P<homebrew_version>.*)\n.*", stdout)

    if not match:
        module.fail_json(msg=f"Could not determine the brew version. Output: `{stdout}")
        return

    ansible_facts.update(match.groupdict())

    module.exit_json(**ansible_facts)


if __name__ == "__main__":
    main()

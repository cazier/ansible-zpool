import re
import pathlib

from ansible.module_utils.basic import AnsibleModule  # type: ignore[import]


def main() -> None:
    module = AnsibleModule(argument_spec={}, supports_check_mode=True)

    facts: dict[str, str | bool] = {"changed": False}

    path = module.get_bin_path(
        "brew",
        opt_dirs=[
            "/opt/homebrew/bin",  # ARM macOS
            "/usr/local/bin",  # Intel macOS
            "/home/linuxbrew/.linuxbrew/bin",  # Linuxbrew
        ],
    )

    if not path:
        facts["homebrew_installed"] = False
        module.exit_json(ansible_facts=facts, changed=False)

    facts["homebrew_installed"] = True
    facts["homebrew_prefix"] = str(pathlib.Path(path).parents[1])

    rc, stdout, stderr = module.run_command([path, "--version"])  # pylint: disable=invalid-name

    if rc != 0:
        module.fail_json(msg=f"An error occurred executing the brew binary: `{stderr}`")

    match = re.match(r"^Homebrew (?P<homebrew_version>.*)\n.*", stdout)

    if not match:
        module.fail_json(msg=f"Could not determine the brew version. Output: `{stdout}")
        return

    facts.update(match.groupdict())

    module.exit_json(ansible_facts=facts, changed=False)


if __name__ == "__main__":
    main()

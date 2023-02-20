import re
import pathlib

from ansible.module_utils.basic import AnsibleModule  # type: ignore[import]

SHELL_PROFILES = {"zsh": ".zshrc", "bash": ".bashrc"}


def homebrew(module: AnsibleModule) -> dict[str, str | bool]:
    facts: dict[str, str | bool] = {"success": True}

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
        return facts

    facts["homebrew_installed"] = True
    facts["homebrew_prefix"] = str(pathlib.Path(path).parents[1])

    rc, stdout, stderr = module.run_command([path, "--version"])  # pylint: disable=invalid-name

    if rc != 0:
        facts.update(success=False, msg=f"An error occurred executing the brew binary: `{stderr}`")
        return facts

    match = re.match(r"^Homebrew (?P<homebrew_version>.*?\d+) .*?\n.*", stdout)

    if not match:
        facts.update(success=False, msg=f"Could not determine the brew version. Output: `{stdout}")
        return facts

    facts.update(match.groupdict())

    return facts


def shells() -> dict[str, bool | dict[str, dict[str, str]]]:
    try:
        import pwd  # pylint: disable=import-outside-toplevel

    except ImportError:
        return {"success": True}

    facts: dict[str, dict[str, dict[str, str]]] = {"user_shells": {}}

    for struct in pwd.getpwall():
        if struct.pw_name.startswith("_"):
            continue

        facts["user_shells"][struct.pw_name] = {
            "home": struct.pw_dir,
            "shell": struct.pw_shell,
            "profile": SHELL_PROFILES.get(struct.pw_shell.split("/")[-1], ""),
        }

    return {"success": True, **facts}


def main() -> None:
    module = AnsibleModule(argument_spec={}, supports_check_mode=True)

    union: dict[str, str | bool | dict[str, dict[str, str]]] = {}

    if not (homebrew_facts := homebrew(module)).pop("success"):
        module.fail_json(msg=homebrew_facts.pop("msg"))

    union.update(homebrew_facts)

    if not (shell_facts := shells()).pop("success"):
        module.fail_json(msg=shell_facts.pop("msg"))

    union.update(shell_facts)

    module.exit_json(ansible_facts=union, changed=False)


if __name__ == "__main__":
    main()

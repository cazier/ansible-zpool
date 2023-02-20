import typing as t
import pathlib


class FilterModule:
    def filters(self) -> dict[str, t.Any]:
        return {
            "users_profile": self.users_profile,
            "users_shell": self.users_shell,
            "users_home": self.users_home,
            "users_uid": self.users_uid,
            "users_gid": self.users_gid,
        }

    def users_profile(
        self, username: str, ansible_facts: dict[str, dict[str, dict[str, str]]], full: bool = True
    ) -> str:
        user = ansible_facts["user_shells"][username]

        if full:
            return pathlib.Path(user["home"], user["profile"]).as_posix()

        return user["profile"]

    def users_shell(self, username: str, ansible_facts: dict[str, dict[str, dict[str, str]]]) -> str:
        return ansible_facts["user_shells"][username]["shell"]

    def users_home(self, username: str, ansible_facts: dict[str, dict[str, dict[str, str]]]) -> str:
        return ansible_facts["user_shells"][username]["home"]

    def users_uid(self, username: str, ansible_facts: dict[str, dict[str, dict[str, str]]]) -> str:
        return ansible_facts["user_shells"][username]["uid"]

    def users_gid(self, username: str, ansible_facts: dict[str, dict[str, dict[str, str]]]) -> str:
        return ansible_facts["user_shells"][username]["gid"]

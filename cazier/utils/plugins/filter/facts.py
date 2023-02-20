import typing as t


class FilterModule:
    def filters(self) -> dict[str, t.Callable[[str, dict[str, t.Any]], str]]:
        return {"users_profile": self.users_profile, "users_shell": self.users_shell}

    def users_profile(self, username: str, ansible_facts: dict[str, t.Any]) -> str:
        return ansible_facts["user_shells"][username]["profile"]

    def users_shell(self, username: str, ansible_facts: dict[str, t.Any]) -> str:
        return ansible_facts["user_shells"][username]["shell"]

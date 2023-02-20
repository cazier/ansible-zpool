import typing as t


class FilterModule:
    def filters(self) -> dict[str, t.Callable[[dict[str, dict[str, str]], str], str]]:
        return {"users_profile": self.users_profile, "users_shell": self.users_shell}

    def users_profile(self, shells: dict[str, dict[str, str]], username: str) -> str:
        return shells[username]["profile"]

    def users_shell(self, shells: dict[str, dict[str, str]], username: str) -> str:
        return shells[username]["shell"]

import typing as t


class FilterModule:
    def filters(self) -> dict[str, t.Callable[[list[str]], dict[str, bool]]]:
        return {"snapshot": self.snapshot}  # pragma: no cover

    def snapshot(self, spans: list[str]) -> dict[str, bool]:
        output: dict[str, bool] = {}
        for span in ("frequent", "hourly", "daily", "weekly", "monthly"):
            output[f"com.sun:auto-snapshot:{span}"] = bool(span in spans or "@all" in spans)

        return output

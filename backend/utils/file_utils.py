from pathlib import Path


class FileService:
    def __init__(self, WIKI_DIR: Path):
        self.WIKI_DIR = WIKI_DIR
        self.index_map: dict[str, str] = {}

    @property
    def INDEX_PATH(self) -> Path:
        return self.WIKI_DIR / "index.md"

    @property
    def LOG_PATH(self) -> Path:
        return self.WIKI_DIR / "log.md"

    def parse_index_line(self, line: str) -> tuple[str, str] | None:
        if "[[" in line and "]] — " in line:
            name = line.split("[[")[1].split("]]")[0]
            desc = line.split("]] — ", 1)[1].strip()
            return name, desc
        return None

    def _build_file_map(self) -> dict[str, Path]:
        return {
            p.stem: p
            for p in self.WIKI_DIR.rglob("*.md")
            if p.name not in {"index.md", "log.md"} and not p.name.startswith("_")
        }

    def _get_index_map(self) -> dict[str, str]:
        if not self.INDEX_PATH.exists():
            return {}
        return {
            parsed[0]: parsed[1]
            for line in self.INDEX_PATH.read_text(encoding="utf-8").splitlines()
            if (parsed := self.parse_index_line(line))
        }

    def _update_index(self, updates: dict[str, str | None]) -> None:
        for key, value in updates.items():
            if value is None:
                self.index_map.pop(key, None)
            else:
                self.index_map[key] = value
        self.INDEX_PATH.write_text(
            "\n".join(f"[[{k}]] — {v}" for k, v in sorted(self.index_map.items())),
            encoding="utf-8",
        )

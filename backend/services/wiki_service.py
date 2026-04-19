from pathlib import Path
def get_wiki_pages(WIKI_DIR: Path) -> list[Path]:
    return [p for p in sorted(WIKI_DIR.glob("*.md")) if p.name != "_last_response.txt"]
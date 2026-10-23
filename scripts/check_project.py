"""Check the distributable Skill and examples without installing dependencies."""
from pathlib import Path
import json
import re
import sys


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    skill = root / "skills/lizicut"
    errors = []
    entry = (skill / "SKILL.md").read_text(encoding="utf-8")
    if not entry.startswith("---\nname: lizicut\n") or not re.search(r"^description: .+", entry, re.M):
        errors.append("SKILL.md: missing discoverable frontmatter")
    for required in ["README.md", "LICENSE", "skills/lizicut/agents/openai.yaml", "docs/review-v0.1.1.md", "examples/revenue-profit/timeline.json", "examples/revenue-profit/README.md", "examples/revenue-profit/film.mp4", "examples/layered-edit/timeline.json", "examples/layered-edit/README.md", "examples/layered-edit/film.mp4"]:
        if not (root / required).is_file():
            errors.append(f"Missing {required}")
    checked = 0
    for path in root.rglob("*"):
        if not path.is_file() or any(part in {"__pycache__", ".local", "output", "dist"} for part in path.relative_to(root).parts):
            continue
        if path.suffix not in {".md", ".py", ".json", ".srt", ".yaml", ".yml", ".ps1"}:
            continue
        checked += 1
        payload = path.read_bytes()
        if payload.startswith(b"\xef\xbb\xbf"):
            errors.append(f"{path.relative_to(root)}: UTF-8 BOM")
        content = payload.decode("utf-8")
        if path.suffix in {".md", ".yaml", ".yml"} and ("[TODO:" in content or "[TODO]" in content):
            errors.append(f"{path.relative_to(root)}: unfinished scaffold")
        if path.suffix == ".md":
            for link in re.findall(r"\]\(([^)]+)\)", content):
                target = link.strip("<>").split("#", 1)[0]
                if not target or re.match(r"[a-zA-Z][\w+.-]*:", target):
                    continue
                if not (path.parent / target).exists():
                    errors.append(f"{path.relative_to(root)}: broken reference {target}")
    sys.path.insert(0, str(skill / "scripts"))
    from timeline import LizicutError, read_json, validate
    for example in sorted((root / "examples").glob("*/timeline.json")):
        try:
            validate(read_json(example), example.parent, media=True)
        except (LizicutError, OSError) as error:
            errors.append(f"{example.relative_to(root)}: {error}")
    print(json.dumps({"text_files_checked": checked, "errors": errors, "boundary": "package/source checks; no independent creative review"}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

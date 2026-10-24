import json
import sys
from pathlib import Path


def item(id="item"):
    return {
        "type": "Feature",
        "stac_version": "1.1.0",
        "stac_extensions": [],
        "id": id,
        "geometry": {"type": "Point", "coordinates": [0, 0]},
        "bbox": [0, 0, 0, 0],
        "properties": {"datetime": "2024-01-01T00:00:00Z"},
        "links": [],
        "assets": {},
    }


def catalog(links=None, type="Catalog"):
    value = {
        "type": type,
        "stac_version": "1.1.0",
        "id": "catalog",
        "description": "A test catalog",
        "links": links or [],
    }
    if type == "Collection":
        value.update(
            license="MIT",
            extent={
                "spatial": {"bbox": [[-180, -90, 180, 90]]},
                "temporal": {"interval": [[None, None]]},
            },
        )
    return value


def generate(root: Path, count: int = 1000) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "catalog.json").write_text(
        json.dumps(
            catalog(
                [
                    {"rel": "self", "href": "https://offline.invalid/catalog.json"},
                    {"rel": "child", "href": "https://offline.invalid/collection.json"},
                ]
            )
        ),
        encoding="utf-8",
    )
    (root / "collection.json").write_text(
        json.dumps(
            catalog(
                [
                    {"rel": "item", "href": f"https://offline.invalid/{i}.json"}
                    for i in range(count)
                ],
                "Collection",
            )
        ),
        encoding="utf-8",
    )
    for i in range(count):
        (root / f"{i}.json").write_text(json.dumps(item(str(i))), encoding="utf-8")
    invalid = item()
    invalid["bbox"] = [0, 0]
    (root / "invalid.json").write_text(json.dumps(invalid), encoding="utf-8")


if __name__ == "__main__":
    generate(Path(sys.argv[1]))

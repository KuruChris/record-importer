"""Sample records and a mock paginated API for demos and tests."""

from typing import TypedDict


class SampleRecord(TypedDict):
    external_id: str
    name: str


SAMPLE_RECORDS: list[SampleRecord] = [
    {"external_id": "SB-1001", "name": "Notebook"},
    {"external_id": "SB-1002", "name": "Pencil Case"},
    {"external_id": "SB-1003", "name": "Backpack"},
    {"external_id": "SB-1004", "name": "Folder"},
    # Uncomment the following lines to add more sample records for testing purposes.
    # {"external_id": "SB-1005", "name": "Eraser"},
    # {"external_id": "SB-1006", "name": "Ruler"},
    # {"external_id": "SB-1007", "name": "Pencil"},
    # {"external_id": "SB-1008", "name": "Ballpoint Pen"},
    # {"external_id": "SB-1009", "name": "Highlighter"},
    # {"external_id": "SB-1010", "name": "Marker Set"},
    # {"external_id": "SB-1011", "name": "Colored Pencils"},
    # {"external_id": "SB-1012", "name": "Crayons"},
    # {"external_id": "SB-1013", "name": "Glue Stick"},
    # {"external_id": "SB-1014", "name": "Safety Scissors"},
    # {"external_id": "SB-1015", "name": "Tape Dispenser"},
    # {"external_id": "SB-1016", "name": "Index Cards"},
    # {"external_id": "SB-1017", "name": "Sticky Notes"},
    # {"external_id": "SB-1018", "name": "Graph Paper"},
    # {"external_id": "SB-1019", "name": "Composition Book"},
    # {"external_id": "SB-1020", "name": "Binder"},
    # {"external_id": "SB-1021", "name": "Binder Dividers"},
    # {"external_id": "SB-1022", "name": "Sheet Protectors"},
    # {"external_id": "SB-1023", "name": "Calculator"},
    # {"external_id": "SB-1024", "name": "Protractor"},
    # {"external_id": "SB-1025", "name": "Compass"},
    # {"external_id": "SB-1026", "name": "Lunch Box"},
    # {"external_id": "SB-1027", "name": "Water Bottle"},
    # {"external_id": "SB-1028", "name": "Art Sketchbook"},
    # {"external_id": "SB-1029", "name": "Paintbrush Set"},
    # {"external_id": "SB-1030", "name": "USB Flash Drive"},
]


def sample_fetch_page(offset: int, limit: int) -> list[SampleRecord]:
    """Return a page from the sample dataset, mimicking an external API."""
    return SAMPLE_RECORDS[offset : offset + limit]

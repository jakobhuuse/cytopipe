import re
from pathlib import Path

import pandas as pd

# ChannelNumber to Cell Painting channel (w1=DNA, w2=Mito, w3=AGP, w4=RNA, w5=ER).
#
# WARNING: this is a hardcoded assumption about the acquisition's filter/channel
# configuration, not something this codebase can verify. It used to match a
# NamesAndTypes rule in the .cppipe files; those were migrated to LoadData-CSV
# input and no longer state this mapping anywhere, so nothing here cross-checks
# it. If it's wrong, every measurement and every DeepProfiler embedding channel
# is silently mislabeled by stain, with no error raised anywhere. Verify this
# against the microscope's actual channel configuration before trusting results
# from a new acquisition protocol, see the README warning.
CHANNEL_BY_NUMBER = {1: "DNA", 2: "Mito", 3: "AGP", 4: "RNA", 5: "ER"}

# Filename convention, mirroring the .cppipe Metadata regex:
# <experiment>_<well>_s<site>_w<channel><uuid>.tif
FILENAME_RE = re.compile(
    r"^(?P<experiment>[^_]+(?:-[^_]+)*)_(?P<well>[A-P][0-9]{2})_s(?P<site>[0-9]{1,2})_w(?P<channel>[0-9])"
)


def scan_images(input_dir: Path) -> pd.DataFrame:
    """Scan a plate dir for channel TIFFs, parsing (well, site, channel) from each filename.

    Thumbnails (``*_thumb*``) and files not matching the naming convention are skipped.
    Returns one row per image file with columns FileName, Well, Site, ChannelNumber.
    """
    rows = []
    for path in sorted(Path(input_dir).rglob("*.tif")):
        if "_thumb" in path.name.lower():
            continue
        match = FILENAME_RE.match(path.name)
        if not match:
            continue
        channel = int(match["channel"])
        if channel not in CHANNEL_BY_NUMBER:
            continue
        rows.append(
            {
                "FileName": path.name,
                "Well": match["well"],
                "Site": int(match["site"]),
                "ChannelNumber": channel,
            }
        )
    if not rows:
        raise FileNotFoundError(
            f"No channel images matching the naming convention found under {input_dir}."
        )
    return pd.DataFrame(rows)

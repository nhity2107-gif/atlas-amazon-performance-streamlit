from __future__ import annotations

import argparse
from pathlib import Path
import re

from cryptography.fernet import Fernet


ROOT = Path(__file__).resolve().parents[1]
SECRETS = ROOT / ".streamlit" / "secrets.toml"
DEFAULT_EXPORT = ROOT.parent / "STREAMLIT-CLOUD-SECRET.txt"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create the shared encrypted-snapshot key without printing it to the terminal."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_EXPORT)
    args = parser.parse_args()

    contents = SECRETS.read_text(encoding="utf-8") if SECRETS.exists() else ""
    match = re.search(
        r'^(?:DASHBOARD_DATA_KEY|PUBLISHED_SNAPSHOT_KEY)\s*=\s*"([^"]+)"',
        contents,
        flags=re.MULTILINE,
    )
    if match:
        key = match.group(1)
        status = "Existing local key retained."
    else:
        key = Fernet.generate_key().decode("utf-8")
        separator = "" if not contents or contents.endswith("\n") else "\n"
        SECRETS.parent.mkdir(parents=True, exist_ok=True)
        SECRETS.write_text(
            contents + separator + f'\nDASHBOARD_DATA_KEY = "{key}"\n',
            encoding="utf-8",
        )
        status = "New local key created."

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "# Copy this line to Streamlit Cloud > App settings > Secrets.\n"
        f'DASHBOARD_DATA_KEY = "{key}"\n',
        encoding="utf-8",
    )
    print(status)
    print(f"Cloud secret saved to: {output}")
    print("The key value was not printed to this terminal.")


if __name__ == "__main__":
    main()

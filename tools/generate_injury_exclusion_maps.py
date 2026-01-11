from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_filtering import write_injury_exclusion_files


if __name__ == "__main__":
    write_injury_exclusion_files()

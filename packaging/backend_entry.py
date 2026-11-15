"""cx_Freeze entry point for the installed NightCrate backend."""

from nightcrate.serve import main


if __name__ == "__main__":
    raise SystemExit(main())

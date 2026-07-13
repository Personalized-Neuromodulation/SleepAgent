#!/usr/bin/env python3
from __future__ import annotations

import multiprocessing as mp


def main() -> int:
    try:
        mp.set_start_method("fork")
    except RuntimeError:
        pass
    from fmriprep.cli.run import main as fmriprep_main

    return int(fmriprep_main() or 0)


if __name__ == "__main__":
    raise SystemExit(main())

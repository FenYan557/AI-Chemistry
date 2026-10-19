# -*- coding: utf-8 -*-
"""统一验收入口；详细口径与实现见 release_check.py。"""
import sys
from release_check import main

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

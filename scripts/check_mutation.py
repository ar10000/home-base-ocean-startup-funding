"""Mutation-testing gate (handbook section 9).

Reads `mutmut results --all true` from stdin and fails unless at least 90% of
mutants are killed overall and 100% in the matching and today modules.

    cd api && uv run mutmut results --all true | uv run python ../scripts/check_mutation.py
"""

from __future__ import annotations

import re
import sys
from collections import Counter

OVERALL_MIN = 0.90
MODULE_MIN = {"matching": 1.0, "today": 1.0}
LINE = re.compile(r"^\s*home_base\.modules\.(\w+)\.(\w+)\.\S+:\s*(\w+)\s*$")


def main() -> int:
    killed: Counter[str] = Counter()
    total: Counter[str] = Counter()
    survivors: list[str] = []
    for line in sys.stdin:
        match = LINE.match(line)
        if not match:
            continue
        module, _, status = match.groups()
        total[module] += 1
        if status == "killed":
            killed[module] += 1
        else:
            survivors.append(f"{line.strip()}")
    if not total:
        sys.stderr.write("check_mutation: no mutant results read\n")
        return 1
    failed = False
    for module in sorted(total):
        ratio = killed[module] / total[module]
        need = MODULE_MIN.get(module)
        flag = "" if need is None or ratio >= need else f"  below {need:.0%}"
        failed |= bool(flag)
        sys.stdout.write(f"{module}: {killed[module]}/{total[module]} killed ({ratio:.1%}){flag}\n")
    overall = sum(killed.values()) / sum(total.values())
    if overall < OVERALL_MIN:
        failed = True
    sys.stdout.write(f"overall: {sum(killed.values())}/{sum(total.values())} ({overall:.1%})\n")
    for survivor in survivors:
        sys.stderr.write(f"not killed: {survivor}\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

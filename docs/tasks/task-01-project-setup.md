# Task 01: Project Setup

**Plan:** test-plan.md
**Prerequisites:** None

## Objective

Set up the directory structure, dependencies, and basic configuration so tests can import tychos_skyfield and run with pytest.

## Steps

### 1. Create requirements.txt at repo root

```
numpy
scipy
pytest
```

Note: skyfield is NOT needed for eclipse testing — we only use tychos_skyfield's native baselib, not the skyfield bridge.

### 2. Create directory structure

```
tests/
  data/           # will hold parsed eclipse JSON files
  conftest.py     # empty for now, populated in task-02
```

### 3. Create a minimal conftest.py

```python
import sys
from pathlib import Path

# Add tychos_skyfield to the import path
sys.path.insert(0, str(Path(__file__).parent.parent / "tychos_skyfield"))
```

### 4. Verify imports work

```bash
PYTHONPATH=tychos_skyfield pytest tests/ --collect-only
```

Should collect 0 tests with no import errors.

## Verification

- [ ] `pip install -r requirements.txt` succeeds
- [ ] `pytest tests/ --collect-only` runs without import errors
- [ ] `python -c "from tychos_skyfield import baselib"` works

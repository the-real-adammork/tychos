# Tasks: Tychos Eclipse Prediction Tests

**Source Plan:** [test-plan.md](../test-plan.md)
**Total Tasks:** 6

## Task Sequence

| # | Task | Description |
|---|------|-------------|
| 01 | [Project setup](./task-01-project-setup.md) | requirements.txt, conftest.py, directory structure |
| 02 | [Angular separation helpers](./task-02-helpers.md) | Vincenty formula, scan logic, shared utilities |
| 03 | [Parse NASA eclipse catalogs](./task-03-parse-catalogs.md) | Script to convert fixed-width NASA data to JSON |
| 04 | [Solar eclipse tests](./task-04-solar-eclipses.md) | Test Tychos predictions against NASA solar eclipse catalog |
| 05 | [Lunar eclipse tests](./task-05-lunar-eclipses.md) | Test Tychos predictions against NASA lunar eclipse catalog |
| 06 | [Smoke and false-positive tests](./task-06-smoke-tests.md) | Sanity checks and non-eclipse verification |

## Dependencies

```
task-01 ──► task-02 ──► task-04
                   ├──► task-05
                   └──► task-06
task-03 ──► task-04
       └──► task-05
```

---
name: repo-analysis
description: Analyze the purpose, modules, runtime flow, and tests of a Python repository using direct file evidence.
---

# Python Repository Analysis

Use this procedure when the user asks what a Python repository does or how it is organized.

1. List the repository root and locate the primary source directory.
2. Inspect the main package's `__init__.py` and the largest source modules.
3. Infer public entry points from imports and callable definitions in the source package.
4. Inspect the test tree to identify the main behavior contracts.
5. Explain purpose, modules, runtime flow, and risks. Cite concrete relative paths for every architectural claim.

Do not modify repository files. Do not claim a path or entry point that you did not directly inspect.

# Task: Characterise a Paraboloid Test Function

Work with the test function `f(x, y) = (x - 3)^2 + x*y + (y + 4)^2 - 3`.

First evaluate it at the point `x = 1.0`, `y = 2.0`. Then, separately, find
its unconstrained minimum with a gradient-based optimizer, letting both
variables range over `[-50, 50]`.

## What matters

- The evaluation and the minimisation are two distinct runs; keep them
  distinguishable in your records.
- Confirm the optimizer actually converged before you trust the minimum.

## Report

The function value at the evaluation point, and the minimised function value
with the location where it occurs.

This task deliberately does not name the component type, parameter keys, or
tool workflow. Consult the server's own reference material to choose them.

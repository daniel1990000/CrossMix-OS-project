"""Fixed reviewed source configuration entrypoint.

The development payload deliberately supplies no qualified runtime. A qualified
release can replace this fixed source module after the independent source-use,
installed inventory and physical checks pass. Card JSON, environment variables
and package signatures cannot select callbacks or turn these gates on.
"""


def configuration():
    return None

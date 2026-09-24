# SPDX-FileCopyrightText: 2026 The University of St Andrews
# SPDX-License-Identifier: GPL-3.0-or-later

"""Entry point for the citesmith command-line interface.

This module exposes a console script entry point that invokes the
CLI defined in citesmith.cli.
"""

from citesmith.cli import cli

if __name__ == "__main__":
    cli()  # pylint: disable=no-value-for-parameter

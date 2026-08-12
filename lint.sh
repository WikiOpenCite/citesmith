#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Zoe Nickson <zoe.nickson@sidingsmedia.com>
# SPDX-License-Identifier: MIT

pylint citesmith

pylint tests --disable redefined-outer-name,unused-argument,pointless-statement,missing-module-docstring
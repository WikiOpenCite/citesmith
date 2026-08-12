#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Zoe Nickson <mjn6@st-andrews.ac.uk>
# SPDX-License-Identifier: MIT

pylint app

pylint tests --disable redefined-outer-name,unused-argument,pointless-statement,missing-module-docstring
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared SSL context — read the CA bundle exactly once for the process.

On Windows, OpenSSL's BIO layer reads certifi's cacert.pem (~272 KB)
byte-by-byte through ReadFile(), generating ~272K I/O operations per
ssl.create_default_context(cafile=...) call.  By creating the context
once and sharing it across all httpx clients, the CA bundle is parsed
a single time regardless of how many clients are constructed.
"""

from __future__ import annotations

import ssl

import certifi

ssl_ctx: ssl.SSLContext = ssl.create_default_context(cafile=certifi.where())

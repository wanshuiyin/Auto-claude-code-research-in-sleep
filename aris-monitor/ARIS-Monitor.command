#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
exec "$(dirname "$0")/run.sh" "$@"

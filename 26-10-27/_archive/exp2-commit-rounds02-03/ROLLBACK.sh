#!/bin/sh
set -eu
ROOT='/Users/y4n9/Workspace/Projects/My-github-projects/IPI-screen-sec-vault'
INDEX='/Users/y4n9/Workspace/Projects/My-github-projects/IPI-screen-sec-vault/26-10-27/_archive/exp2-commit-rounds02-03/rollback.index'
GIT_INDEX_FILE="$INDEX" git -C "$ROOT" read-tree f1443143c643335e21ec60d6f0a8bbfb2a8608b0
actual=$(GIT_INDEX_FILE="$INDEX" git -C "$ROOT" write-tree)
expected=$(git -C "$ROOT" rev-parse f1443143c643335e21ec60d6f0a8bbfb2a8608b0^{tree})
[ "$actual" = "$expected" ]
printf "ROLLBACK PASS: isolated index restored to original tree %s\n" "$actual"

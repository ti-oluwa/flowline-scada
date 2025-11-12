#!/usr/bin/env bash

NAME="flowlinescada.exe"

if [ -n "$1" ]; then
  NAME="$1"
fi

nicegui-pack --onefile --windowed --name "$NAME" main.py

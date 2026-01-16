#!/usr/bin/env bash
set -euo pipefail

trap 'echo "[ERROR] Script failed on line $LINENO"' ERR

NAME="FlowlineSCADA.exe"
ENTRY="main.py"
ICON="assets/pipeline.ico"

OPTIND=1

print_info() { printf "[INFO]  %s\n" "$*"; }
print_warn() { printf "[WARN]  %s\n" "$*"; }
print_err()  { printf "[ERROR] %s\n" "$*" >&2; }

usage() {
    cat <<'EOF'
Usage: build.sh [options]

Options:
  -n NAME    Set output name (default: FlowlineSCADA.exe)
  -e ENTRY   Entry python file (default: main.py)
  -h         Show this help message
EOF
}

while getopts ":n:e:h" opt; do
    case "$opt" in
        n) NAME="$OPTARG" ;;
        e) ENTRY="$OPTARG" ;;
        h) usage; exit 0 ;;
        \?) print_err "Invalid option: -$OPTARG"; usage; exit 1 ;;
        :)  print_err "Option -$OPTARG requires an argument"; exit 1 ;;
    esac
done

shift $((OPTIND - 1))

print_info "Repository root: $(pwd)"
print_info "Entry point: $ENTRY"
print_info "Output name: $NAME"
print_info "Icon: $ICON"

command -v nicegui-pack >/dev/null 2>&1 || {
    print_err "'nicegui-pack' not found in PATH"
    exit 1
}

if [ -f "$NAME" ]; then
    print_warn "Removing existing artifact: $NAME"
    rm -f "$NAME"
fi

print_info "Running nicegui-pack..."
nicegui-pack \
    --onefile \
    --windowed \
    --icon "$ICON" \
    --name "$NAME" \
    "$ENTRY"

print_info "Build completed"


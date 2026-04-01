#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

launch_in_terminal_window() {
  local script_path="$1"
  local script_name
  script_name="$(basename "${script_path}")"

  if command -v x-terminal-emulator >/dev/null 2>&1; then
    x-terminal-emulator -e bash -lc "'${script_path}'" &
    return
  fi

  if command -v gnome-terminal >/dev/null 2>&1; then
    gnome-terminal -- bash -lc "'${script_path}'" &
    return
  fi

  if command -v konsole >/dev/null 2>&1; then
    konsole --noclose -e bash -lc "'${script_path}'" &
    return
  fi

  if command -v xfce4-terminal >/dev/null 2>&1; then
    xfce4-terminal --command "bash -lc '${script_path}'" &
    return
  fi

  if command -v cmd.exe >/dev/null 2>&1; then
    local cmd_script
    cmd_script="${script_path%.sh}.cmd"
    if [[ -f "${cmd_script}" ]]; then
      cmd.exe /c start "OpAMP ${script_name}" cmd /k "${cmd_script}" >/dev/null 2>&1
      return
    fi
  fi

  echo "No terminal launcher detected for ${script_name}; running in background."
  nohup bash "${script_path}" >/dev/null 2>&1 &
}

shopt -s nullglob
supervisor_scripts=("${SCRIPT_DIR}"/run_*_supervisor.sh)
launched_count=0

if [[ ${#supervisor_scripts[@]} -eq 0 ]]; then
  echo "No run_*_supervisor.sh scripts found in ${SCRIPT_DIR}"
  exit 0
fi

for supervisor_script in "${supervisor_scripts[@]}"; do
  if [[ "$(basename "${supervisor_script}")" == "run_all_supervisors.sh" ]]; then
    continue
  fi
  echo "Launching ${supervisor_script}"
  launch_in_terminal_window "${supervisor_script}"
  launched_count=$((launched_count + 1))
done

if [[ ${launched_count} -eq 0 ]]; then
  echo "No matching supervisor launch scripts found (excluding run_all_supervisors.sh)."
fi

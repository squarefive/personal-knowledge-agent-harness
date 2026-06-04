#!/usr/bin/env bash

set -euo pipefail

MAIN_BRANCH="main"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Error: current directory is not inside a Git repository." >&2
  exit 1
fi

if ! git show-ref --verify --quiet "refs/heads/${MAIN_BRANCH}"; then
  echo "Error: local branch '${MAIN_BRANCH}' does not exist." >&2
  exit 1
fi

repo_root="$(git rev-parse --show-toplevel)"
current_branch="$(git branch --show-current)"
branches_file="$(mktemp)"
merged_file="$(mktemp)"
delete_file="$(mktemp)"

cleanup() {
  rm -f "${branches_file}" "${merged_file}" "${delete_file}"
}
trap cleanup EXIT

git branch --format='%(refname:short)' | sort >"${branches_file}"
git branch --merged "${MAIN_BRANCH}" --format='%(refname:short)' | sort >"${merged_file}"

while IFS= read -r branch; do
  if [[ "${branch}" == "${MAIN_BRANCH}" ]]; then
    continue
  fi

  if grep -Fxq "${branch}" "${merged_file}"; then
    printf '%s\n' "${branch}" >>"${delete_file}"
  fi
done <"${branches_file}"

echo "Repository: ${repo_root}"
echo
printf '%-48s %s\n' "Branch" "Delete"
printf '%-48s %s\n' "------" "------"

while IFS= read -r branch; do
  delete_status="no"
  if [[ "${branch}" != "${MAIN_BRANCH}" ]] && grep -Fxq "${branch}" "${delete_file}"; then
    delete_status="yes"
  fi

  printf '%-48s %s\n' "${branch}" "${delete_status}"
done <"${branches_file}"

echo

if [[ ! -s "${delete_file}" ]]; then
  echo "No local branches merged into '${MAIN_BRANCH}' need deletion."
  exit 0
fi

echo "Branches marked 'yes' are local branches already merged into '${MAIN_BRANCH}'."
printf "Delete these branches? Type 'yes' to continue: "
read -r answer

if [[ "${answer}" != "yes" ]]; then
  echo "Cancelled."
  exit 0
fi

if grep -Fxq "${current_branch}" "${delete_file}"; then
  echo "Current branch '${current_branch}' is marked for deletion. Switching to '${MAIN_BRANCH}' first."
  git switch "${MAIN_BRANCH}"
fi

while IFS= read -r branch; do
  git branch -d "${branch}"
done <"${delete_file}"

echo "Done."

#!/usr/bin/env python3
"""
Set or replace a single key=value in .env. Preserves other lines and comments.
Usage: update_env.py KEY VALUE [.env_path]
Default .env path: .env in current directory (or first dir containing .env upward).
"""
import os
import sys

def find_env_path(start_dir: str, default_name: str = ".env") -> str:
    d = os.path.abspath(start_dir)
    for _ in range(20):
        p = os.path.join(d, default_name)
        if os.path.isfile(p):
            return p
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return os.path.join(os.getcwd(), default_name)


def main():
    if len(sys.argv) < 3:
        print("Usage: update_env.py KEY VALUE [.env_path]", file=sys.stderr)
        sys.exit(1)
    key = sys.argv[1]
    value = sys.argv[2]
    env_path = sys.argv[3] if len(sys.argv) > 3 else find_env_path(os.getcwd())
    if not os.path.isfile(env_path):
        with open(env_path, "w") as f:
            f.write(f"{key}={value}\n")
        return
    with open(env_path, "r") as f:
        lines = f.readlines()
    new_line = f"{key}={value}\n"
    found = False
    out = []
    for line in lines:
        if line.strip().startswith("#"):
            out.append(line)
            continue
        if "=" in line and line.split("=", 1)[0].strip() == key:
            out.append(new_line)
            found = True
        else:
            out.append(line)
    if not found:
        out.append(new_line)
    with open(env_path, "w") as f:
        f.writelines(out)


if __name__ == "__main__":
    main()

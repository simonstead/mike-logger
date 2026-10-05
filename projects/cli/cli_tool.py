#!/usr/bin/env python3

"""
A command-line interface (CLI) tool for file management.

This tool provides a set of commands to perform common file operations, such as
creating, deleting, copying, and moving files and directories. It is designed
to be user-friendly and efficient, making it easy to manage files and
directories from the command line.

Features:
- Create, delete, copy, and move files and directories
- List the contents of a directory
- Change the current working directory
- Display file and directory information
- Supports tab completion for file and directory names

Usage:
  cli_tool.py [command] [arguments]

Available commands:
  create [file/dir]    Create a new file or directory
  delete [file/dir]    Delete a file or directory
  copy [source] [dest] Copy a file or directory
  move [source] [dest] Move a file or directory
  list [directory]     List the contents of a directory
  cd [directory]       Change the current working directory
  info [file/dir]      Display information about a file or directory
  help                 Display help information

For more information on a specific command, use 'help [command]'.
"""

import os
import shutil
import argparse
from pathlib import Path
from typing import List, Tuple

def create(path: str) -> None:
    """
    Create a new file or directory.

    Args:
        path (str): The path of the file or directory to create.
    """
    try:
        if path.endswith('/'):
            os.makedirs(path, exist_ok=True)
        else:
            open(path, 'a').close()
        print(f"Created {path}")
    except Exception as e:
        print(f"Error creating {path}: {e}")

def delete(path: str) -> None:
    """
    Delete a file or directory.

    Args:
        path (str): The path of the file or directory to delete.
    """
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        print(f"Deleted {path}")
    except Exception as e:
        print(f"Error deleting {path}: {e}")

def copy(source: str, dest: str) -> None:
    """
    Copy a file or directory.

    Args:
        source (str): The path of the file or directory to copy.
        dest (str): The destination path for the copy.
    """
    try:
        if os.path.isdir(source):
            shutil.copytree(source, dest)
        else:
            shutil.copy2(source, dest)
        print(f"Copied {source} to {dest}")
    except Exception as e:
        print(f"Error copying {source} to {dest}: {e}")

def move(source: str, dest: str) -> None:
    """
    Move a file or directory.

    Args:
        source (str): The path of the file or directory to move.
        dest (str): The destination path for the move.
    """
    try:
        shutil.move(source, dest)
        print(f"Moved {source} to {dest}")
    except Exception as e:
        print(f"Error moving {source} to {dest}: {e}")

def list_dir(directory: str) -> None:
    """
    List the contents of a directory.

    Args:
        directory (str): The path of the directory to list.
    """
    try:
        contents = os.listdir(directory)
        for item in contents:
            print(item)
    except Exception as e:
        print(f"Error listing {directory}: {e}")

def change_dir(directory: str) -> None:
    """
    Change the current working directory.

    Args:
        directory (str): The path of the directory to change to.
    """
    try:
        os.chdir(directory)
        print(f"Changed directory to {directory}")
    except Exception as e:
        print(f"Error changing directory to {directory}: {e}")

def get_info(path: str) -> None:
    """
    Display information about a file or directory.

    Args:
        path (str): The path of the file or directory to get information about.
    """
    try:
        if os.path.isdir(path):
            print(f"Directory: {path}")
            print(f"Size: {sum(f.stat().st_size for f in Path(path).glob('**/*') if f.is_file())} bytes")
            print(f"Number of files: {len(list(Path(path).glob('**/*')))}")
        else:
            print(f"File: {path}")
            print(f"Size: {os.path.getsize(path)} bytes")
            print(f"Last modified: {os.path.getmtime(path)}")
    except Exception as e:
        print(f"Error getting information for {path}: {e}")

def main() -> None:
    """
    The main entry point for the CLI tool.
    """
    parser = argparse.ArgumentParser(description="CLI file management tool")
    parser.add_argument("command", choices=["create", "delete", "copy", "move", "list", "cd", "info", "help"])
    parser.add_argument("args", nargs="*")
    args = parser.parse_args()

    if args.command == "create":
        create(args.args[0])
    elif args.command == "delete":
        delete(args.args[0])
    elif args.command == "copy":
        copy(args.args[0], args.args[1])
    elif args.command == "move":
        move(args.args[0], args.args[1])
    elif args.command == "list":
        list_dir(args.args[0] if args.args else os.getcwd())
    elif args.command == "cd":
        change_dir(args.args[0])
    elif args.command == "info":
        get_info(args.args[0])
    elif args.command == "help":
        print(__doc__)

if __name__ == "__main__":
    main()
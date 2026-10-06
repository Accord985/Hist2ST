"""
Change working directory to the root of the repo.
Assumed that the folder is called "notebooks" and the parent folder is the root of the repo.
Based on our documents structure this would be true. If the structure changes, this function may not work as expected.
"""

import os
from pathlib import Path

def move_wd_out():
    if Path.cwd().stem == "notebooks":  
        os.chdir(Path.cwd().parent)

if __name__ == "__main__":
    print("Before:", os.getcwd())
    move_wd_out()
    print("After:", os.getcwd())
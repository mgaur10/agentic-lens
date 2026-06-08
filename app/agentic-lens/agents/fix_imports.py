import glob, os

for filepath in glob.glob("*/agent.py"):
    with open(filepath, "r") as f:
        content = f.read()
    
    # Fix from .src.manager
    content = content.replace("from .src.manager", "from src.manager")
    content = content.replace("from .lens_department_hooks", "from lens_department_hooks")
    
    with open(filepath, "w") as f:
        f.write(content)

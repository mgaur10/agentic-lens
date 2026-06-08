import glob
for filepath in glob.glob("agentic-lens/agents/*/requirements.txt"):
    with open(filepath, "r") as f:
        content = f.read()
    if "cloudpickle>=3.0.0" in content:
        content = content.replace("cloudpickle>=3.0.0", "cloudpickle>=2.0.0,<3")
        with open(filepath, "w") as f:
            f.write(content)

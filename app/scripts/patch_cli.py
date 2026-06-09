import sys

def main():
    if len(sys.argv) < 2:
        print("Usage: patch_cli.py <path_to_cli_deploy.py>")
        sys.exit(1)
        
    path = sys.argv[1]
    with open(path, "r") as f:
        text = f.read()

    part1 = text.split("_AGENT_ENGINE_CLASS_METHODS = [")[0]
    part2 = "def _resolve_project(" + text.split("def _resolve_project(")[1]

    new_methods = """_AGENT_ENGINE_CLASS_METHODS = [
    {"name": "query", "description": "Standard Vertex AI query method.", "api_mode": "", "parameters": {"type": "object", "properties": {"message": {"type": "string"}, "session_id": {"type": "string"}}}},
    {"name": "stream_query", "description": "Standard Vertex AI stream_query method.", "api_mode": "stream", "parameters": {"type": "object", "properties": {"message": {"type": "string"}, "session_id": {"type": "string"}}}}
]

"""

    with open(path, "w") as f:
        f.write(part1 + new_methods + part2)

if __name__ == "__main__":
    main()

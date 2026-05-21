
import sys
# Add .venv site-packages to path if not running with venv python (just in case)
import site
# site.addsitedir("agentic-lens/.venv/lib/python3.13/site-packages")

try:
    import google.adk
    print(f"ADK path: {google.adk.__file__}")
    
    # Try to find InvocationContext
    from google.adk.types import InvocationContext
    print("Found InvocationContext in google.adk.types")
    print(help(InvocationContext))
except ImportError:
    try:
        from google.adk.model import InvocationContext
        print("Found InvocationContext in google.adk.model")
        print(help(InvocationContext))
    except ImportError:
        print("Could not find InvocationContext in types or model. Listing google.adk submodules...")
        import pkgutil
        for importer, modname, ispkg in pkgutil.iter_modules(google.adk.__path__):
            print(modname)

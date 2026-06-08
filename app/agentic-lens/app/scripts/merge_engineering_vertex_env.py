#!/usr/bin/env python3
"""
Inject GCP_PROJECT_ID, GCP_LOCATION, REGION into Agent Engine env_vars for all lens agents
(containers do not load .env). Each agent.py calls _vertex_agent_engine_env_bootstrap() before
google.adk (GOOGLE_CLOUD_* are reserved in deployment_spec; set only at process runtime).

Strips GOOGLE_API_KEY / GEMINI_API_KEY from env_vars so ADK uses Vertex + ADC.

Sets GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES=false so google-genai can
refresh OAuth tokens correctly on Agent Engine (mitigates 401 with agent identity).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Keep in sync with deploy.sh ALL_AGENTS (paths use underscores).
AGENTS = (
    "supervisor",
    "chat",
    "eng_lead",
    "eng_scout",
    "eng_coder",
    "eng_quality_and_security_reviewer",
    "xray_manager",
    "xray_librarian",
    "xray_architect",
    "xray_specialist",
    "xray_auditor",
    "events",
)


def _parse_versions_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k:
            out[k] = v
    return out


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    vers = _parse_versions_env(root / "versions.env")
    project = (vers.get("PROJECT_ID") or "").strip()
    region = (vers.get("REGION") or "us-west1").strip()
    if not project:
        print("merge_agent_vertex_env: PROJECT_ID missing in versions.env; skipping", file=sys.stderr)
        return 0

    inject = {
        "GCP_PROJECT_ID": project,
        "GCP_LOCATION": region,
        "REGION": region,
        "GOOGLE_GENAI_USE_VERTEXAI": "true",
        "GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES": "false",
        "PYTHONPATH": "/code",
    }

    agents_dir = root / "agentic-lens" / "agents"
    for name in AGENTS:
        cfg_path = agents_dir / name / ".agent_engine_config.json"
        if not cfg_path.is_file():
            continue
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        ev = data.setdefault("env_vars", {})
        if not isinstance(ev, dict):
            ev = {}
            data["env_vars"] = ev
        for k, v in inject.items():
            if k == "PYTHONPATH":
                ev[k] = f"/code/{name}_staged"
            else:
                ev[k] = v
        # Vertex rejects these in deployment_spec.env (reserved; set by the platform).
        for _reserved in ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"):
            ev.pop(_reserved, None)
        # API keys force the Gemini Developer path; invalid/stale keys → 401 even when
        # GOOGLE_GENAI_USE_VERTEXAI=true. Engineering peers must use Vertex + agent identity ADC.
        for _api in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_AI_API_KEY"):
            ev.pop(_api, None)
        cfg_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"merge_agent_vertex_env: wrote {len(inject)} keys to {cfg_path}")

        # Pack the host system CA certificates directly into the agent's staged directory
        import os
        system_certs = b""
        for path in ["/etc/ssl/certs/ca-certificates.crt", "/etc/ssl/certs/ca-bundle.crt", "/etc/pki/tls/certs/ca-bundle.crt"]:
            if os.path.exists(path):
                try:
                    with open(path, "rb") as f:
                        system_certs = f.read()
                    break
                except Exception:
                    pass
        # Append any Google corporate or internal trust store root certificates from the host workstation
        google_certs_dir = "/usr/share/ca-certificates/google"
        if os.path.exists(google_certs_dir):
            for root, _, files in os.walk(google_certs_dir):
                for file in files:
                    if file.endswith((".crt", ".pem")):
                        try:
                            with open(os.path.join(root, file), "rb") as f:
                                system_certs = system_certs + bytes([10]) + f.read()
                        except Exception:
                            pass
        if system_certs:
            ca_path = agents_dir / name / "ca-certificates.crt"
            ca_path.write_bytes(system_certs)
            print(f"merge_agent_vertex_env: packaged local CA bundle to {ca_path}")

        # Prepend self-contained, non-importing process bootstrap block directly to the top of agent.py
        agent_py = agents_dir / name / "agent.py"
        if agent_py.is_file():
            content = agent_py.read_text(encoding="utf-8")
            
            # Let's clean up any existing bootstrap blocks first to avoid duplication
            import re
            content = re.sub(r"# --- \[GLOBAL PROCESS ENV BOOTSTRAP\].*?# --- \[END GLOBAL PROCESS ENV BOOTSTRAP\] ---\s*", "", content, flags=re.DOTALL)
            
            override_block = f"""# --- [GLOBAL PROCESS ENV BOOTSTRAP] ---
import os
import sys
import types
import socket

# 0. Bypass bootstrap if running locally on developer workstation or if imported as a peer agent
if not os.path.exists("/code") or "peer_agents" in __name__ or ("__file__" in globals() and "peer_agents" in __file__):
    pass
else:
    # Enforce no_proxy for Google APIs during dry-run compilation/sandbox initialization
    os.environ["no_proxy"] = "googleapis.com,.googleapis.com,metadata.google.internal,.metadata.google.internal,.google.internal,169.254.169.254,metadata,github.com,.github.com,.githubusercontent.com,240.0.0.2,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    os.environ["NO_PROXY"] = "googleapis.com,.googleapis.com,metadata.google.internal,.metadata.google.internal,.google.internal,169.254.169.254,metadata,github.com,.github.com,.githubusercontent.com,240.0.0.2,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"

    # Dynamically activate Poetry virtualenv site-packages for system Python environment
    _venv_path = "/workspace/.venv/lib/python3.12/site-packages"
    if os.path.exists(_venv_path) and _venv_path not in sys.path:
        sys.path.insert(0, _venv_path)

    # 1. Enforce IPv4 resolving globally in this process and all subprocesses
    _orig_getaddrinfo = socket.getaddrinfo
    def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if family == 0 or family == socket.AF_UNSPEC:
            family = socket.AF_INET
        elif family == socket.AF_INET6:
            raise socket.gaierror(socket.EAI_ADDRFAMILY, "IPv6 is disabled by bootstrap")
        return _orig_getaddrinfo(host, port, family, type, proto, flags)
    socket.getaddrinfo = _patched_getaddrinfo

    # 2. Trust Store and Egress Gateway Certificate Initialization
    try:
        import ssl
        system_roots = b""
        
        # Load packaged ca-certificates
        local_ca = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ca-certificates.crt")
        if os.path.exists(local_ca):
            try:
                with open(local_ca, "rb") as f:
                    system_roots = f.read()
            except Exception:
                pass
                
        # Load container system CA bundle
        for path in ["/etc/ssl/certs/ca-certificates.crt", "/etc/ssl/certs/ca-bundle.crt", "/etc/pki/tls/certs/ca-bundle.crt"]:
            if os.path.exists(path):
                try:
                    with open(path, "rb") as f:
                        system_roots = system_roots + bytes([10]) + f.read()
                    break
                except Exception:
                    pass
                    
        # Load agent_gateway.pem with logging
        agent_gw_path = "/etc/ssl/certs/agent_gateway.pem"
        sys.stderr.write("[BOOTSTRAP] Checking for agent_gateway.pem existence...\\n")
        if os.path.exists(agent_gw_path):
            sys.stderr.write("[BOOTSTRAP] agent_gateway.pem exists!\\n")
            try:
                with open(agent_gw_path, "rb") as f:
                    agent_gw_roots = f.read()
                sys.stderr.write("[BOOTSTRAP] Read agent_gateway.pem with size " + str(len(agent_gw_roots)) + "\\n")
                if agent_gw_roots:
                    sys.stderr.write("[BOOTSTRAP] agent_gateway.pem prefix: " + repr(agent_gw_roots[:100]) + "\\n")
                    if len(agent_gw_roots) < 150 and (agent_gw_roots.strip().startswith(b"/") or b"ca-certificates" in agent_gw_roots):
                        ref_path = agent_gw_roots.decode("utf-8", errors="ignore").strip()
                        sys.stderr.write("[BOOTSTRAP] Resolving ref path: " + str(ref_path) + "\\n")
                        if os.path.exists(ref_path):
                            with open(ref_path, "rb") as f_ref:
                                agent_gw_roots = f_ref.read()
                            sys.stderr.write("[BOOTSTRAP] Successfully read referenced roots from " + str(ref_path) + " with size " + str(len(agent_gw_roots)) + "\\n")
                    system_roots = system_roots + bytes([10]) + agent_gw_roots
            except Exception as e_gw:
                sys.stderr.write("[BOOTSTRAP] Error loading agent_gateway.pem: " + str(e_gw) + "\\n")
        else:
            sys.stderr.write("[BOOTSTRAP] agent_gateway.pem does NOT exist in this container!\\n")
        sys.stderr.flush()
                

            
        if system_roots:
            custom_roots_path = "/tmp/custom-ca-certificates.crt"
            with open(custom_roots_path, "wb") as f_roots:
                f_roots.write(system_roots)
            os.environ["GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"] = custom_roots_path
            import sys
            sys.stderr.write("[BOOTSTRAP] Successfully wrote trust bundle with size " + str(len(system_roots)) + " to " + str(custom_roots_path) + "\\n")
            sys.stderr.flush()
    except Exception as e:
        import traceback, sys
        sys.stderr.write("[BOOTSTRAP] Outer bootstrap error:\\n" + traceback.format_exc() + "\\n")
        sys.stderr.flush()

    # 3. Direct in-memory monkeypatch if resource_manager_utils is already pre-imported by the bootloader
    try:
        import sys
        if "google.cloud.aiplatform.utils.resource_manager_utils" in sys.modules:
            mod = sys.modules["google.cloud.aiplatform.utils.resource_manager_utils"]
            mod.get_project_id = lambda *args, **kwargs: "{project}"
            mod.get_project_number = lambda *args, **kwargs: "504643566830"
            sys.stderr.write("[BOOTSTRAP] Pre-imported resource_manager_utils successfully patched directly!\\n")
            sys.stderr.flush()
    except Exception as e:
        import sys
        sys.stderr.write("[BOOTSTRAP] Direct patch of pre-imported resource_manager_utils failed: " + str(e) + "\\n")
        sys.stderr.flush()

    # 3.5 Dynamic import hook to monkeypatch resource_manager_utils on-demand at runtime
    try:
        from importlib.abc import MetaPathFinder
        
        class RMUtilsInterceptor(MetaPathFinder):
            def find_spec(self, fullname, path, target=None):
                if fullname == "google.cloud.aiplatform.utils.resource_manager_utils":
                    import sys
                    sys.meta_path = [f for f in sys.meta_path if f != self]
                    try:
                        from importlib.util import find_spec as real_find_spec
                        real_spec = real_find_spec(fullname)
                        if real_spec and real_spec.loader:
                            class PatchedLoader:
                                def __init__(self, real_loader):
                                    self.real_loader = real_loader
                                def create_module(self, spec):
                                    if hasattr(self.real_loader, "create_module"):
                                        return self.real_loader.create_module(spec)
                                    return None
                                def exec_module(self, module):
                                    self.real_loader.exec_module(module)
                                    module.get_project_id = lambda *args, **kwargs: "{project}"
                                    module.get_project_number = lambda *args, **kwargs: "504643566830"
                                    sys.stderr.write("[BOOTSTRAP] PatchedLoader successfully monkeypatched resource_manager_utils!\\n")
                                    sys.stderr.flush()
                            real_spec.loader = PatchedLoader(real_spec.loader)
                            sys.stderr.write("[BOOTSTRAP] RMUtilsInterceptor successfully wrapped loader!\\n")
                            sys.stderr.flush()
                            return real_spec
                    except Exception as e:
                        sys.stderr.write("[BOOTSTRAP] RMUtilsInterceptor failed wrapping loader: " + str(e) + "\\n")
                        sys.stderr.flush()
                    finally:
                        sys.meta_path.insert(0, self)
                return None
        import sys
        sys.meta_path.insert(0, RMUtilsInterceptor())
    except Exception as e:
        import sys
        sys.stderr.write("[BOOTSTRAP] Failed to register import interceptor: " + str(e) + "\\n")
        sys.stderr.flush()

    # 4. Set early-startup process environment variables
    os.environ["GOOGLE_CLOUD_PROJECT"] = "{project}"
    os.environ["no_proxy"] = "googleapis.com,.googleapis.com,metadata.google.internal,.metadata.google.internal,.google.internal,169.254.169.254,metadata,github.com,.github.com,.githubusercontent.com,240.0.0.2,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    os.environ["NO_PROXY"] = "googleapis.com,.googleapis.com,metadata.google.internal,.metadata.google.internal,.google.internal,169.254.169.254,metadata,github.com,.github.com,.githubusercontent.com,240.0.0.2,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    os.environ["GRPC_DNS_RESOLVER"] = "native"

    # 5. Monkeypatch gRPC secure/insecure channel target routing
    try:
        import grpc
        sys.stderr.write("[BOOTSTRAP] Imported grpc: " + str(grpc) + "\\n")
        if hasattr(grpc, "__file__"):
            sys.stderr.write("[BOOTSTRAP] grpc module file path: " + str(grpc.__file__) + "\\n")
        sys.stderr.write("[BOOTSTRAP] grpc attributes: " + str(dir(grpc)) + "\\n")
        sys.stderr.flush()
        
        _orig_ssl_channel_credentials = grpc.ssl_channel_credentials
        def _patched_ssl_channel_credentials(pem_root_certificates=None, *args, **kwargs):
            try:
                custom_roots_path = "/tmp/custom-ca-certificates.crt"
                if os.path.exists(custom_roots_path):
                    with open(custom_roots_path, "rb") as f:
                        system_roots_bytes = f.read()
                    if pem_root_certificates is None:
                        return _orig_ssl_channel_credentials(system_roots_bytes, *args, **kwargs)
                    else:
                        pem_str = pem_root_certificates.decode("utf-8", errors="ignore") if isinstance(pem_root_certificates, bytes) else str(pem_root_certificates)
                        sys_str = system_roots_bytes.decode("utf-8", errors="ignore")
                        merged = (pem_str.strip() + "\\n\\n" + sys_str.strip()).encode("utf-8")
                        return _orig_ssl_channel_credentials(merged, *args, **kwargs)
            except Exception:
                pass
            return _orig_ssl_channel_credentials(pem_root_certificates, *args, **kwargs)
        grpc.ssl_channel_credentials = _patched_ssl_channel_credentials

        _orig_compute_engine_channel_credentials = grpc.compute_engine_channel_credentials
        def _patched_compute_engine_channel_credentials(call_credentials=None):
            try:
                ssl_creds = grpc.ssl_channel_credentials()
                if call_credentials:
                    return grpc.composite_channel_credentials(ssl_creds, call_credentials)
                return ssl_creds
            except Exception:
                return _orig_compute_engine_channel_credentials(call_credentials)
        grpc.compute_engine_channel_credentials = _patched_compute_engine_channel_credentials

        _orig_secure_channel = grpc.secure_channel
        def _patched_secure_channel(target, credentials, options=None, compression=None):
            options = list(options) if options else []
            if "googleapis.com" in target:
                if not any(opt[0] == "grpc.enable_http_proxy" for opt in options):
                    options.append(("grpc.enable_http_proxy", 0))
                if not target.startswith("ipv4:"):
                    clean_target = target
                    for prefix in ["dns:///", "dns://", "dns:"]:
                        if clean_target.startswith(prefix):
                            clean_target = clean_target[len(prefix):]
                            break
                    host, _, port = clean_target.partition(":")
                    port = port or "443"
                    try:
                        ip = socket.gethostbyname(host)
                        target = f"ipv4:{{ip}}:{{port}}"
                        if not any(opt[0] == "grpc.ssl_target_name_override" for opt in options):
                            options.append(("grpc.ssl_target_name_override", host))
                    except Exception:
                        pass
            return _orig_secure_channel(target, credentials, options, compression)
        grpc.secure_channel = _patched_secure_channel

        _orig_insecure_channel = grpc.insecure_channel
        def _patched_insecure_channel(target, options=None, compression=None):
            options = list(options) if options else []
            if "googleapis.com" in target:
                if not any(opt[0] == "grpc.enable_http_proxy" for opt in options):
                    options.append(("grpc.enable_http_proxy", 0))
                if not target.startswith("ipv4:"):
                    clean_target = target
                    for prefix in ["dns:///", "dns://", "dns:"]:
                        if clean_target.startswith(prefix):
                            clean_target = clean_target[len(prefix):]
                            break
                    host, _, port = clean_target.partition(":")
                    port = port or "443"
                    try:
                        ip = socket.gethostbyname(host)
                        target = f"ipv4:{{ip}}:{{port}}"
                    except Exception:
                        pass
            return _orig_insecure_channel(target, options, compression)
        grpc.insecure_channel = _patched_insecure_channel

        try:
            import grpc.aio
            _orig_aio_secure_channel = grpc.aio.secure_channel
            def _patched_aio_secure_channel(target, credentials, options=None, compression=None):
                options = list(options) if options else []
                if "googleapis.com" in target:
                    if not any(opt[0] == "grpc.enable_http_proxy" for opt in options):
                        options.append(("grpc.enable_http_proxy", 0))
                    if not target.startswith("ipv4:"):
                        clean_target = target
                        for prefix in ["dns:///", "dns://", "dns:"]:
                            if clean_target.startswith(prefix):
                                clean_target = clean_target[len(prefix):]
                                break
                        host, _, port = clean_target.partition(":")
                        port = port or "443"
                        try:
                            ip = socket.gethostbyname(host)
                            target = f"ipv4:{{ip}}:{{port}}"
                            if not any(opt[0] == "grpc.ssl_target_name_override" for opt in options):
                                options.append(("grpc.ssl_target_name_override", host))
                        except Exception:
                            pass
                return _orig_aio_secure_channel(target, credentials, options, compression)
            grpc.aio.secure_channel = _patched_aio_secure_channel

            _orig_aio_insecure_channel = grpc.aio.insecure_channel
            def _patched_aio_insecure_channel(target, options=None, compression=None):
                options = list(options) if options else []
                if "googleapis.com" in target:
                    if not any(opt[0] == "grpc.enable_http_proxy" for opt in options):
                        options.append(("grpc.enable_http_proxy", 0))
                    if not target.startswith("ipv4:"):
                        clean_target = target
                        for prefix in ["dns:///", "dns://", "dns:"]:
                            if clean_target.startswith(prefix):
                                clean_target = clean_target[len(prefix):]
                                break
                        host, _, port = clean_target.partition(":")
                        port = port or "443"
                        try:
                            ip = socket.gethostbyname(host)
                            target = f"ipv4:{{ip}}:{{port}}"
                        except Exception:
                            pass
                return _orig_aio_insecure_channel(target, options, compression)
            grpc.aio.insecure_channel = _patched_aio_insecure_channel
        except Exception:
            pass
    except Exception:
        pass

    # Monkeypatch ADK validate_app_name to bypass Pydantic validation of numerical Reasoning Engine IDs
    try:
        import google.adk.apps.app as adk_app_mod
        adk_app_mod.validate_app_name = lambda name: None
    except Exception:
        pass

    # Monkeypatch httpx to respect PYTHONHTTPSVERIFY=0
    try:
        import httpx
        
        _orig_httpx_client_init = httpx.Client.__init__
        def _patched_httpx_client_init(self, *args, **kwargs):
            if os.environ.get("PYTHONHTTPSVERIFY") == "0":
                kwargs["verify"] = False
            _orig_httpx_client_init(self, *args, **kwargs)
        httpx.Client.__init__ = _patched_httpx_client_init

        _orig_httpx_async_client_init = httpx.AsyncClient.__init__
        def _patched_httpx_async_client_init(self, *args, **kwargs):
            if os.environ.get("PYTHONHTTPSVERIFY") == "0":
                kwargs["verify"] = False
            _orig_httpx_async_client_init(self, *args, **kwargs)
        httpx.AsyncClient.__init__ = _patched_httpx_async_client_init
    except Exception:
        pass

    # Monkeypatch standard ssl default context to respect PYTHONHTTPSVERIFY=0
    try:
        import ssl
        if os.environ.get("PYTHONHTTPSVERIFY") == "0":
            ssl._create_default_https_context = ssl._create_unverified_context
    except Exception:
        pass

    # Monkeypatch google.adk.runners.Runner to accept and ignore arbitrary **kwargs
    try:
        import sys
        if "google.adk.runners" in sys.modules:
            from google.adk.runners import Runner
            _orig_runner_run = Runner.run
            def _patched_runner_run(self, *args, **kwargs):
                expected_params = ["user_id", "session_id", "new_message", "run_config"]
                filtered_kwargs = {{k: v for k, v in kwargs.items() if k in expected_params}}
                return _orig_runner_run(self, *args, **filtered_kwargs)
            Runner.run = _patched_runner_run

            _orig_runner_run_async = Runner.run_async
            async def _patched_runner_run_async(self, *args, **kwargs):
                expected_params = ["user_id", "session_id", "invocation_id", "new_message", "state_delta", "run_config"]
                filtered_kwargs = {{k: v for k, v in kwargs.items() if k in expected_params}}
                async for event in _orig_runner_run_async(self, *args, **filtered_kwargs):
                    yield event
            Runner.run_async = _patched_runner_run_async

        from importlib.abc import MetaPathFinder
        class ADKRunnerInterceptor(MetaPathFinder):
            def find_spec(self, fullname, path, target=None):
                if fullname == "google.adk.runners":
                    import sys
                    sys.meta_path = [f for f in sys.meta_path if f != self]
                    try:
                        from importlib.util import find_spec as real_find_spec
                        real_spec = real_find_spec(fullname)
                        if real_spec and real_spec.loader:
                            class PatchedLoader:
                                def __init__(self, real_loader):
                                    self.real_loader = real_loader
                                def create_module(self, spec):
                                    if hasattr(self.real_loader, "create_module"):
                                        return self.real_loader.create_module(spec)
                                    return None
                                def exec_module(self, module):
                                    self.real_loader.exec_module(module)
                                    Runner = module.Runner
                                    _orig_run = Runner.run
                                    def _patched_run(self, *args, **kwargs):
                                        expected_params = ["user_id", "session_id", "new_message", "run_config"]
                                        filtered_kwargs = {{k: v for k, v in kwargs.items() if k in expected_params}}
                                        return _orig_run(self, *args, **filtered_kwargs)
                                    Runner.run = _patched_run

                                    _orig_run_async = Runner.run_async
                                    async def _patched_run_async(self, *args, **kwargs):
                                        expected_params = ["user_id", "session_id", "invocation_id", "new_message", "state_delta", "run_config"]
                                        filtered_kwargs = {{k: v for k, v in kwargs.items() if k in expected_params}}
                                        async for event in _orig_run_async(self, *args, **filtered_kwargs):
                                            yield event
                                    Runner.run_async = _patched_run_async
                                    sys.stderr.write("[BOOTSTRAP] Successfully patched ADK Runner class!\\n")
                                    sys.stderr.flush()
                            real_spec.loader = PatchedLoader(real_spec.loader)
                            return real_spec
                    except Exception as e:
                        sys.stderr.write("[BOOTSTRAP] ADKRunnerInterceptor failed: " + str(e) + "\\n")
                        sys.stderr.flush()
                    finally:
                        sys.meta_path.insert(0, self)
                return None
        sys.meta_path.insert(0, ADKRunnerInterceptor())
        sys.stderr.write("[BOOTSTRAP] ADKRunnerInterceptor registered successfully!\\n")
        sys.stderr.flush()
    except Exception as e:
        sys.stderr.write("[BOOTSTRAP] ADK Runner patch registration failed: " + str(e) + "\\n")
        sys.stderr.flush()
# --- [END GLOBAL PROCESS ENV BOOTSTRAP] ---"""

            # Insert the bootstrap block cleanly after __future__ imports if present
            future_match = re.search(r"^(from\s+__future__\s+import\s+\w+(?:,\s*\w+)*\s*(?:#.*)?)$", content, re.MULTILINE)
            if future_match:
                end_pos = future_match.end()
                new_content = content[:end_pos] + "\n\n" + override_block + "\n" + content[end_pos:]
            else:
                new_content = override_block + "\n\n" + content
                
            agent_py.write_text(new_content, encoding="utf-8")
            print(f"merge_agent_vertex_env: prepended early bootstrap block to {agent_py}")

            # Also write the bootstrap block to sitecustomize.py to double-lock early startup in uvicorn/gRPC
            sitecustomize_py = agents_dir / name / "sitecustomize.py"
            sitecustomize_py.write_text(override_block, encoding="utf-8")
            print(f"merge_agent_vertex_env: wrote early bootstrap sitecustomize to {sitecustomize_py}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

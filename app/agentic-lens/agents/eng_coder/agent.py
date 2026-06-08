# --- [GLOBAL PROCESS ENV BOOTSTRAP] ---
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
        sys.stderr.write("[BOOTSTRAP] Checking for agent_gateway.pem existence...\n")
        if os.path.exists(agent_gw_path):
            sys.stderr.write("[BOOTSTRAP] agent_gateway.pem exists!\n")
            try:
                with open(agent_gw_path, "rb") as f:
                    agent_gw_roots = f.read()
                sys.stderr.write("[BOOTSTRAP] Read agent_gateway.pem with size " + str(len(agent_gw_roots)) + "\n")
                if agent_gw_roots:
                    sys.stderr.write("[BOOTSTRAP] agent_gateway.pem prefix: " + repr(agent_gw_roots[:100]) + "\n")
                    if len(agent_gw_roots) < 150 and (agent_gw_roots.strip().startswith(b"/") or b"ca-certificates" in agent_gw_roots):
                        ref_path = agent_gw_roots.decode("utf-8", errors="ignore").strip()
                        sys.stderr.write("[BOOTSTRAP] Resolving ref path: " + str(ref_path) + "\n")
                        if os.path.exists(ref_path):
                            with open(ref_path, "rb") as f_ref:
                                agent_gw_roots = f_ref.read()
                            sys.stderr.write("[BOOTSTRAP] Successfully read referenced roots from " + str(ref_path) + " with size " + str(len(agent_gw_roots)) + "\n")
                    system_roots = system_roots + bytes([10]) + agent_gw_roots
            except Exception as e_gw:
                sys.stderr.write("[BOOTSTRAP] Error loading agent_gateway.pem: " + str(e_gw) + "\n")
        else:
            sys.stderr.write("[BOOTSTRAP] agent_gateway.pem does NOT exist in this container!\n")
        sys.stderr.flush()
                

            
        if system_roots:
            custom_roots_path = "/tmp/custom-ca-certificates.crt"
            with open(custom_roots_path, "wb") as f_roots:
                f_roots.write(system_roots)
            os.environ["GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"] = custom_roots_path
            import sys
            sys.stderr.write("[BOOTSTRAP] Successfully wrote trust bundle with size " + str(len(system_roots)) + " to " + str(custom_roots_path) + "\n")
            sys.stderr.flush()
    except Exception as e:
        import traceback, sys
        sys.stderr.write("[BOOTSTRAP] Outer bootstrap error:\n" + traceback.format_exc() + "\n")
        sys.stderr.flush()

    # 3. Direct in-memory monkeypatch if resource_manager_utils is already pre-imported by the bootloader
    try:
        import sys
        if "google.cloud.aiplatform.utils.resource_manager_utils" in sys.modules:
            mod = sys.modules["google.cloud.aiplatform.utils.resource_manager_utils"]
            mod.get_project_id = lambda *args, **kwargs: "agentic-ai-lens"
            mod.get_project_number = lambda *args, **kwargs: "504643566830"
            sys.stderr.write("[BOOTSTRAP] Pre-imported resource_manager_utils successfully patched directly!\n")
            sys.stderr.flush()
    except Exception as e:
        import sys
        sys.stderr.write("[BOOTSTRAP] Direct patch of pre-imported resource_manager_utils failed: " + str(e) + "\n")
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
                                    module.get_project_id = lambda *args, **kwargs: "agentic-ai-lens"
                                    module.get_project_number = lambda *args, **kwargs: "504643566830"
                                    sys.stderr.write("[BOOTSTRAP] PatchedLoader successfully monkeypatched resource_manager_utils!\n")
                                    sys.stderr.flush()
                            real_spec.loader = PatchedLoader(real_spec.loader)
                            sys.stderr.write("[BOOTSTRAP] RMUtilsInterceptor successfully wrapped loader!\n")
                            sys.stderr.flush()
                            return real_spec
                    except Exception as e:
                        sys.stderr.write("[BOOTSTRAP] RMUtilsInterceptor failed wrapping loader: " + str(e) + "\n")
                        sys.stderr.flush()
                    finally:
                        sys.meta_path.insert(0, self)
                return None
        import sys
        sys.meta_path.insert(0, RMUtilsInterceptor())
    except Exception as e:
        import sys
        sys.stderr.write("[BOOTSTRAP] Failed to register import interceptor: " + str(e) + "\n")
        sys.stderr.flush()

    # 4. Set early-startup process environment variables
    os.environ["GOOGLE_CLOUD_PROJECT"] = "agentic-ai-lens"
    os.environ["no_proxy"] = "googleapis.com,.googleapis.com,metadata.google.internal,.metadata.google.internal,.google.internal,169.254.169.254,metadata,github.com,.github.com,.githubusercontent.com,240.0.0.2,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    os.environ["NO_PROXY"] = "googleapis.com,.googleapis.com,metadata.google.internal,.metadata.google.internal,.google.internal,169.254.169.254,metadata,github.com,.github.com,.githubusercontent.com,240.0.0.2,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    os.environ["GRPC_DNS_RESOLVER"] = "native"

    # 5. Monkeypatch gRPC secure/insecure channel target routing
    try:
        import grpc
        sys.stderr.write("[BOOTSTRAP] Imported grpc: " + str(grpc) + "\n")
        if hasattr(grpc, "__file__"):
            sys.stderr.write("[BOOTSTRAP] grpc module file path: " + str(grpc.__file__) + "\n")
        sys.stderr.write("[BOOTSTRAP] grpc attributes: " + str(dir(grpc)) + "\n")
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
                        merged = (pem_str.strip() + "\n\n" + sys_str.strip()).encode("utf-8")
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
                        target = f"ipv4:{ip}:{port}"
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
                        target = f"ipv4:{ip}:{port}"
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
                            target = f"ipv4:{ip}:{port}"
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
                            target = f"ipv4:{ip}:{port}"
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
                filtered_kwargs = {k: v for k, v in kwargs.items() if k in expected_params}
                return _orig_runner_run(self, *args, **filtered_kwargs)
            Runner.run = _patched_runner_run

            _orig_runner_run_async = Runner.run_async
            async def _patched_runner_run_async(self, *args, **kwargs):
                expected_params = ["user_id", "session_id", "invocation_id", "new_message", "state_delta", "run_config"]
                filtered_kwargs = {k: v for k, v in kwargs.items() if k in expected_params}
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
                                        filtered_kwargs = {k: v for k, v in kwargs.items() if k in expected_params}
                                        return _orig_run(self, *args, **filtered_kwargs)
                                    Runner.run = _patched_run

                                    _orig_run_async = Runner.run_async
                                    async def _patched_run_async(self, *args, **kwargs):
                                        expected_params = ["user_id", "session_id", "invocation_id", "new_message", "state_delta", "run_config"]
                                        filtered_kwargs = {k: v for k, v in kwargs.items() if k in expected_params}
                                        async for event in _orig_run_async(self, *args, **filtered_kwargs):
                                            yield event
                                    Runner.run_async = _patched_run_async
                                    sys.stderr.write("[BOOTSTRAP] Successfully patched ADK Runner class!\n")
                                    sys.stderr.flush()
                            real_spec.loader = PatchedLoader(real_spec.loader)
                            return real_spec
                    except Exception as e:
                        sys.stderr.write("[BOOTSTRAP] ADKRunnerInterceptor failed: " + str(e) + "\n")
                        sys.stderr.flush()
                    finally:
                        sys.meta_path.insert(0, self)
                return None
        sys.meta_path.insert(0, ADKRunnerInterceptor())
        sys.stderr.write("[BOOTSTRAP] ADKRunnerInterceptor registered successfully!\n")
        sys.stderr.flush()
    except Exception as e:
        sys.stderr.write("[BOOTSTRAP] ADK Runner patch registration failed: " + str(e) + "\n")
        sys.stderr.flush()
# --- [END GLOBAL PROCESS ENV BOOTSTRAP] ---

"""
Eng-Coder agent — safe config loader.
Loads root_agent.yaml and passes only LlmAgentConfig-allowed fields to avoid Pydantic ValidationError.
"""
import os
import yaml
from google.adk.agents import LlmAgent
from google.adk.agents.llm_agent_config import LlmAgentConfig

DEFAULT_MODEL = "gemini-2.5-pro"
_ALLOWED_KEYS = frozenset(LlmAgentConfig.model_fields)


def _sanitize_agent_name(sanitized: dict, default: str) -> None:
    """Convert kebab-case (eng-coder) to valid Python identifier (eng_coder)."""
    name = sanitized.get("name")
    sanitized["name"] = (name if isinstance(name, str) else default).replace("-", "_")


def _safe_load_root_agent(config_path: str) -> LlmAgent:
    abs_path = os.path.abspath(config_path)
    with open(abs_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    sanitized = {k: v for k, v in data.items() if k in _ALLOWED_KEYS}
    sanitized["model"] = sanitized.get("model") or DEFAULT_MODEL
    _sanitize_agent_name(sanitized, "agentic_prism_eng_coder")
    config = LlmAgentConfig.model_validate(sanitized)
    return LlmAgent.from_config(config, abs_path)


root_agent = _safe_load_root_agent(os.path.join(os.path.dirname(__file__), "root_agent.yaml"))

from __future__ import annotations

from pathlib import Path

from conftest import RENDER_BACKEND_URL


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPO_ROOT / "web"
NEXT_CONFIG_SOURCE = (WEB_ROOT / "next.config.ts").read_text()
ROOT_LAYOUT_SOURCE = (WEB_ROOT / "app" / "layout.tsx").read_text(encoding="utf-8")
PROXY_SOURCE = (WEB_ROOT / "proxy.ts").read_text()
AUTH_FORM_SOURCE = (WEB_ROOT / "components" / "auth-form.tsx").read_text(encoding="utf-8")
TURNSTILE_SOURCE = (WEB_ROOT / "components" / "turnstile-challenge.tsx").read_text(encoding="utf-8")
FORGOT_PASSWORD_SOURCE = (WEB_ROOT / "app" / "forgot-password" / "page.tsx").read_text(encoding="utf-8")
ENV_EXAMPLE_SOURCE = (WEB_ROOT / ".env.local.example").read_text(encoding="utf-8")


def _expected_destination(api_base_url: str) -> str:
    return f"{api_base_url}/api/:path*"


def test_vercel_frontend_rewrite_fails_production_build_without_backend_url():
    assert 'source: "/api/:path*"' in NEXT_CONFIG_SOURCE
    assert "NEXT_PUBLIC_API_BASE_URL must be set for production builds so /api rewrites are always configured." in NEXT_CONFIG_SOURCE
    assert 'process.env.NODE_ENV !== "production"' in NEXT_CONFIG_SOURCE
    assert "return null;" in NEXT_CONFIG_SOURCE
    assert "throw new Error(MISSING_PRODUCTION_REWRITE_ERROR);" in NEXT_CONFIG_SOURCE
    assert 'http://127.0.0.1:8000' in NEXT_CONFIG_SOURCE
    assert '`/api/:path*`' not in NEXT_CONFIG_SOURCE


def test_vercel_frontend_rewrite_uses_configured_backend_destination():
    assert _expected_destination(RENDER_BACKEND_URL) == f"{RENDER_BACKEND_URL}/api/:path*"


def test_browser_fetches_use_same_origin_api_paths():
    api_client_source = (WEB_ROOT / "lib" / "api.ts").read_text()

    assert 'if (typeof window !== "undefined") {' in api_client_source
    assert 'return "";' in api_client_source


def test_server_side_api_client_requires_backend_url_in_production():
    api_client_source = (WEB_ROOT / "lib" / "api.ts").read_text()

    assert "NEXT_PUBLIC_API_BASE_URL must be set for server-side API calls in production." in api_client_source
    assert 'process.env.NODE_ENV !== "production"' in api_client_source
    assert 'http://127.0.0.1:8000' in api_client_source


def test_next_config_sets_baseline_security_headers():
    assert "async headers()" in NEXT_CONFIG_SOURCE
    for header_name in (
        "X-Frame-Options",
        "X-Content-Type-Options",
        "Referrer-Policy",
        "Permissions-Policy",
    ):
        assert header_name in NEXT_CONFIG_SOURCE, f"missing security header: {header_name}"
    assert "DENY" in NEXT_CONFIG_SOURCE
    assert "nosniff" in NEXT_CONFIG_SOURCE
    assert "strict-origin-when-cross-origin" in NEXT_CONFIG_SOURCE
    assert "camera=(), microphone=(), geolocation=()" in NEXT_CONFIG_SOURCE


def test_csp_uses_per_request_nonce_for_next_hydration_scripts():
    assert '{ key: "Content-Security-Policy"' not in NEXT_CONFIG_SOURCE
    assert 'export const dynamic = "force-dynamic";' in ROOT_LAYOUT_SOURCE
    assert "function buildContentSecurityPolicy" in PROXY_SOURCE
    assert "response.headers.set(\"Content-Security-Policy\", csp)" in PROXY_SOURCE
    assert "requestHeaders.set(\"Content-Security-Policy\", csp)" in PROXY_SOURCE
    assert "\"x-nonce\"" in PROXY_SOURCE
    assert "'nonce-${nonce}'" in PROXY_SOURCE
    assert "'strict-dynamic'" in PROXY_SOURCE
    assert "'unsafe-inline'" not in PROXY_SOURCE.split("script-src", 1)[1].split("style-src", 1)[0]


def test_turnstile_is_csp_allowlisted_and_optional_until_configured():
    assert "NEXT_PUBLIC_TURNSTILE_SITE_KEY" in ENV_EXAMPLE_SOURCE
    assert "NEXT_PUBLIC_TURNSTILE_SITE_KEY" in TURNSTILE_SOURCE
    assert "if (!TURNSTILE_SITE_KEY)" in TURNSTILE_SOURCE
    assert "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit" in TURNSTILE_SOURCE

    assert "https://challenges.cloudflare.com" in PROXY_SOURCE
    assert "frame-src https://challenges.cloudflare.com" in PROXY_SOURCE


def test_all_supabase_email_auth_requests_forward_turnstile_token():
    for source in (AUTH_FORM_SOURCE, FORGOT_PASSWORD_SOURCE):
        assert "TurnstileChallenge" in source
        assert "captchaToken" in source

    assert "client.auth.signUp" in AUTH_FORM_SOURCE
    assert "client.auth.signInWithPassword" in AUTH_FORM_SOURCE
    assert "client.auth.signInWithOtp" in AUTH_FORM_SOURCE
    assert "client.auth.resetPasswordForEmail" in FORGOT_PASSWORD_SOURCE


def test_delete_plan_uses_shared_request_pipeline():
    api_client_source = (WEB_ROOT / "lib" / "api.ts").read_text()
    assert "requestVoid" in api_client_source
    delete_section_start = api_client_source.find("export async function deletePlan")
    assert delete_section_start != -1
    next_export = api_client_source.find("\nexport ", delete_section_start + 1)
    delete_section = api_client_source[delete_section_start:next_export]
    assert "fetch(" not in delete_section, "deletePlan should not call fetch directly"
    assert "requestVoid" in delete_section


def test_no_public_env_var_exposes_supabase_service_role_key():
    web_lib_usage = "\n".join(p.read_text() for p in (WEB_ROOT / "lib").rglob("*") if p.is_file())
    web_env_usage = web_lib_usage + "\n" + NEXT_CONFIG_SOURCE
    assert "NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY" not in web_env_usage
    assert "SUPABASE_SERVICE_ROLE_KEY" not in web_env_usage

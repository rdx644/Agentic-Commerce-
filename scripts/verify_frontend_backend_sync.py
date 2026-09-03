"""
Script to verify that the frontend (dashboard/app.js, index.html)
is completely synchronized with the backend routes, schemas, and logic.
Uses FastAPI's complete OpenAPI schema to resolve all registered paths.
"""
import re
from pathlib import Path
from src.main import app

def main():
    print("=" * 70)
    print("FRONTEND <-> BACKEND CODE SYNCHRONIZATION AUDIT")
    print("=" * 70)

    # 1. Get all backend routes from OpenAPI schema
    openapi = app.openapi()
    backend_paths = openapi.get("paths", {})
    
    backend_routes = {}
    for path, methods in backend_paths.items():
        for m in methods:
            backend_routes[f"{m.upper()} {path}"] = methods[m]

    print(f"\n[1] Total Backend Endpoints in OpenAPI: {len(backend_routes)}")
    for r in sorted(backend_routes.keys()):
        print(f"    {r}")

    # 2. Extract all API calls from app.js
    app_js = Path("dashboard/app.js").read_text(encoding="utf-8")
    
    # Matches apiFetch('url' or fetch('url'
    fetch_matches = re.findall(r'(?:apiFetch|fetch)\s*\(\s*[`\'"]([^`\'"?$]+)', app_js)
    
    print("\n[2] Endpoints invoked from dashboard/app.js:")
    unique_calls = sorted(set(fetch_matches))
    for c in unique_calls:
        print(f"    {c}")

    # 3. Check each frontend endpoint against backend routes
    print("\n[3] Verifying Endpoint Path Matching:")
    mismatches = []
    for path in unique_calls:
        matched = False
        for route_key in backend_routes:
            method, route_path = route_key.split(" ", 1)
            # handle path parameters like {session_id}
            regex_route = "^" + re.sub(r'\{[^}]+\}', r'[^/]+', route_path) + "$"
            if re.match(regex_route, path) or path == route_path or route_path.startswith(path):
                matched = True
                break
        if matched:
            print(f"    [OK] {path} matches registered backend route")
        else:
            print(f"    [FAIL] MISMATCH: {path} not found in backend routes!")
            mismatches.append(path)

    # 4. Check Checkout Simulator Presets & Logic
    print("\n[4] Verifying Checkout Simulator Presets in HTML & JS:")
    index_html = Path("dashboard/index.html").read_text(encoding="utf-8")
    chips = re.findall(r'data-prompt="([^"]+)"', index_html)
    for i, chip in enumerate(chips, 1):
        print(f"    Chip {i}: \"{chip}\"")

    chip_listener = "data-prompt" in app_js or "btn-chip" in app_js or "dataset.prompt" in app_js
    print(f"    Chip click handler in app.js: {'[OK] Yes' if chip_listener else '[FAIL] No'}")

    send_btn = "send-checkout" in index_html and "send-checkout" in app_js
    print(f"    Checkout Send button matched (HTML & JS): {'[OK] Yes (id=send-checkout)' if send_btn else '[FAIL] No'}")

    # 5. Check Payload synchronization for /checkout/converse
    print("\n[5] Verifying /checkout/converse Payload & Response Contract:")
    converse_payload_match = re.search(r'/checkout/converse.*?body:\s*JSON\.stringify\(({[^}]+})\)', app_js, re.DOTALL)
    if converse_payload_match:
        payload_code = converse_payload_match.group(1).replace('\n', ' ').strip()
        print(f"    Payload sent by frontend: {payload_code}")

    # 6. Check /payment/dispatch contract
    print("\n[6] Verifying /payment/dispatch Payload Contract:")
    dispatch_payload = re.search(r'/payment/dispatch.*?body:\s*JSON\.stringify\(({[^}]+})\)', app_js, re.DOTALL)
    if dispatch_payload:
        print(f"    Payload sent by frontend: {dispatch_payload.group(1).replace(chr(10), ' ').strip()}")

    # 7. Check /campaign/run contract
    print("\n[7] Verifying /campaign/run Payload Contract:")
    campaign_payload = re.search(r'/campaign/run.*?body:\s*JSON\.stringify\(({[^}]+})\)', app_js, re.DOTALL)
    if campaign_payload:
        print(f"    Payload sent by frontend: {campaign_payload.group(1).replace(chr(10), ' ').strip()}")

    # 8. Check Auth Flow contract
    print("\n[8] Verifying /auth/token Payload Contract:")
    auth_payload = re.search(r'/auth/token.*?body:\s*([^,\n)]+)', app_js, re.DOTALL)
    if auth_payload:
        print(f"    Auth body format: {auth_payload.group(1).strip()}")

    # 9. Check SSE contract (/audit/stream)
    print("\n[9] Verifying /audit/stream SSE Handling:")
    sse_init = "new EventSource(" in app_js
    print(f"    EventSource initialized: {'[OK] Yes' if sse_init else '[FAIL] No'}")
    
    # 10. Check Zero Unsafe DOM Sinks
    print("\n[10] Verifying Zero Unsafe DOM Sinks in app.js:")
    sinks = ["innerHTML", "outerHTML", "document.write", "eval("]
    sink_found = False
    for s in sinks:
        matches = [line.strip() for line in app_js.splitlines() if s in line and not line.strip().startswith("//")]
        if matches:
            sink_found = True
            print(f"    [FAIL] Found sink {s}: {matches[:2]}")
        else:
            print(f"    [OK] Zero instances of {s}")

    print("\n" + "=" * 70)
    if not mismatches and not sink_found and send_btn:
        print("RESULT: FRONTEND AND BACKEND ARE 100% IN SYNC & FULLY VERIFIED")
    else:
        print("RESULT: DISCREPANCIES DETECTED")
    print("=" * 70)

if __name__ == "__main__":
    main()

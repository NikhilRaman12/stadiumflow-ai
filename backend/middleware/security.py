import time
import logging
from collections import defaultdict
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

log = logging.getLogger("stadiumiq.middleware.security")

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Enforces strict security headers (CSP, Frame options, HSTS)."""
    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)
        
        # Enforce CSP: Allow self and trusted CDNs for scripts/styles
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://unpkg.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' ws: wss:; "
            "frame-ancestors 'none';"
        )
        response.headers["Content-Security-Policy"] = csp
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
            
        return response

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory IP-based rate limiter middleware."""
    def __init__(self, app, requests_per_minute: int = 120):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        # Maps IP to list of request timestamps
        self.ip_records = defaultdict(list)

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        # Only rate limit API, WebSocket, and A2A routes
        if path.startswith("/api/") or path.startswith("/ws") or path.startswith("/a2a"):
            client_ip = request.client.host if request.client else "unknown"
            now = time.time()
            
            # Filter out timestamps older than 60 seconds
            self.ip_records[client_ip] = [t for t in self.ip_records[client_ip] if now - t < 60]
            
            if len(self.ip_records[client_ip]) >= self.requests_per_minute:
                log.warning("Rate limit exceeded for IP: %s on path: %s", client_ip, path)
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"error": "Rate limit exceeded. Maximum 120 requests per minute."}
                )
            
            self.ip_records[client_ip].append(now)
            
        return await call_next(request)

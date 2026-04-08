package proxy

import (
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"
	"time"
)

// NewReverseProxy creates an HTTP reverse proxy to the given backend URL.
func NewReverseProxy(backendURL string) (*httputil.ReverseProxy, error) {
	target, err := url.Parse(backendURL)
	if err != nil {
		return nil, err
	}

	proxy := &httputil.ReverseProxy{
		Director: func(req *http.Request) {
			req.URL.Scheme = target.Scheme
			req.URL.Host = target.Host

			// Preserve the original Host header for Flask
			// (req.Host is already set from the incoming request)

			// Set forwarding headers
			if clientIP, _, err := net.SplitHostPort(req.RemoteAddr); err == nil {
				prior := req.Header.Get("X-Forwarded-For")
				if prior != "" {
					req.Header.Set("X-Forwarded-For", prior+", "+clientIP)
				} else {
					req.Header.Set("X-Forwarded-For", clientIP)
				}
				if req.Header.Get("X-Real-IP") == "" {
					req.Header.Set("X-Real-IP", clientIP)
				}
			}

			if req.TLS != nil {
				req.Header.Set("X-Forwarded-Proto", "https")
			} else {
				req.Header.Set("X-Forwarded-Proto", "http")
			}
		},
		Transport: &http.Transport{
			DialContext:           (&net.Dialer{Timeout: 10 * time.Second}).DialContext,
			MaxIdleConns:          200,
			MaxIdleConnsPerHost:   200,
			IdleConnTimeout:       90 * time.Second,
			ResponseHeaderTimeout: 120 * time.Second,
		},
		ErrorHandler: func(w http.ResponseWriter, r *http.Request, err error) {
			log.Printf("proxy error: %s %s → %v", r.Method, r.URL.Path, err)
			http.Error(w, `{"error":"backend unavailable"}`, http.StatusBadGateway)
		},
	}
	return proxy, nil
}

// Handler returns an http.Handler that proxies requests. WebSocket upgrade
// requests are handled by the websocket proxy; all others go through httputil.
func Handler(backendURL string) http.Handler {
	rp, err := NewReverseProxy(backendURL)
	if err != nil {
		log.Fatalf("failed to create reverse proxy: %v", err)
	}
	wsProxy := NewWebSocketProxy(backendURL)

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Detect WebSocket upgrade
		if isWebSocketUpgrade(r) {
			wsProxy.ServeHTTP(w, r)
			return
		}
		rp.ServeHTTP(w, r)
	})
}

func isWebSocketUpgrade(r *http.Request) bool {
	return strings.EqualFold(r.Header.Get("Upgrade"), "websocket") &&
		strings.Contains(strings.ToLower(r.Header.Get("Connection")), "upgrade")
}

package proxy

import (
	"io"
	"log"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// WebSocketProxy does a TCP-level transparent proxy for WebSocket connections.
// This preserves the full SocketIO protocol without reimplementing it.
type WebSocketProxy struct {
	backendHost string
}

// NewWebSocketProxy creates a WebSocket proxy targeting the backend URL.
func NewWebSocketProxy(backendURL string) *WebSocketProxy {
	u, err := url.Parse(backendURL)
	if err != nil {
		log.Fatalf("invalid backend URL for websocket proxy: %v", err)
	}
	host := u.Host
	if !strings.Contains(host, ":") {
		if u.Scheme == "https" {
			host += ":443"
		} else {
			host += ":80"
		}
	}
	return &WebSocketProxy{backendHost: host}
}

func (p *WebSocketProxy) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// Hijack the client connection
	hj, ok := w.(http.Hijacker)
	if !ok {
		http.Error(w, "server does not support hijacking", http.StatusInternalServerError)
		return
	}
	clientConn, clientBuf, err := hj.Hijack()
	if err != nil {
		http.Error(w, "hijack failed: "+err.Error(), http.StatusInternalServerError)
		return
	}
	defer clientConn.Close()

	// Connect to backend
	backendConn, err := net.DialTimeout("tcp", p.backendHost, 10*time.Second)
	if err != nil {
		log.Printf("websocket proxy: cannot connect to backend %s: %v", p.backendHost, err)
		clientConn.Close()
		return
	}
	defer backendConn.Close()

	// Reconstruct the original HTTP request and forward to backend
	reqLine := r.Method + " " + r.URL.RequestURI() + " " + r.Proto + "\r\n"
	_, _ = backendConn.Write([]byte(reqLine))

	// Update Host header to backend host
	r.Header.Set("Host", p.backendHost)
	_ = r.Header.Write(backendConn)
	_, _ = backendConn.Write([]byte("\r\n"))

	// Flush any buffered data from the client
	if clientBuf.Reader.Buffered() > 0 {
		buffered := make([]byte, clientBuf.Reader.Buffered())
		_, _ = clientBuf.Read(buffered)
		_, _ = backendConn.Write(buffered)
	}

	// Bidirectional copy
	done := make(chan struct{}, 2)

	go func() {
		_, _ = io.Copy(backendConn, clientConn)
		done <- struct{}{}
	}()

	go func() {
		_, _ = io.Copy(clientConn, backendConn)
		done <- struct{}{}
	}()

	// Wait for either direction to finish
	<-done
}

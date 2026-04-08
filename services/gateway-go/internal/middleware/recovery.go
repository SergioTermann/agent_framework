package middleware

import (
	"fmt"
	"log"
	"net/http"
)

func Recovery(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if recovered := recover(); recovered != nil {
				log.Printf("gateway-go panic recovered: %v", recovered)
				http.Error(w, fmt.Sprintf(`{"error":"internal server error"}`), http.StatusInternalServerError)
			}
		}()
		next.ServeHTTP(w, r)
	})
}

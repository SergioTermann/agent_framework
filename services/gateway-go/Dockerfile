FROM golang:1.21-alpine AS build

WORKDIR /src
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /out/gateway-go ./cmd/gateway

FROM alpine:3.20

WORKDIR /app
COPY --from=build /out/gateway-go /app/gateway-go

EXPOSE 7000

ENTRYPOINT ["/app/gateway-go"]

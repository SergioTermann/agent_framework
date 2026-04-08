FROM golang:1.21-alpine AS build

WORKDIR /src
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /out/task-executor-go ./cmd/executor

FROM alpine:3.20

WORKDIR /app
COPY --from=build /out/task-executor-go /app/task-executor-go

EXPOSE 7003

ENTRYPOINT ["/app/task-executor-go"]

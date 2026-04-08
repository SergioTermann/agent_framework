.PHONY: build run clean test

BINARY := gateway
SRC := ./cmd/gateway

build:
	go build -o $(BINARY) $(SRC)

run: build
	./$(BINARY)

clean:
	rm -f $(BINARY)

test:
	go test ./...

tidy:
	go mod tidy

lint:
	golangci-lint run ./...

FROM golang:1.23-alpine AS builder
ARG GOARCH=amd64
# GOARCH= is cleared here so go install builds for the host arch (not cross-compiles),
# which fails when GOBIN is set. The cross-compilation happens in the next RUN step.
RUN GOARCH= go install go.opentelemetry.io/collector/cmd/builder@v0.118.0
WORKDIR /build
COPY builder-config.yaml .
RUN GOOS=linux GOARCH=${GOARCH} $(go env GOPATH)/bin/builder --config=builder-config.yaml

FROM golang:1.23-alpine AS builder
ARG GOARCH=amd64
# git is needed if the Go proxy doesn't have the Scaleway receiver indexed
RUN apk add --no-cache git
# GOARCH= is cleared here so go install builds for the host arch (not cross-compiles),
# which fails when GOBIN is set. The cross-compilation happens in the next RUN step.
RUN GOARCH= go install go.opentelemetry.io/collector/cmd/builder@v0.118.0
# /go/bin is the default GOPATH/bin inside the golang Docker image; builder is always installed there.
WORKDIR /build
COPY builder-config.yaml .
RUN GOOS=linux GOARCH=${GOARCH} /go/bin/builder --config=builder-config.yaml

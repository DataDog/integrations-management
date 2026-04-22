FROM golang:1.23-alpine AS builder
ARG GOARCH=amd64
RUN go install go.opentelemetry.io/collector/cmd/builder@v0.118.0
WORKDIR /build
COPY builder-config.yaml .
RUN GOOS=linux GOARCH=${GOARCH} /go/bin/builder --config=builder-config.yaml

FROM golang:1.22-alpine AS builder

WORKDIR /app
COPY go.mod go.sum* ./
RUN go mod download 2>/dev/null || go mod tidy
COPY . .
RUN CGO_ENABLED=0 go build -o auth-server .

FROM alpine:3.20
RUN apk add --no-cache ca-certificates
COPY --from=builder /app/auth-server /auth-server
EXPOSE 8080
CMD ["/auth-server"]

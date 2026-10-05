package common

import (
	"bytes"
	"encoding/json"
	"net/http"

	"github.com/gin-gonic/gin"
)

// Envelope is the single response shape of every endpoint. Field order is part of the
// contract (code, message, data) and matches the Python server.
type Envelope struct {
	Code    RetCode `json:"code"`
	Message string  `json:"message"`
	Data    any     `json:"data"`
}

// render serialises the envelope without HTML escaping, as the Python side does.
func render(env Envelope) []byte {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(env); err != nil {
		buf.Reset()
		_ = json.NewEncoder(&buf).Encode(Envelope{Code: CodeServerError, Message: "internal error"})
	}
	return bytes.TrimRight(buf.Bytes(), "\n")
}

func write(c *gin.Context, status int, env Envelope) {
	c.Data(status, "application/json; charset=utf-8", render(env))
}

// OK writes HTTP 200 with code 0.
func OK(c *gin.Context, data any) {
	write(c, http.StatusOK, Envelope{Code: CodeSuccess, Message: "", Data: data})
}

// Fail writes the given HTTP status with an error envelope and null data.
func Fail(c *gin.Context, status int, code RetCode, msg string) {
	write(c, status, Envelope{Code: code, Message: msg, Data: nil})
}

// FailWithData writes an error envelope that carries a data payload (health uses this for 503).
func FailWithData(c *gin.Context, status int, code RetCode, msg string, data any) {
	write(c, status, Envelope{Code: code, Message: msg, Data: data})
}

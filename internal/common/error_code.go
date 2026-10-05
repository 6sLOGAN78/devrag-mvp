package common

// RetCode is the envelope return code. Values equal common/constants.py RetCode.
type RetCode int

const (
	CodeSuccess             RetCode = 0
	CodeNotEffective        RetCode = 10
	CodeExceptionError      RetCode = 100
	CodeArgumentError       RetCode = 101
	CodeDataError           RetCode = 102
	CodeOperatingError      RetCode = 103
	CodeConnectionError     RetCode = 105
	CodeRunning             RetCode = 106
	CodePermissionError     RetCode = 108
	CodeAuthenticationError RetCode = 109
	CodeBadRequest          RetCode = 400
	CodeUnauthorized        RetCode = 401
	CodeForbidden           RetCode = 403
	CodeNotFound            RetCode = 404
	CodeMethodNotAllowed    RetCode = 405
	CodeConflict            RetCode = 409
	CodeServerError         RetCode = 500
	CodeServiceUnavailable  RetCode = 503
)

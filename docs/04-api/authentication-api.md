# Authentication & User Management API

## Level 1: Endpoint Specification Overview

The Authentication & User Management APIs handle user registration, credential login, password reset, captcha generation, tenant selection, and user profile retrieval.

---

## Level 2: Comprehensive API Endpoints Specification

### 1. User Email Login
- **Endpoint**: `POST /api/v1/auth/login`
- **Engine**: Go Gin (`internal/handler/user.go`)
- **Auth Level**: Unauthenticated
- **Request Body**:
  ```json
  {
    "email": "user@example.com",
    "password": "Password123!"
  }
  ```
- **Response Body**:
  ```json
  {
    "retcode": 0,
    "retmsg": "success",
    "data": {
      "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "user": {
        "id": "u-12345",
        "email": "user@example.com",
        "nickname": "John Doe"
      }
    }
  }
  ```

---

### 2. User Registration
- **Endpoint**: `POST /api/v1/users`
- **Engine**: Go Gin (`internal/handler/user.go`)
- **Auth Level**: Unauthenticated
- **Request Body**:
  ```json
  {
    "email": "newuser@example.com",
    "password": "Password123!",
    "nickname": "New User"
  }
  ```

---

### 3. Get User Info
- **Endpoint**: `GET /v1/user/info`
- **Engine**: Go Gin (`internal/handler/user.go`)
- **Auth Level**: JWT / Session Cookie (`AuthMiddleware`)
- **Response Body**:
  ```json
  {
    "retcode": 0,
    "retmsg": "success",
    "data": {
      "id": "u-12345",
      "email": "user@example.com",
      "tenant_id": "t-67890",
      "role": "owner"
    }
  }
  ```

---

### 4. Forgot Password Flow
- **Send OTP Endpoint**: `POST /api/v1/auth/password/forgot/otp`
- **Verify OTP Endpoint**: `POST /api/v1/auth/password/forgot/otp/verify`
- **Reset Password Endpoint**: `POST /api/v1/auth/password/reset`
- **Engine**: Go Gin ([`internal/router/router.go:L190`](file:///home/logan78/Desktop/ragflow/internal/router/router.go#L190))
- **Auth Level**: Unauthenticated

### Source Links

- Go User Handler: [`internal/handler/user.go`](file:///home/logan78/Desktop/ragflow/internal/handler/user.go)
- Go Router Config: [`internal/router/router.go`](file:///home/logan78/Desktop/ragflow/internal/router/router.go#L141)
- Python Auth App: [`api/apps/auth/`](file:///home/logan78/Desktop/ragflow/api/apps/auth)
- User Database Service: [`api/db/services/user_service.py`](file:///home/logan78/Desktop/ragflow/api/db/services/user_service.py#L33)

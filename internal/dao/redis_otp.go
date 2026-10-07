package dao

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

// The one-time-code primitives below keep every multi-step state change inside one Lua script, so
// parallel callers cannot step around an attempt cap or consume a code twice (T-02-75, T-02-79).

// otpIssue replaces any previous record under the key with a fresh one: hash value v, zero
// attempts, owner u and a TTL. The record is a single hash, so the replacement is atomic.
var otpIssue = redis.NewScript(`
redis.call('DEL', KEYS[1])
redis.call('HSET', KEYS[1], 'v', ARGV[1], 'a', 0, 'u', ARGV[2])
redis.call('PEXPIRE', KEYS[1], ARGV[3])
return 1
`)

// otpAttempt counts one attempt before the caller compares anything. An attempt beyond the cap
// destroys the record. It returns false when no record exists.
var otpAttempt = redis.NewScript(`
if redis.call('EXISTS', KEYS[1]) == 0 then return false end
local a = redis.call('HINCRBY', KEYS[1], 'a', 1)
if a > tonumber(ARGV[1]) then
  redis.call('DEL', KEYS[1])
  return false
end
return {redis.call('HGET', KEYS[1], 'v'), redis.call('HGET', KEYS[1], 'u'), a}
`)

// compareDelete deletes the key only while its hash value still equals the given one, so exactly one
// of several concurrent consumers wins and a replacement code is never destroyed by a stale caller.
var compareDelete = redis.NewScript(`
if redis.call('HGET', KEYS[1], 'v') == ARGV[1] then
  redis.call('DEL', KEYS[1])
  return 1
end
return 0
`)

// OTPIssue stores value (the keyed hash of a code) and its owner under key for ttl, replacing any earlier record.
func (r *Redis) OTPIssue(ctx context.Context, key, value, owner string, ttl time.Duration) error {
	if err := otpIssue.Run(ctx, r.client, []string{key}, value, owner, ttl.Milliseconds()).Err(); err != nil {
		return fmt.Errorf("redis otp issue: %T", err)
	}
	return nil
}

// OTPAttempt records one attempt against key and returns the stored value, its owner and the attempt
// number. found is false when the record is missing, expired or the cap of max attempts was exceeded.
func (r *Redis) OTPAttempt(ctx context.Context, key string, max int) (value, owner string, attempt int64, found bool, err error) {
	res, err := otpAttempt.Run(ctx, r.client, []string{key}, max).Result()
	if errors.Is(err, redis.Nil) {
		return "", "", 0, false, nil
	}
	if err != nil {
		return "", "", 0, false, fmt.Errorf("redis otp attempt: %T", err)
	}
	parts, ok := res.([]any)
	if !ok || len(parts) != 3 {
		return "", "", 0, false, errors.New("redis otp attempt: unexpected reply")
	}
	v, _ := parts[0].(string)
	u, _ := parts[1].(string)
	n, _ := parts[2].(int64)
	return v, u, n, true, nil
}

// OTPCompareDelete removes the record under key when its stored value equals value. It reports
// whether this call removed it.
func (r *Redis) OTPCompareDelete(ctx context.Context, key, value string) (bool, error) {
	n, err := compareDelete.Run(ctx, r.client, []string{key}, value).Int64()
	if err != nil {
		return false, fmt.Errorf("redis otp delete: %T", err)
	}
	return n == 1, nil
}

// SetEX stores value under key with a TTL.
func (r *Redis) SetEX(ctx context.Context, key, value string, ttl time.Duration) error {
	if err := r.client.Set(ctx, key, value, ttl).Err(); err != nil {
		return fmt.Errorf("redis set: %T", err)
	}
	return nil
}

// Get reads a string key; found is false when it is missing.
func (r *Redis) Get(ctx context.Context, key string) (string, bool, error) {
	v, err := r.client.Get(ctx, key).Result()
	if errors.Is(err, redis.Nil) {
		return "", false, nil
	}
	if err != nil {
		return "", false, fmt.Errorf("redis get: %T", err)
	}
	return v, true, nil
}

// GetDel atomically reads and removes a key, so a value can be used once.
func (r *Redis) GetDel(ctx context.Context, key string) (string, bool, error) {
	v, err := r.client.GetDel(ctx, key).Result()
	if errors.Is(err, redis.Nil) {
		return "", false, nil
	}
	if err != nil {
		return "", false, fmt.Errorf("redis getdel: %T", err)
	}
	return v, true, nil
}

// TTL returns the remaining lifetime of key (negative when it has none or does not exist).
func (r *Redis) TTL(ctx context.Context, key string) (time.Duration, error) {
	d, err := r.client.PTTL(ctx, key).Result()
	if err != nil {
		return 0, fmt.Errorf("redis pttl: %T", err)
	}
	return d, nil
}

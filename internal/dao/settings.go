package dao

import (
	"context"
	"errors"
)

// ErrSettingNotFound is returned when system_settings has no row with the requested name.
var ErrSettingNotFound = errors.New("setting not found")

// GetSetting reads one value from system_settings using a bound parameter.
func (d *DB) GetSetting(ctx context.Context, name string) (string, error) {
	var value string
	res := d.gorm.WithContext(ctx).Table("system_settings").Select("value").Where("name = ?", name).Limit(1).Scan(&value)
	if res.Error != nil {
		return "", res.Error
	}
	if res.RowsAffected == 0 {
		return "", ErrSettingNotFound
	}
	return value, nil
}

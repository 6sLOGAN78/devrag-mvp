package dao

import (
	"context"
	"fmt"
	"reflect"
	"sort"
	"strings"
	"sync"

	"gorm.io/gorm/schema"
)

// SELECT-only metadata queries. Values are bound parameters; the verifier never writes (D-10).
const (
	queryTables  = "SELECT table_name AS table_name FROM information_schema.tables WHERE table_schema = DATABASE()"
	queryColumns = "SELECT table_name AS table_name, column_name AS column_name, data_type AS data_type FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name IN ?"
)

// ColumnInfo is one information_schema.columns row.
type ColumnInfo struct {
	Table    string
	Name     string
	DataType string
}

// SchemaProvider reads database metadata. Implementations must be read-only.
type SchemaProvider interface {
	Tables(ctx context.Context) ([]string, error)
	Columns(ctx context.Context, tables []string) ([]ColumnInfo, error)
}

type infoSchemaProvider struct{ db *DB }

type tableRow struct {
	TableName string `gorm:"column:table_name"`
}

type columnRow struct {
	TableName  string `gorm:"column:table_name"`
	ColumnName string `gorm:"column:column_name"`
	DataType   string `gorm:"column:data_type"`
}

func (p infoSchemaProvider) Tables(ctx context.Context) ([]string, error) {
	var rows []tableRow
	if err := p.db.gorm.WithContext(ctx).Raw(queryTables).Scan(&rows).Error; err != nil {
		return nil, fmt.Errorf("read tables: %w", sanitize(err))
	}
	out := make([]string, len(rows))
	for i, r := range rows {
		out[i] = r.TableName
	}
	return out, nil
}

func (p infoSchemaProvider) Columns(ctx context.Context, tables []string) ([]ColumnInfo, error) {
	if len(tables) == 0 {
		return nil, nil
	}
	var rows []columnRow
	if err := p.db.gorm.WithContext(ctx).Raw(queryColumns, tables).Scan(&rows).Error; err != nil {
		return nil, fmt.Errorf("read columns: %w", sanitize(err))
	}
	out := make([]ColumnInfo, len(rows))
	for i, r := range rows {
		out[i] = ColumnInfo{Table: r.TableName, Name: r.ColumnName, DataType: strings.ToLower(r.DataType)}
	}
	return out, nil
}

// SchemaProvider returns the read-only information_schema provider for this database.
func (d *DB) SchemaProvider() SchemaProvider { return infoSchemaProvider{db: d} }

// DriftReport lists every difference between the entities and the live schema.
type DriftReport struct {
	Tables        int
	MissingTables []string
	MissingCols   []string // table.column present in the entity, absent in the database
	ExtraCols     []string // table.column present in the database, absent in the entity
	TypeMismatch  []string // table.column: entity family vs database type
}

// Err is non-nil when any drift exists.
func (r DriftReport) Err() error {
	items := r.Items()
	if len(items) == 0 {
		return nil
	}
	return fmt.Errorf("schema drift (%d items):\n  %s", len(items), strings.Join(items, "\n  "))
}

// Items flattens the report into one line per difference.
func (r DriftReport) Items() []string {
	var out []string
	for _, t := range r.MissingTables {
		out = append(out, "missing table "+t)
	}
	for _, c := range r.MissingCols {
		out = append(out, "missing column "+c)
	}
	for _, c := range r.ExtraCols {
		out = append(out, "extra column "+c)
	}
	for _, c := range r.TypeMismatch {
		out = append(out, "type mismatch "+c)
	}
	return out
}

var typeFamilies = map[string]string{
	"char": "string", "varchar": "string", "tinytext": "string", "text": "string", "mediumtext": "string", "longtext": "string",
	"tinyint": "int", "smallint": "int", "mediumint": "int", "int": "int", "bigint": "int",
	"float": "float", "double": "float", "decimal": "float",
	"datetime": "time", "timestamp": "time", "date": "time",
}

func entityFamily(f *schema.Field) string {
	switch f.DataType {
	case schema.Bool:
		return "int" // tinyint(1)
	case schema.Int, schema.Uint:
		return "int"
	case schema.Float:
		return "float"
	case schema.String:
		return "string"
	case schema.Time:
		return "time"
	}
	return string(f.DataType)
}

// VerifySchema compares GORM-parsed entity schemas with information_schema. It issues SELECTs only.
func VerifySchema(ctx context.Context, p SchemaProvider, models []any) (DriftReport, error) {
	var rep DriftReport
	cache := &sync.Map{}
	existing, err := p.Tables(ctx)
	if err != nil {
		return rep, err
	}
	have := make(map[string]bool, len(existing))
	for _, t := range existing {
		have[t] = true
	}
	parsed := make(map[string]*schema.Schema, len(models))
	var names []string
	for _, m := range models {
		s, err := schema.Parse(m, cache, schema.NamingStrategy{})
		if err != nil {
			return rep, fmt.Errorf("parse entity %T: %w", m, err)
		}
		parsed[s.Table] = s
		names = append(names, s.Table)
	}
	sort.Strings(names)
	rep.Tables = len(names)
	var present []string
	for _, n := range names {
		if have[n] {
			present = append(present, n)
		} else {
			rep.MissingTables = append(rep.MissingTables, n)
		}
	}
	cols, err := p.Columns(ctx, present)
	if err != nil {
		return rep, err
	}
	dbCols := map[string]map[string]string{}
	for _, c := range cols {
		if dbCols[c.Table] == nil {
			dbCols[c.Table] = map[string]string{}
		}
		dbCols[c.Table][c.Name] = c.DataType
	}
	for _, n := range present {
		s := parsed[n]
		seen := map[string]bool{}
		for _, f := range s.Fields {
			if f.DBName == "" {
				continue
			}
			seen[f.DBName] = true
			dt, ok := dbCols[n][f.DBName]
			if !ok {
				rep.MissingCols = append(rep.MissingCols, n+"."+f.DBName)
				continue
			}
			if fam, known := typeFamilies[dt]; !known || fam != entityFamily(f) {
				rep.TypeMismatch = append(rep.TypeMismatch, fmt.Sprintf("%s.%s: entity %s (%s), database %s", n, f.DBName, entityFamily(f), reflect.TypeOf(reflect.New(f.FieldType).Elem().Interface()), dt))
			}
		}
		var extras []string
		for c := range dbCols[n] {
			if !seen[c] {
				extras = append(extras, n+"."+c)
			}
		}
		sort.Strings(extras)
		rep.ExtraCols = append(rep.ExtraCols, extras...)
	}
	return rep, nil
}

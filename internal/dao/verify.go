package dao

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"sort"
	"strings"
)

// SELECT-only metadata queries. Values are bound parameters; the verifier never writes (D-10).
const (
	queryTables  = "SELECT table_name AS table_name FROM information_schema.tables WHERE table_schema = DATABASE()"
	queryColumns = "SELECT table_name AS table_name, column_name AS column_name, column_type AS column_type, is_nullable AS is_nullable, column_default AS column_default, column_key AS column_key FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name IN ?"
	queryIndexes = "SELECT table_name AS table_name, index_name AS index_name, column_name AS column_name, seq_in_index AS seq_in_index, non_unique AS non_unique FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name IN ?"
)

// ColumnDef is one column of conf/schema.json (the Peewee export, the single source of truth).
type ColumnDef struct {
	Name       string  `json:"name"`
	Type       string  `json:"type"`
	Nullable   bool    `json:"nullable"`
	Default    *string `json:"default"`
	PrimaryKey bool    `json:"primary_key"`
}

// IndexDef is one secondary index of conf/schema.json.
type IndexDef struct {
	Name    string   `json:"name"`
	Columns []string `json:"columns"`
	Unique  bool     `json:"unique"`
}

// TableDef is one table of conf/schema.json.
type TableDef struct {
	Name    string      `json:"name"`
	Columns []ColumnDef `json:"columns"`
	Indexes []IndexDef  `json:"indexes"`
}

// SchemaDef is the parsed conf/schema.json.
type SchemaDef struct {
	Tables []TableDef `json:"tables"`
}

// LoadSchemaDef parses the Peewee schema export.
func LoadSchemaDef(raw []byte) (SchemaDef, error) {
	var d SchemaDef
	if err := json.Unmarshal(raw, &d); err != nil {
		return d, fmt.Errorf("parse schema definition: %w", err)
	}
	if len(d.Tables) == 0 {
		return d, errors.New("schema definition has no tables")
	}
	return d, nil
}

// ColumnInfo is one information_schema.columns row.
type ColumnInfo struct {
	Table      string
	Name       string
	ColumnType string // full definition, e.g. varchar(32), bigint unsigned
	Nullable   bool
	HasDefault bool
	Key        string // PRI, UNI, MUL or empty
}

// IndexInfo is one information_schema.statistics row (one column of one index).
type IndexInfo struct {
	Table  string
	Name   string
	Column string
	Seq    int
	Unique bool
}

// SchemaProvider reads database metadata. Implementations must be read-only.
type SchemaProvider interface {
	Tables(ctx context.Context) ([]string, error)
	Columns(ctx context.Context, tables []string) ([]ColumnInfo, error)
	Indexes(ctx context.Context, tables []string) ([]IndexInfo, error)
}

type infoSchemaProvider struct{ db *DB }

type tableRow struct {
	TableName string `gorm:"column:table_name"`
}

type columnRow struct {
	TableName     string  `gorm:"column:table_name"`
	ColumnName    string  `gorm:"column:column_name"`
	ColumnType    string  `gorm:"column:column_type"`
	IsNullable    string  `gorm:"column:is_nullable"`
	ColumnDefault *string `gorm:"column:column_default"`
	ColumnKey     string  `gorm:"column:column_key"`
}

type indexRow struct {
	TableName  string `gorm:"column:table_name"`
	IndexName  string `gorm:"column:index_name"`
	ColumnName string `gorm:"column:column_name"`
	SeqInIndex int    `gorm:"column:seq_in_index"`
	NonUnique  int    `gorm:"column:non_unique"`
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
		out[i] = ColumnInfo{
			Table: r.TableName, Name: r.ColumnName, ColumnType: r.ColumnType,
			Nullable: strings.EqualFold(r.IsNullable, "YES"), HasDefault: r.ColumnDefault != nil, Key: r.ColumnKey,
		}
	}
	return out, nil
}

func (p infoSchemaProvider) Indexes(ctx context.Context, tables []string) ([]IndexInfo, error) {
	if len(tables) == 0 {
		return nil, nil
	}
	var rows []indexRow
	if err := p.db.gorm.WithContext(ctx).Raw(queryIndexes, tables).Scan(&rows).Error; err != nil {
		return nil, fmt.Errorf("read indexes: %w", sanitize(err))
	}
	out := make([]IndexInfo, len(rows))
	for i, r := range rows {
		out[i] = IndexInfo{Table: r.TableName, Name: r.IndexName, Column: r.ColumnName, Seq: r.SeqInIndex, Unique: r.NonUnique == 0}
	}
	return out, nil
}

// SchemaProvider returns the read-only information_schema provider for this database.
func (d *DB) SchemaProvider() SchemaProvider { return infoSchemaProvider{db: d} }

// DriftReport lists every difference between conf/schema.json and the live schema.
type DriftReport struct {
	Tables          int
	MissingTables   []string
	MissingCols     []string // table.column defined in schema.json, absent in the database
	ExtraCols       []string // table.column present in the database, absent in schema.json
	TypeMismatch    []string // table.column: full column type (family, length, precision, unsigned)
	NullMismatch    []string // table.column: nullability
	DefaultMismatch []string // table.column: default present or absent
	KeyMismatch     []string // primary key and index membership, uniqueness
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
	add := func(prefix string, xs []string) {
		for _, x := range xs {
			out = append(out, prefix+x)
		}
	}
	add("missing table ", r.MissingTables)
	add("missing column ", r.MissingCols)
	add("extra column ", r.ExtraCols)
	add("type mismatch ", r.TypeMismatch)
	add("nullability mismatch ", r.NullMismatch)
	add("default mismatch ", r.DefaultMismatch)
	add("key mismatch ", r.KeyMismatch)
	return out
}

var intDisplayWidth = regexp.MustCompile(`^((?:tiny|small|medium|big)?int)\((\d+)\)`)

// normaliseType lowercases and removes the integer display width MySQL 5.7 printed but 8.0.19+
// does not, except tinyint(1), which MySQL keeps and Peewee's boolean maps to.
func normaliseType(t string) string {
	t = strings.Join(strings.Fields(strings.ToLower(t)), " ")
	if m := intDisplayWidth.FindStringSubmatch(t); m != nil && !(m[1] == "tinyint" && m[2] == "1") {
		t = m[1] + strings.TrimPrefix(t, m[0])
	}
	return t
}

// sortedCopy is used for primary keys: schema.json lists columns in table order, not key order,
// so key membership is compared as a set.
func sortedCopy(in []string) []string {
	out := append([]string(nil), in...)
	sort.Strings(out)
	return out
}

func joinCols(cols []string) string { return strings.Join(cols, ", ") }

// VerifySchema compares conf/schema.json with information_schema: table and column presence, the
// full column type, nullability, default presence, primary key and index membership. It issues
// SELECTs only and reports every difference in one DriftReport.
func VerifySchema(ctx context.Context, p SchemaProvider, def SchemaDef) (DriftReport, error) {
	var rep DriftReport
	existing, err := p.Tables(ctx)
	if err != nil {
		return rep, err
	}
	have := make(map[string]bool, len(existing))
	for _, t := range existing {
		have[t] = true
	}
	tables := append([]TableDef(nil), def.Tables...)
	sort.Slice(tables, func(i, j int) bool { return tables[i].Name < tables[j].Name })
	rep.Tables = len(tables)
	var present []string
	for _, t := range tables {
		if have[t.Name] {
			present = append(present, t.Name)
		} else {
			rep.MissingTables = append(rep.MissingTables, t.Name)
		}
	}
	cols, err := p.Columns(ctx, present)
	if err != nil {
		return rep, err
	}
	idx, err := p.Indexes(ctx, present)
	if err != nil {
		return rep, err
	}
	dbCols := map[string]map[string]ColumnInfo{}
	for _, c := range cols {
		if dbCols[c.Table] == nil {
			dbCols[c.Table] = map[string]ColumnInfo{}
		}
		dbCols[c.Table][c.Name] = c
	}
	type idxKey struct{ table, name string }
	type idxShape struct {
		cols   map[int]string
		unique bool
	}
	dbIdx := map[idxKey]*idxShape{}
	for _, i := range idx {
		k := idxKey{i.Table, i.Name}
		if dbIdx[k] == nil {
			dbIdx[k] = &idxShape{cols: map[int]string{}, unique: i.Unique}
		}
		dbIdx[k].cols[i.Seq] = i.Column
	}
	ordered := func(s *idxShape) []string {
		keys := make([]int, 0, len(s.cols))
		for k := range s.cols {
			keys = append(keys, k)
		}
		sort.Ints(keys)
		out := make([]string, len(keys))
		for i, k := range keys {
			out[i] = s.cols[k]
		}
		return out
	}
	for _, t := range tables {
		if !have[t.Name] {
			continue
		}
		seen := map[string]bool{}
		var pk []string
		for _, c := range t.Columns {
			seen[c.Name] = true
			ref := t.Name + "." + c.Name
			got, ok := dbCols[t.Name][c.Name]
			if !ok {
				rep.MissingCols = append(rep.MissingCols, ref)
				continue
			}
			if want, have := normaliseType(c.Type), normaliseType(got.ColumnType); want != have {
				rep.TypeMismatch = append(rep.TypeMismatch, fmt.Sprintf("%s: schema.json %s, database %s", ref, want, have))
			}
			if c.Nullable != got.Nullable {
				rep.NullMismatch = append(rep.NullMismatch, fmt.Sprintf("%s: schema.json nullable=%t, database nullable=%t", ref, c.Nullable, got.Nullable))
			}
			if (c.Default != nil) != got.HasDefault {
				rep.DefaultMismatch = append(rep.DefaultMismatch, fmt.Sprintf("%s: schema.json has default=%t, database has default=%t", ref, c.Default != nil, got.HasDefault))
			}
			if c.PrimaryKey {
				pk = append(pk, c.Name)
			}
			if c.PrimaryKey != (got.Key == "PRI") {
				rep.KeyMismatch = append(rep.KeyMismatch, fmt.Sprintf("%s: schema.json primary_key=%t, database key=%q", ref, c.PrimaryKey, got.Key))
			}
		}
		var extras []string
		for name := range dbCols[t.Name] {
			if !seen[name] {
				extras = append(extras, t.Name+"."+name)
			}
		}
		sort.Strings(extras)
		rep.ExtraCols = append(rep.ExtraCols, extras...)

		// Primary-key membership (a set; see sortedCopy) and every declared secondary index.
		if len(pk) > 0 {
			if s := dbIdx[idxKey{t.Name, "PRIMARY"}]; s == nil || joinCols(sortedCopy(ordered(s))) != joinCols(sortedCopy(pk)) {
				got := "none"
				if s != nil {
					got = joinCols(ordered(s))
				}
				rep.KeyMismatch = append(rep.KeyMismatch, fmt.Sprintf("%s primary key: schema.json (%s), database (%s)", t.Name, joinCols(pk), got))
			}
		}
		for _, ix := range t.Indexes {
			found, uniqueMismatch := false, false
			for k, s := range dbIdx {
				if k.table != t.Name || k.name == "PRIMARY" || joinCols(ordered(s)) != joinCols(ix.Columns) {
					continue
				}
				if s.unique == ix.Unique {
					found, uniqueMismatch = true, false
					break
				}
				uniqueMismatch = true
			}
			switch {
			case found:
			case uniqueMismatch:
				rep.KeyMismatch = append(rep.KeyMismatch, fmt.Sprintf("%s index (%s): schema.json unique=%t, database unique=%t", t.Name, joinCols(ix.Columns), ix.Unique, !ix.Unique))
			default:
				rep.KeyMismatch = append(rep.KeyMismatch, fmt.Sprintf("%s missing index (%s) unique=%t", t.Name, joinCols(ix.Columns), ix.Unique))
			}
		}
	}
	return rep, nil
}

package dao

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"sync"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"gorm.io/gorm/schema"

	"devrag/internal/entity"
)

type probe struct {
	ID    string `gorm:"column:id;primaryKey"`
	Count int32  `gorm:"column:count"`
	Seen  *int64 `gorm:"column:seen"`
}

func (probe) TableName() string { return "probe" }

type fakeProvider struct {
	tables []string
	cols   []ColumnInfo
}

func (f fakeProvider) Tables(context.Context) ([]string, error) { return f.tables, nil }
func (f fakeProvider) Columns(_ context.Context, tables []string) ([]ColumnInfo, error) {
	var out []ColumnInfo
	for _, c := range f.cols {
		for _, t := range tables {
			if c.Table == t {
				out = append(out, c)
			}
		}
	}
	return out, nil
}

func goodCols() []ColumnInfo {
	return []ColumnInfo{
		{Table: "probe", Name: "id", DataType: "varchar"},
		{Table: "probe", Name: "count", DataType: "int"},
		{Table: "probe", Name: "seen", DataType: "bigint"},
	}
}

func verify(t *testing.T, p fakeProvider) DriftReport {
	t.Helper()
	rep, err := VerifySchema(context.Background(), p, []any{probe{}})
	require.NoError(t, err)
	return rep
}

func TestVerifyCleanSchema(t *testing.T) {
	rep := verify(t, fakeProvider{tables: []string{"probe", "unrelated"}, cols: goodCols()})
	assert.NoError(t, rep.Err())
	assert.Equal(t, 1, rep.Tables)
}

func TestVerifyMissingTable(t *testing.T) {
	rep := verify(t, fakeProvider{tables: nil})
	assert.Equal(t, []string{"probe"}, rep.MissingTables)
	assert.ErrorContains(t, rep.Err(), "missing table probe")
}

func TestVerifyMissingColumn(t *testing.T) {
	rep := verify(t, fakeProvider{tables: []string{"probe"}, cols: goodCols()[:2]})
	assert.Equal(t, []string{"probe.seen"}, rep.MissingCols)
	assert.ErrorContains(t, rep.Err(), "probe.seen")
}

func TestVerifyExtraColumn(t *testing.T) {
	cols := append(goodCols(), ColumnInfo{Table: "probe", Name: "stray", DataType: "int"})
	rep := verify(t, fakeProvider{tables: []string{"probe"}, cols: cols})
	assert.Equal(t, []string{"probe.stray"}, rep.ExtraCols)
}

func TestVerifyTypeFamilyMismatch(t *testing.T) {
	cols := goodCols()
	cols[1].DataType = "varchar"
	rep := verify(t, fakeProvider{tables: []string{"probe"}, cols: cols})
	require.Len(t, rep.TypeMismatch, 1)
	assert.Contains(t, rep.TypeMismatch[0], "probe.count")
}

func TestVerifyTypeWithinFamilyIsAccepted(t *testing.T) {
	cols := goodCols()
	cols[1].DataType = "bigint" // int family
	cols[0].DataType = "longtext"
	assert.NoError(t, verify(t, fakeProvider{tables: []string{"probe"}, cols: cols}).Err())
}

func TestMetadataQueriesAreSelectOnlyAndParameterised(t *testing.T) {
	for _, q := range []string{queryTables, queryColumns} {
		assert.True(t, strings.HasPrefix(strings.ToUpper(q), "SELECT "), q)
		for _, verb := range []string{"INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "CREATE", "TRUNCATE"} {
			assert.NotContains(t, strings.ToUpper(q), verb+" ", q)
		}
		assert.NotContains(t, q, "'", "no inlined literals")
	}
	assert.Contains(t, queryColumns, "IN ?")
}

type schemaJSON struct {
	Tables []struct {
		Name    string `json:"name"`
		Columns []struct {
			Name     string `json:"name"`
			Nullable bool   `json:"nullable"`
		} `json:"columns"`
	} `json:"tables"`
}

func repoRoot(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	require.NoError(t, err)
	for {
		if _, err := os.Stat(filepath.Join(dir, "go.mod")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		require.NotEqual(t, dir, parent, "go.mod not found above test directory")
		dir = parent
	}
}

// TestEntitiesMatchSchemaJSON proves, without a database, that the generated GORM entities carry
// exactly the tables, ordered columns and nullability of conf/schema.json (DATA-06).
func TestEntitiesMatchSchemaJSON(t *testing.T) {
	raw, err := os.ReadFile(filepath.Join(repoRoot(t), "conf", "schema.json"))
	require.NoError(t, err)
	var want schemaJSON
	require.NoError(t, json.Unmarshal(raw, &want))
	models := entity.All()
	require.Len(t, models, len(want.Tables))
	byTable := map[string]*schema.Schema{}
	for _, m := range models {
		s, err := schema.Parse(m, &sync.Map{}, schema.NamingStrategy{})
		require.NoError(t, err)
		byTable[s.Table] = s
	}
	for _, tbl := range want.Tables {
		s, ok := byTable[tbl.Name]
		require.True(t, ok, "no entity for table %s", tbl.Name)
		var gotNames []string
		nullable := map[string]bool{}
		for _, f := range s.Fields {
			if f.DBName == "" {
				continue
			}
			gotNames = append(gotNames, f.DBName)
			nullable[f.DBName] = f.FieldType.Kind() == reflect.Ptr
		}
		var wantNames []string
		for _, c := range tbl.Columns {
			wantNames = append(wantNames, c.Name)
		}
		assert.Equal(t, wantNames, gotNames, "columns of %s", tbl.Name)
		for _, c := range tbl.Columns {
			assert.Equal(t, c.Nullable, nullable[c.Name], "nullability of %s.%s", tbl.Name, c.Name)
		}
	}
}

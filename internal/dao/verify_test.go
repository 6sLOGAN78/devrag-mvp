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

	"devrag/conf"
	"devrag/internal/entity"
)

type fakeProvider struct {
	tables  []string
	cols    []ColumnInfo
	indexes []IndexInfo
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
func (f fakeProvider) Indexes(_ context.Context, tables []string) ([]IndexInfo, error) {
	var out []IndexInfo
	for _, i := range f.indexes {
		for _, t := range tables {
			if i.Table == t {
				out = append(out, i)
			}
		}
	}
	return out, nil
}

func probeDef() SchemaDef {
	return SchemaDef{Tables: []TableDef{{
		Name: "probe",
		Columns: []ColumnDef{
			{Name: "id", Type: "varchar(32)", Nullable: false, PrimaryKey: true},
			{Name: "count", Type: "int", Nullable: false, Default: strPtr("0")},
			{Name: "seen", Type: "bigint", Nullable: true},
		},
		Indexes: []IndexDef{{Name: "probe_seen", Columns: []string{"seen"}}, {Name: "probe_id_count", Columns: []string{"id", "count"}, Unique: true}},
	}}}
}

func strPtr(s string) *string { return &s }

func goodProvider() fakeProvider {
	return fakeProvider{
		tables: []string{"probe", "unrelated"},
		cols: []ColumnInfo{
			{Table: "probe", Name: "id", ColumnType: "varchar(32)", Nullable: false, Key: "PRI"},
			{Table: "probe", Name: "count", ColumnType: "int", Nullable: false, HasDefault: true},
			{Table: "probe", Name: "seen", ColumnType: "bigint", Nullable: true, Key: "MUL"},
		},
		indexes: []IndexInfo{
			{Table: "probe", Name: "PRIMARY", Column: "id", Seq: 1, Unique: true},
			{Table: "probe", Name: "probe_seen", Column: "seen", Seq: 1},
			{Table: "probe", Name: "probe_id_count", Column: "id", Seq: 1, Unique: true},
			{Table: "probe", Name: "probe_id_count", Column: "count", Seq: 2, Unique: true},
		},
	}
}

func verify(t *testing.T, p fakeProvider) DriftReport {
	t.Helper()
	rep, err := VerifySchema(context.Background(), p, probeDef())
	require.NoError(t, err)
	return rep
}

func TestVerifyCleanSchema(t *testing.T) {
	rep := verify(t, goodProvider())
	assert.NoError(t, rep.Err())
	assert.Equal(t, 1, rep.Tables)
}

func TestVerifyMissingTable(t *testing.T) {
	rep := verify(t, fakeProvider{})
	assert.Equal(t, []string{"probe"}, rep.MissingTables)
	assert.ErrorContains(t, rep.Err(), "missing table probe")
}

func TestVerifyMissingColumn(t *testing.T) {
	p := goodProvider()
	p.cols = p.cols[:2]
	rep := verify(t, p)
	assert.Equal(t, []string{"probe.seen"}, rep.MissingCols)
	assert.ErrorContains(t, rep.Err(), "probe.seen")
}

func TestVerifyExtraColumn(t *testing.T) {
	p := goodProvider()
	p.cols = append(p.cols, ColumnInfo{Table: "probe", Name: "stray", ColumnType: "int"})
	assert.Equal(t, []string{"probe.stray"}, verify(t, p).ExtraCols)
}

func TestVerifyTypeFamilyMismatch(t *testing.T) {
	p := goodProvider()
	p.cols[1].ColumnType = "varchar(10)"
	rep := verify(t, p)
	require.Len(t, rep.TypeMismatch, 1)
	assert.Contains(t, rep.TypeMismatch[0], "probe.count")
}

// WR-10: the family-only check accepted every one of the cases below.
func TestVerifyTypeWithinFamilyIsRejected(t *testing.T) {
	p := goodProvider()
	p.cols[1].ColumnType = "bigint" // same family as int
	p.cols[0].ColumnType = "longtext"
	rep := verify(t, p)
	assert.Len(t, rep.TypeMismatch, 2)
}

func TestVerifyLengthDifference(t *testing.T) {
	p := goodProvider()
	p.cols[0].ColumnType = "varchar(16)"
	rep := verify(t, p)
	require.Len(t, rep.TypeMismatch, 1)
	assert.Contains(t, rep.TypeMismatch[0], "probe.id")
	assert.Contains(t, rep.TypeMismatch[0], "varchar(32)")
	assert.Contains(t, rep.TypeMismatch[0], "varchar(16)")
}

func TestVerifyNullabilityDifference(t *testing.T) {
	p := goodProvider()
	p.cols[2].Nullable = false
	rep := verify(t, p)
	require.Len(t, rep.NullMismatch, 1)
	assert.ErrorContains(t, rep.Err(), "nullability mismatch probe.seen")
}

func TestVerifyDefaultPresenceDifference(t *testing.T) {
	p := goodProvider()
	p.cols[1].HasDefault = false
	rep := verify(t, p)
	require.Len(t, rep.DefaultMismatch, 1)
	assert.Contains(t, rep.DefaultMismatch[0], "probe.count")
}

func TestVerifyPrimaryKeyDifference(t *testing.T) {
	p := goodProvider()
	p.cols[0].Key = ""
	rep := verify(t, p)
	require.Len(t, rep.KeyMismatch, 1)
	assert.Contains(t, rep.KeyMismatch[0], "probe.id")
}

func TestVerifyMissingIndex(t *testing.T) {
	p := goodProvider()
	p.indexes = p.indexes[:2] // drops probe_id_count
	rep := verify(t, p)
	require.Len(t, rep.KeyMismatch, 1)
	assert.Contains(t, rep.KeyMismatch[0], "id, count")
}

func TestVerifyIndexUniquenessDifference(t *testing.T) {
	p := goodProvider()
	p.indexes[2].Unique = false
	p.indexes[3].Unique = false
	rep := verify(t, p)
	require.Len(t, rep.KeyMismatch, 1)
	assert.Contains(t, rep.KeyMismatch[0], "unique")
}

func TestVerifyNormalisesIntegerDisplayWidth(t *testing.T) {
	p := goodProvider()
	p.cols[1].ColumnType = "INT(11)"
	assert.NoError(t, verify(t, p).Err())
}

func TestVerifyReportsEveryDifferenceAtOnce(t *testing.T) {
	p := goodProvider()
	p.cols[0].ColumnType = "varchar(16)"
	p.cols[2].Nullable = false
	p.cols[1].HasDefault = false
	rep := verify(t, p)
	assert.Len(t, rep.Items(), 3)
}

func TestEmbeddedSchemaMatchesFile(t *testing.T) {
	raw, err := os.ReadFile(filepath.Join(repoRoot(t), "conf", "schema.json"))
	require.NoError(t, err)
	assert.Equal(t, raw, conf.SchemaJSON)
	def, err := LoadSchemaDef(conf.SchemaJSON)
	require.NoError(t, err)
	assert.Len(t, def.Tables, len(entity.All()))
}

func TestLoadSchemaDefRejectsGarbage(t *testing.T) {
	_, err := LoadSchemaDef([]byte("not json"))
	assert.Error(t, err)
	_, err = LoadSchemaDef([]byte(`{"tables":[]}`))
	assert.Error(t, err)
}

func TestMetadataQueriesAreSelectOnlyAndParameterised(t *testing.T) {
	for _, q := range []string{queryTables, queryColumns, queryIndexes} {
		assert.True(t, strings.HasPrefix(strings.ToUpper(q), "SELECT "), q)
		for _, verb := range []string{"INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "CREATE", "TRUNCATE"} {
			assert.NotContains(t, strings.ToUpper(q), verb+" ", q)
		}
		assert.NotContains(t, q, "'", "no inlined literals")
	}
	assert.Contains(t, queryColumns, "IN ?")
	assert.Contains(t, queryIndexes, "IN ?")
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

func TestVerifyPrimaryKeyMembershipIgnoresExportOrder(t *testing.T) {
	def := SchemaDef{Tables: []TableDef{{Name: "t", Columns: []ColumnDef{
		{Name: "a", Type: "int", PrimaryKey: true}, {Name: "b", Type: "int", PrimaryKey: true},
	}}}}
	p := fakeProvider{
		tables:  []string{"t"},
		cols:    []ColumnInfo{{Table: "t", Name: "a", ColumnType: "int", Key: "PRI"}, {Table: "t", Name: "b", ColumnType: "int", Key: "PRI"}},
		indexes: []IndexInfo{{Table: "t", Name: "PRIMARY", Column: "b", Seq: 1, Unique: true}, {Table: "t", Name: "PRIMARY", Column: "a", Seq: 2, Unique: true}},
	}
	rep, err := VerifySchema(context.Background(), p, def)
	require.NoError(t, err)
	assert.NoError(t, rep.Err())
}

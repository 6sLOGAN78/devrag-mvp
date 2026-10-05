package dao

import (
	"context"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
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

package internal_test

import (
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

const mod = "devrag/internal/"

// imports returns every import path used by the non-test files of one package directory.
func imports(t *testing.T, dir string) []string {
	t.Helper()
	entries, err := os.ReadDir(dir)
	require.NoError(t, err)
	fset := token.NewFileSet()
	var out []string
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".go") || strings.HasSuffix(e.Name(), "_test.go") {
			continue
		}
		f, err := parser.ParseFile(fset, filepath.Join(dir, e.Name()), nil, parser.ImportsOnly)
		require.NoError(t, err)
		for _, imp := range f.Imports {
			p, err := strconv.Unquote(imp.Path.Value)
			require.NoError(t, err)
			out = append(out, p)
		}
	}
	return out
}

func forbidden(t *testing.T, pkg string, banned ...string) {
	t.Helper()
	for _, imp := range imports(t, pkg) {
		for _, b := range banned {
			assert.Falsef(t, imp == b || strings.HasPrefix(imp, b+"/"), "internal/%s must not import %s", pkg, imp)
		}
	}
}

func required(t *testing.T, pkg string, want string) {
	t.Helper()
	assert.Contains(t, imports(t, pkg), want, "internal/%s must import %s", pkg, want)
}

func TestRouterOnlyReachesHandlers(t *testing.T) {
	required(t, "router", mod+"handler")
	forbidden(t, "router", mod+"service", mod+"dao", "gorm.io/gorm", "github.com/redis/go-redis/v9")
}

func TestHandlerCallsServiceNotStorage(t *testing.T) {
	required(t, "handler", mod+"service")
	required(t, "handler", mod+"common")
	forbidden(t, "handler", mod+"dao", mod+"router", "gorm.io/gorm", "gorm.io/driver/mysql", "github.com/redis/go-redis/v9")
}

func TestServiceUsesDAONotTransport(t *testing.T) {
	required(t, "service", mod+"dao")
	forbidden(t, "service", mod+"handler", mod+"router", "github.com/gin-gonic/gin")
}

func TestDAOHasNoUpwardImports(t *testing.T) {
	forbidden(t, "dao", mod+"handler", mod+"service", mod+"router", "github.com/gin-gonic/gin")
}

func TestNoGoToPythonHTTPOrSchemaChange(t *testing.T) {
	for _, pkg := range []string{"common", "dao", "handler", "router", "server", "service"} {
		forbidden(t, pkg, "net/http/httputil")
		entries, err := os.ReadDir(pkg)
		require.NoError(t, err)
		for _, e := range entries {
			if strings.HasSuffix(e.Name(), "_test.go") || !strings.HasSuffix(e.Name(), ".go") {
				continue
			}
			raw, err := os.ReadFile(filepath.Join(pkg, e.Name()))
			require.NoError(t, err)
			assert.NotContains(t, string(raw), "Auto"+"Migrate", e.Name())
			assert.NotContains(t, string(raw), "http.Client", e.Name())
			assert.NotContains(t, string(raw), ":9380", e.Name())
		}
	}
}

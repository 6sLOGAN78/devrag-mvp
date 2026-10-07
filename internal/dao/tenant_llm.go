package dao

import "devrag/internal/entity"

// TenantModelRows builds the tenant_llm rows seeded at registration. It does not touch the
// database: CreateAccount inserts them inside the registration transaction.
func TenantModelRows(tenantID, factory, baseURL string, models map[string]string, now int64) []entity.TenantLLM {
	var rows []entity.TenantLLM
	for _, modelType := range []string{"chat", "embedding", "rerank"} {
		name := models[modelType]
		if name == "" {
			continue
		}
		mt, base, nm := modelType, baseURL, name
		var apiBase *string
		if base != "" {
			apiBase = &base
		}
		rows = append(rows, entity.TenantLLM{
			TenantID: tenantID, LLMFactory: factory, LLMName: &nm, ModelType: &mt, APIBase: apiBase,
			MaxTokens: 8192, Status: "1", CreateTime: &now, UpdateTime: &now,
		})
	}
	return rows
}

/**
 * The five model providers in the fixed display order (D-15) and the form rules the provider dialogs (plan 03-21)
 * read. Provider names are product names and are not translated, except the one the UI-SPEC gives a key
 * (`models.provider.compatible.name`). Slugs match the API (`rag/llm/__init__.py`).
 */
export type ProviderSlug = "openai" | "azure-openai" | "ollama" | "openrouter" | "openai-compatible";

export interface ProviderSpec {
  slug: ProviderSlug;
  /** Literal product name; absent when the name comes from `nameKey`. */
  name?: string;
  nameKey?: string;
  descriptionKey: string;
  fields: {
    /** `none`: not asked (the documented default is used); `required`: the person gives the address. */
    baseUrl: "none" | "required";
    /** Label key of the address field. */
    baseUrlLabelKey: string;
    apiVersion: boolean;
    key: "required" | "optional" | "none";
    chatLabelKey: string;
    embeddingLabelKey: string;
  };
  /** Example model ids for the helper text; the first is a chat model, the second an embedding model. */
  modelExamples: readonly [string, string];
}

const DEFAULT_FIELDS = {
  baseUrlLabelKey: "models.field.baseUrl",
  chatLabelKey: "models.field.chatModel",
  embeddingLabelKey: "models.field.embeddingModel",
} as const;

export const PROVIDERS: readonly ProviderSpec[] = [
  {
    slug: "openai",
    name: "OpenAI",
    descriptionKey: "models.provider.openai.description",
    fields: { ...DEFAULT_FIELDS, baseUrl: "none", apiVersion: false, key: "required" },
    modelExamples: ["gpt-4o-mini", "text-embedding-3-small"],
  },
  {
    slug: "azure-openai",
    name: "Azure OpenAI",
    descriptionKey: "models.provider.azure.description",
    fields: {
      baseUrl: "required",
      baseUrlLabelKey: "models.field.endpoint",
      apiVersion: true,
      key: "required",
      chatLabelKey: "models.field.chatDeployment",
      embeddingLabelKey: "models.field.embeddingDeployment",
    },
    modelExamples: ["my-gpt-4o-deployment", "my-embedding-deployment"],
  },
  {
    slug: "ollama",
    name: "Ollama",
    descriptionKey: "models.provider.ollama.description",
    fields: { ...DEFAULT_FIELDS, baseUrl: "required", apiVersion: false, key: "none" },
    modelExamples: ["llama3.1", "nomic-embed-text"],
  },
  {
    slug: "openrouter",
    name: "OpenRouter",
    descriptionKey: "models.provider.openrouter.description",
    fields: { ...DEFAULT_FIELDS, baseUrl: "none", apiVersion: false, key: "required" },
    modelExamples: ["meta-llama/llama-3.1-8b-instruct", "baai/bge-m3"],
  },
  {
    slug: "openai-compatible",
    nameKey: "models.provider.compatible.name",
    descriptionKey: "models.provider.compatible.description",
    fields: { ...DEFAULT_FIELDS, baseUrl: "required", apiVersion: false, key: "optional" },
    modelExamples: ["my-chat-model", "my-embedding-model"],
  },
];

/** The provider's display name; `translate` resolves the one name that has a key. */
export function providerName(spec: ProviderSpec, translate: (key: string) => string): string {
  return spec.name ?? translate(spec.nameKey ?? spec.slug);
}

export function findProvider(slug: string): ProviderSpec | undefined {
  return PROVIDERS.find((spec) => spec.slug === slug);
}

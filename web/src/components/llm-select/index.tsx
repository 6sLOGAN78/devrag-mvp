import { useTranslation } from "react-i18next";
import { NativeSelect } from "@/components/ui/native-select";
import type { ModelType, ModelView } from "@/services/model-service";

interface LlmSelectProps {
  models: readonly ModelView[];
  /** Only models of this type are offered. */
  type: ModelType;
  /** Composite model id, or empty for "not set". A value that is not in the list renders as "Not set". */
  value: string;
  onChange: (value: string) => void;
  id?: string;
  disabled?: boolean;
  /** Overrides the "Not set" first option. */
  notSetLabel?: string;
  "aria-describedby"?: string;
  "data-testid"?: string;
}

/** Models of one type, grouped by provider. The option value is the composite id the API uses. */
export function LlmSelect({ models, type, value, onChange, id, disabled, notSetLabel, "aria-describedby": describedBy, "data-testid": testId }: LlmSelectProps) {
  const { t } = useTranslation();
  const offered = models.filter((model) => model.type === type);
  const groups = new Map<string, ModelView[]>();
  for (const model of offered) groups.set(model.provider, [...(groups.get(model.provider) ?? []), model]);
  const current = offered.some((model) => model.id === value) ? value : "";
  return (
    <NativeSelect id={id} value={current} disabled={disabled} aria-describedby={describedBy} data-testid={testId} onChange={(event) => onChange(event.target.value)}>
      <option value="">{notSetLabel ?? t("common.notSet")}</option>
      {[...groups.entries()].map(([provider, items]) => (
        <optgroup key={provider} label={provider}>
          {items.map((model) => (
            <option key={model.id} value={model.id}>
              {model.name}
            </option>
          ))}
        </optgroup>
      ))}
    </NativeSelect>
  );
}

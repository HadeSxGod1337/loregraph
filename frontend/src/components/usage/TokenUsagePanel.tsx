import { useTranslation } from "react-i18next";
import { useProjectUsage } from "../../hooks/useProjects";

interface TokenUsagePanelProps {
  projectId: string;
}

interface PricingRates {
  input: number;         // USD per 1M tokens
  output: number;        // USD per 1M tokens
  cacheRead?: number;    // USD per 1M tokens
  cacheCreation?: number;// USD per 1M tokens
}

function getModelPricing(modelName: string): PricingRates {
  const name = modelName.toLowerCase();
  
  // Anthropic Claude 3.5 / 4.5 pricing
  if (name.includes("haiku")) {
    return { input: 0.8, output: 4.0, cacheRead: 0.08, cacheCreation: 1.0 };
  }
  if (name.includes("sonnet")) {
    return { input: 3.0, output: 15.0, cacheRead: 0.3, cacheCreation: 3.75 };
  }
  if (name.includes("opus")) {
    return { input: 15.0, output: 75.0, cacheRead: 1.5, cacheCreation: 18.75 };
  }
  // OpenAI GPT pricing
  if (name.includes("gpt-4o-mini") || name.includes("gpt-4-mini")) {
    return { input: 0.15, output: 0.6 };
  }
  if (name.includes("gpt-4o") || name.includes("gpt-4")) {
    return { input: 2.5, output: 10.0 };
  }
  if (name.includes("o1-mini")) {
    return { input: 3.0, output: 12.0 };
  }
  if (name.includes("o1")) {
    return { input: 15.0, output: 60.0 };
  }
  if (name.includes("claude-3")) {
    return { input: 3.0, output: 15.0, cacheRead: 0.3, cacheCreation: 3.75 };
  }
  
  // Ollama or other local/unknown models are free
  return { input: 0.0, output: 0.0 };
}

function calculateRowCost(row: {
  model: string;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
}): number {
  const rates = getModelPricing(row.model);
  
  const uncachedInput = Math.max(0, row.input_tokens - row.cache_read_tokens - row.cache_creation_tokens);
  
  const inputCost = (uncachedInput * rates.input) / 1000000;
  const outputCost = (row.output_tokens * rates.output) / 1000000;
  
  const cacheReadRate = rates.cacheRead !== undefined ? rates.cacheRead : rates.input * 0.1;
  const cacheReadCost = (row.cache_read_tokens * cacheReadRate) / 1000000;
  
  const cacheCreateRate = rates.cacheCreation !== undefined ? rates.cacheCreation : rates.input * 1.25;
  const cacheCreateCost = (row.cache_creation_tokens * cacheCreateRate) / 1000000;
  
  return inputCost + outputCost + cacheReadCost + cacheCreateCost;
}

export function TokenUsagePanel({ projectId }: TokenUsagePanelProps) {
  const { t } = useTranslation();
  const { data: usageData, isLoading } = useProjectUsage(projectId);

  if (isLoading) {
    return (
      <section className="settings-card token-usage-panel">
        <div className="settings-card-head">
          <h2>{t("usage.heading")}</h2>
          <p className="field-hint">{t("usage.hint")}</p>
        </div>
        <p className="field-hint">{t("common.loading")}</p>
      </section>
    );
  }

  // Calculate aggregates
  const rows = usageData ?? [];
  const totalCalls = rows.reduce((sum, r) => sum + r.calls, 0);
  const totalInput = rows.reduce((sum, r) => sum + r.input_tokens, 0);
  const totalOutput = rows.reduce((sum, r) => sum + r.output_tokens, 0);
  const totalCacheRead = rows.reduce((sum, r) => sum + r.cache_read_tokens, 0);
  const totalCacheCreation = rows.reduce((sum, r) => sum + r.cache_creation_tokens, 0);
  const totalTokens = totalInput + totalOutput;

  const totalCost = rows.reduce((sum, r) => sum + calculateRowCost(r), 0);

  const uncachedInput = Math.max(0, totalInput - totalCacheRead - totalCacheCreation);
  const cacheHitRate = totalInput > 0 ? (totalCacheRead / totalInput) * 100 : 0;

  // Format helper for numbers
  const formatNum = (num: number) => num.toLocaleString();
  
  // Format helper for cost
  const formatCost = (cost: number) => {
    if (cost === 0) return t("usage.free");
    if (cost < 0.01) return `$${cost.toFixed(4)}`;
    return `$${cost.toFixed(2)}`;
  };

  return (
    <section className="settings-card token-usage-panel">
      <div className="settings-card-head">
        <h2>{t("usage.heading")}</h2>
        <p className="field-hint">{t("usage.hint")}</p>
      </div>

      {rows.length === 0 ? (
        <div className="token-usage-empty">
          <p className="field-hint">{t("usage.noUsage")}</p>
        </div>
      ) : (
        <div className="token-usage-content">
          {/* Summary stats */}
          <div className="usage-summary-grid">
            <div className="usage-summary-card total">
              <span className="summary-label">{t("usage.totalTokens")}</span>
              <span className="summary-value">{formatNum(totalTokens)}</span>
              <span className="summary-sub">
                {t("usage.calls", { count: totalCalls })}
              </span>
            </div>

            <div className="usage-summary-card spend">
              <span className="summary-label">{t("usage.estimatedCost")}</span>
              <span className="summary-value" style={{ color: totalCost > 0 ? "var(--text)" : "var(--text-muted)" }}>
                {formatCost(totalCost)}
              </span>
              <span className="summary-sub">USD</span>
            </div>
            
            <div className="usage-summary-card rate">
              <span className="summary-label">{t("usage.cacheHitRate")}</span>
              <span className="summary-value">{cacheHitRate.toFixed(1)}%</span>
              <span className="summary-sub progress-bg">
                <span 
                  className="progress-fill" 
                  style={{ width: `${cacheHitRate}%` }} 
                />
              </span>
            </div>
          </div>

          <div className="usage-detail-totals">
            <div className="detail-total-row">
              <span className="dot uncached" />
              <span className="label">{t("usage.input")} (uncached)</span>
              <span className="val">{formatNum(uncachedInput)}</span>
            </div>
            <div className="detail-total-row">
              <span className="dot cached-read" />
              <span className="label">{t("usage.cachedRead")}</span>
              <span className="val">{formatNum(totalCacheRead)}</span>
            </div>
            <div className="detail-total-row">
              <span className="dot cached-create" />
              <span className="label">{t("usage.cacheCreation")}</span>
              <span className="val">{formatNum(totalCacheCreation)}</span>
            </div>
            <div className="detail-total-row">
              <span className="dot output" />
              <span className="label">{t("usage.output")}</span>
              <span className="val">{formatNum(totalOutput)}</span>
            </div>
          </div>

          <hr className="usage-divider" />

          {/* Breakdown per node & model */}
          <div className="usage-breakdown-list">
            {rows.map((row, idx) => {
              const rowTotal = row.input_tokens + row.output_tokens;
              const rowUncachedInput = Math.max(0, row.input_tokens - row.cache_read_tokens - row.cache_creation_tokens);
              const rowCost = calculateRowCost(row);
              
              const pUncached = rowTotal > 0 ? (rowUncachedInput / rowTotal) * 100 : 0;
              const pCacheRead = rowTotal > 0 ? (row.cache_read_tokens / rowTotal) * 100 : 0;
              const pCacheCreate = rowTotal > 0 ? (row.cache_creation_tokens / rowTotal) * 100 : 0;
              const pOutput = rowTotal > 0 ? (row.output_tokens / rowTotal) * 100 : 0;

              // Node display name
              const nodeTranslationKey = `usage.nodes.${row.node}`;
              const nodeName = t(nodeTranslationKey) !== nodeTranslationKey 
                ? t(nodeTranslationKey) 
                : row.node;

              return (
                <div key={`${row.node}-${row.model}-${idx}`} className="usage-row">
                  <div className="usage-row-meta">
                    <div className="usage-row-node-info">
                      <span className="usage-node-badge">{nodeName}</span>
                      <span className="usage-model-name" title={row.model}>
                        {row.model}
                      </span>
                    </div>
                    <div className="usage-row-meta-right" style={{ textAlign: "right", display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
                      <span className="usage-row-cost" style={{ fontSize: "12.5px", fontWeight: 600, color: rowCost > 0 ? "var(--text)" : "var(--text-muted)" }}>
                        {formatCost(rowCost)}
                      </span>
                      <span className="usage-row-calls" style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                        {t("usage.calls", { count: row.calls })}
                      </span>
                    </div>
                  </div>

                  {/* Stacked bar chart */}
                  <div className="usage-stacked-bar">
                    {pUncached > 0 && (
                      <div 
                        className="bar-segment uncached" 
                        style={{ width: `${pUncached}%` }} 
                        title={`Uncached Input: ${formatNum(rowUncachedInput)}`}
                      />
                    )}
                    {pCacheRead > 0 && (
                      <div 
                        className="bar-segment cached-read" 
                        style={{ width: `${pCacheRead}%` }} 
                        title={`Cached Input (Read): ${formatNum(row.cache_read_tokens)}`}
                      />
                    )}
                    {pCacheCreate > 0 && (
                      <div 
                        className="bar-segment cached-create" 
                        style={{ width: `${pCacheCreate}%` }} 
                        title={`Cache Creation (Write): ${formatNum(row.cache_creation_tokens)}`}
                      />
                    )}
                    {pOutput > 0 && (
                      <div 
                        className="bar-segment output" 
                        style={{ width: `${pOutput}%` }} 
                        title={`Output: ${formatNum(row.output_tokens)}`}
                      />
                    )}
                  </div>

                  <div className="usage-row-numbers">
                    <span>
                      Total: <strong>{formatNum(rowTotal)}</strong>
                    </span>
                    <span className="numbers-breakdown">
                      in: {formatNum(row.input_tokens)} (cache read: {formatNum(row.cache_read_tokens)}) • out: {formatNum(row.output_tokens)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}

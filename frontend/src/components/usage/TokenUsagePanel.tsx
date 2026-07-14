import { useTranslation } from "react-i18next";
import { useProjectUsage } from "../../hooks/useProjects";
import { Icon } from "../ui/Icon";

interface TokenUsagePanelProps {
  projectId: string;
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

  const uncachedInput = Math.max(0, totalInput - totalCacheRead - totalCacheCreation);
  const cacheHitRate = totalInput > 0 ? (totalCacheRead / totalInput) * 100 : 0;

  // Format helper for numbers
  const formatNum = (num: number) => num.toLocaleString();

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
                    <span className="usage-row-calls">
                      {t("usage.calls", { count: row.calls })}
                    </span>
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

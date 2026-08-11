import { useTranslation } from "react-i18next";

import type { NetworkStatus } from "../../api/types";
import { Icon } from "../ui/Icon";

/** Where players can reach this copy from, and — when internet access didn't
 * work — the actual reason, because each one needs a different fix. Shown here
 * rather than only in the launcher console: this is the screen where the DM is
 * about to hand someone a link. */
export function NetworkStatusNotice({ status }: { status: NetworkStatus }) {
  const { t } = useTranslation();

  // Reachability first, then the caveat. A failed UPnP attempt is not an error
  // state: the LAN address still works, so the tone is "here's what's missing".
  const reachKey =
    status.reach === "internet"
      ? "network.reachInternet"
      : status.reach === "lan"
        ? "network.reachLan"
        : "network.reachLocal";

  const problem = status.upnp && !status.upnp.reachable ? status.upnp.outcome : null;

  return (
    <div className={"network-notice network-notice-" + status.reach}>
      <p className="network-notice-head">
        <Icon name={status.reach === "local" ? "eye-off" : "network"} size={14} />
        <span>{t(reachKey)}</span>
        <code>{status.base_url}</code>
      </p>

      {status.reach === "local" && (
        <p className="field-hint">{t("network.localHint")}</p>
      )}

      {problem === "cgnat" && (
        <p className="field-hint">
          {t("network.cgnat", { ip: status.upnp?.external_ip ?? "" })}
        </p>
      )}
      {problem === "no_router" && <p className="field-hint">{t("network.noRouter")}</p>}
      {problem === "refused" && <p className="field-hint">{t("network.refused")}</p>}
      {problem === "failed" && <p className="field-hint">{t("network.failed")}</p>}

      {status.reach !== "local" && !status.tls && (
        <p className="field-hint">{t("network.noTls")}</p>
      )}
    </div>
  );
}

import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { usePlayGraph } from "../hooks/usePlay";
import { PlayBoardCanvas } from "./PlayBoardCanvas";

export function PlayBoardPage() {
  const { t } = useTranslation();
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const { data: graph, isLoading } = usePlayGraph(true);

  if (isLoading) return <p className="play-empty">{t("play.loading")}</p>;
  if (!graph || graph.nodes.length === 0) {
    return <p className="play-empty">{t("play.noCards")}</p>;
  }

  return (
    <div className="play-board">
      <PlayBoardCanvas
        nodes={graph.nodes}
        edges={graph.edges}
        onOpen={(id) => navigate(`/play/${token}/entity/${id}`)}
      />
    </div>
  );
}

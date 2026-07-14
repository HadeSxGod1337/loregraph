from fastapi import APIRouter

from loregraph.api.deps import ProjectStoreDep, UsageStoreDep
from loregraph.schemas.usage import UsageRollupRow

router = APIRouter(tags=["usage"])


@router.get("/projects/{project_id}/usage", response_model=list[UsageRollupRow])
async def project_usage(
    project_id: str, project_store: ProjectStoreDep, usage: UsageStoreDep
) -> list[UsageRollupRow]:
    """Cumulative token spend for a project, sliced by graph node and model.

    Cache-aware: `input_tokens` is the grand total input, of which
    `cache_read_tokens`/`cache_creation_tokens` are the cached portions — so
    the effect of prompt caching is visible, not hidden inside one number.
    Per-session totals are on the agent session itself (AgentSessionOut)."""
    await project_store.get(project_id)  # 404 for unknown projects
    return await usage.project_rollup(project_id)

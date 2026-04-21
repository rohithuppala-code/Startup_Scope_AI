# realtime_groups/backend/social_app.py
# ---------------------------------------------------------------------------
# Social Module Mount Point
#
# This is the FastAPI sub-application for the "Compute-Driven Social Network"
# feature pillar. Mount it into the main StartupScope app in backend/app/main.py:
#
#   from realtime_groups.backend.social_app import include_social_routers
#   include_social_routers(app)
# ---------------------------------------------------------------------------

from fastapi import FastAPI

from realtime_groups.backend.api.profile_router import router as profile_router
from realtime_groups.backend.api.arena_router import router as arena_router
from realtime_groups.backend.api.community_router import router as community_router
from realtime_groups.backend.api.synthesis_router import router as synthesis_router
from realtime_groups.backend.api.search_router import router as search_router
from realtime_groups.backend.api.dm_router import router as dm_router
from realtime_groups.backend.api.comments_router import router as comments_router


def include_social_routers(app: FastAPI) -> None:
    """
    Registers all social routers into an existing FastAPI app.
    This is the RECOMMENDED integration method for the StartupScope monolith.

    Usage in backend/app/main.py:
        from realtime_groups.backend.social_app import include_social_routers
        include_social_routers(app)
    """
    app.include_router(profile_router)
    app.include_router(arena_router)
    app.include_router(community_router)
    app.include_router(synthesis_router)
    app.include_router(search_router)
    app.include_router(dm_router)
    app.include_router(comments_router)


# Standalone sub-application (optional, for microservice deployment)
social_app = FastAPI(
    title="StartupScope Social — Compute-Driven Social Network",
    version="2.0.0",
    description=(
        "The Social Pillar of StartupScope AI. "
        "Implements the Identity Graph, Validation Arena, Community Engine, "
        "DMs, Search & Discovery, Comments, and AI Moderation layer."
    ),
)

include_social_routers(social_app)
